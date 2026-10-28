#!/usr/bin/env python3
"""Benchmark encrypted vs plaintext similarity search (CKKS, TenSEAL).

    taskset -c 0 python3 scripts/bench_he_latency.py --chunks 25 50 100 200 --json-out bench.json

Pins TenSEAL to one thread (HE_THREADS=1) to match the 1-core deployment target.
Reports per-stage latency, ciphertext size, numerical error vs plaintext and
top-5 ranking agreement.

If TenSEAL is not installed (e.g. Python 3.13 has no wheel yet — install
Python 3.11 and run again), the script falls back to a numpy stand-in so
the scaffolding and output format can still be verified.  The numpy numbers
are orders of magnitude faster than real CKKS; they are labelled clearly so
they cannot be mistaken for real measurements.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from encryption.he import HEEvaluator, HEKeyHolder, HEParams  # noqa: E402

# ---------------------------------------------------------------------------
# Numpy fallback — used when TenSEAL is not installed.
# Numbers are much faster than real CKKS; clearly labelled in output.
# ---------------------------------------------------------------------------
try:
    import tenseal as _ts_check  # noqa: F401
    _HAVE_TENSEAL = True
except ImportError:
    _HAVE_TENSEAL = False


class _NumpyHolder:
    """Drop-in stand-in for HEKeyHolder with plaintext numpy math."""
    context_id = "numpy-stub"

    def __init__(self, params):
        self.params = params

    def encrypt(self, vec):
        return np.asarray(vec, dtype=np.float64).tobytes()

    def decrypt_scores(self, encs):
        return [float(e) for e in encs]

    def public_context_bytes(self):
        return b"numpy-stub"


class _NumpyEvaluator:
    def load(self, b):
        return np.frombuffer(b, dtype=np.float64)

    def dot_many(self, q_bytes, docs):
        qv = self.load(q_bytes)
        return [float(d @ qv) for d in docs]


def unit_rows(rng, n, d):
    m = rng.normal(size=(n, d))
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", type=int, nargs="+", default=[25, 50, 100, 200])
    ap.add_argument("--dim", type=int, default=768)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--json-out")
    a = ap.parse_args()

    params = HEParams(n_threads=1)

    if not _HAVE_TENSEAL:
        print("WARNING: tenseal not installed — using numpy stand-in.")
        print("         Numbers below are NOT real CKKS timings.")
        print("         Install Python 3.11 + tenseal for real measurements.\n")
        holder = _NumpyHolder(params)
        ev = _NumpyEvaluator()
        keygen_s = 0.0
    else:
        t = time.perf_counter()
        holder = HEKeyHolder.create(params)
        keygen_s = time.perf_counter() - t
        ev = HEEvaluator(holder.public_context_bytes(), n_threads=1)
    rng = np.random.default_rng(42)
    pub_bytes = holder.public_context_bytes()
    out = {"machine": {"cpu": platform.processor() or platform.machine(), "cores_visible": os.cpu_count(),
                       "affinity": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
                       "python": platform.python_version()},
           "tenseal_available": _HAVE_TENSEAL,
           "params": params.describe(), "dim": a.dim, "keygen_s": round(keygen_s, 3),
           "public_context_bytes": len(pub_bytes), "runs": []}
    print(json.dumps({k: out[k] for k in ("machine", "tenseal_available", "dim", "keygen_s",
                                           "public_context_bytes")}, indent=1))

    max_n = max(a.chunks)
    docs = unit_rows(rng, max_n, a.dim)
    t = time.perf_counter()
    cts = [holder.encrypt(d) for d in docs]
    enc_per_chunk_ms = (time.perf_counter() - t) * 1000 / max_n
    ct_bytes = statistics.mean(len(c) for c in cts)
    loaded = [ev.load(c) for c in cts]
    print(f"encrypt: {enc_per_chunk_ms:.2f} ms/chunk, ciphertext {ct_bytes/1024:.0f} KiB/chunk")

    print(f"{'chunks':>6} {'plain ms':>9} {'enc q ms':>9} {'HE dot ms':>10} {'decrypt ms':>10} "
          f"{'total ms':>9} {'ms/chunk':>9} {'max|err|':>9} {'top5 same':>9}")
    for n in a.chunks:
        rows = []
        for _ in range(a.repeats):
            q = unit_rows(rng, 1, a.dim)[0]
            t0 = time.perf_counter(); plain = docs[:n] @ q; t_plain = time.perf_counter() - t0
            t0 = time.perf_counter(); eq = holder.encrypt(q); t_encq = time.perf_counter() - t0
            t0 = time.perf_counter(); enc = ev.dot_many(eq, loaded[:n]); t_dot = time.perf_counter() - t0
            t0 = time.perf_counter(); he = np.array(holder.decrypt_scores(enc)); t_dec = time.perf_counter() - t0
            rows.append((t_plain, t_encq, t_dot, t_dec, float(np.max(np.abs(he - plain))),
                         list(np.argsort(-he)[:5]) == list(np.argsort(-plain)[:5])))
        med = lambda i: statistics.median(r[i] for r in rows) * 1000  # noqa: E731
        total = med(1) + med(2) + med(3)
        run = {"chunks": n, "plaintext_ms": round(med(0), 4), "encrypt_query_ms": round(med(1), 2),
               "he_dot_ms": round(med(2), 2), "decrypt_scores_ms": round(med(3), 2), "he_total_ms": round(total, 2),
               "he_ms_per_chunk": round(total / n, 2), "max_abs_error": max(r[4] for r in rows),
               "top5_identical": all(r[5] for r in rows), "slowdown_x": round(total / max(med(0), 1e-6))}
        out["runs"].append(run)
        print(f"{n:6d} {run['plaintext_ms']:9.4f} {run['encrypt_query_ms']:9.2f} {run['he_dot_ms']:10.2f} "
              f"{run['decrypt_scores_ms']:10.2f} {total:9.1f} {run['he_ms_per_chunk']:9.2f} "
              f"{run['max_abs_error']:9.2e} {str(run['top5_identical']):>9}")
    out["encrypt_ms_per_chunk"] = round(enc_per_chunk_ms, 2)
    out["ciphertext_bytes_per_chunk"] = int(ct_bytes)
    per = out["runs"][-1]["he_ms_per_chunk"]
    out["chunks_within_5s_budget"] = int(5000 / per) if per else None
    if _HAVE_TENSEAL:
        print(f"\n=> about {out['chunks_within_5s_budget']} chunks fit a 5 s HE search budget on this machine")
    else:
        print("\n=> numpy stand-in: numbers above are NOT real CKKS.")
        print("   To get real timings: pip install tenseal  (requires Python 3.8-3.12)")
        print("   Then re-run:  taskset -c 0 python3 scripts/bench_he_latency.py --json-out bench_he.json")
        out["chunks_within_5s_budget"] = None
    if a.json_out:
        with open(a.json_out, "w") as f:
            json.dump(out, f, indent=2)
        print(f"=> results written to {a.json_out}")


if __name__ == "__main__":
    main()
