"""
Profile query latency without TenSEAL (uses fake HE stand-in identical to the test suite).
Run:  python scripts/profile_query.py

Reports per-stage timings for a realistic workload (3 docs, 5-15 chunks each)
and identifies which stage dominates — so you know what to fix before running
on the real VM with TenSEAL.
"""
import asyncio
import hashlib
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("ENCRYPTION_MASTER_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

from encryption.audit import AuditLog
from encryption.he import HEParams, HEStats
from encryption.keys import KeyRing, generate_master_key
from encryption.pipeline import EncryptionConfig, SecurePipeline
from encryption.vault import EncryptedVault

DIM = 768


def hash_embed(text: str, dim: int = DIM) -> list:
    v = np.zeros(dim)
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if len(w) < 3:
            continue
        h = int(hashlib.sha256(w.encode()).hexdigest(), 16)
        rng = np.random.default_rng(h % (2**32))
        v += rng.normal(size=dim)
    n = np.linalg.norm(v)
    return (v / n if n else v).tolist()


class FakeEmbedder:
    async def __call__(self, texts, kind):
        await asyncio.sleep(0)          # yields but no real latency
        return [hash_embed(t) for t in texts]


class FakeEmbedderSlow:
    """Simulates a typical Ollama round-trip: ~150 ms per batch."""
    async def __call__(self, texts, kind):
        await asyncio.sleep(0.15)
        return [hash_embed(t) for t in texts]


class MockAtomic:
    async def __call__(self, tool, args):
        import json, uuid
        if tool == "create_atom":
            atom_id = str(uuid.uuid4())
            return {"jsonrpc": "2.0", "id": 1,
                    "result": {"content": [{"type": "text", "text": json.dumps({"atom_id": atom_id})}], "isError": False}}
        return {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "{}"}], "isError": False}}


# ---------------------------------------------------------------------------
# Fake HE (same as test_pipeline.py — identical interface, plaintext math)
# ---------------------------------------------------------------------------

class _FakeHolder:
    context_id = "fakectx000000000"

    def __init__(self):
        self.params = HEParams()
        self.stats = HEStats()

    def encrypt(self, vec):
        self.stats.encryptions += 1
        return np.asarray(vec, dtype=np.float64).tobytes()

    def decrypt_scores(self, encs):
        return [float(e) for e in encs]


class _FakeEvaluator:
    def __init__(self):
        self.stats = HEStats()

    def load(self, b):
        return np.frombuffer(b, dtype=np.float64)

    def dot_many(self, q, docs):
        qv = self.load(q)
        self.stats.dot_products += len(docs)
        return [float(d @ qv) for d in docs]


DOCS = {
    "hydrocracker_sop.txt": (
        "Hydrocracker emergency depressurisation must be initiated when reactor bed temperature "
        "exceeds the high-high trip. Operators verify quench hydrogen flow and isolate the feed pump.\n\n"
        "Catalyst regeneration requires nitrogen purging and oxygen concentration below one percent. "
        "The reactor effluent cooler is isolated during any emergency shutdown. Feed preheat furnace "
        "must be tripped before feed pump isolation. Monitor reactor inlet temperature continuously.\n\n"
        "Relief valve upstream isolation is prohibited during normal operation. Safety instrumented "
        "system requires proof-test every 12 months. High-pressure separator level control is critical."
    ),
    "boiler_manual.txt": (
        "Boiler feedwater chemistry: maintain pH between nine and ten, dose oxygen scavenger, "
        "and blow down the drum to control total dissolved solids.\n\n"
        "Safety valve lift testing is performed annually by the boiler inspector. "
        "Superheater drain valves must be open during startup and warm-through.\n\n"
        "Refractory inspection interval is every two years. Burner management system (BMS) "
        "requires full functional test after any repair. Stack temperature indicates excess air."
    ),
    "compressor_notes.txt": (
        "Centrifugal compressor surge control uses an anti-surge valve and recycle line. "
        "Vibration above the alarm limit requires a controlled shutdown and bearing inspection.\n\n"
        "Dry gas seals require clean dry nitrogen. Lube oil system requires flushing after "
        "bearing replacement. Speed control is via a steam turbine driver and governor valve.\n\n"
        "Piping stress analysis is required after any nozzle modification. Startup checklist "
        "must be completed before any attempt to start the machine."
    ),
}


def make_pipeline(tmp_path, embedder, dp_enabled=False, eps=5000.0):
    mk = generate_master_key()
    keys = KeyRing.from_master_key(mk)
    cfg = EncryptionConfig(
        enabled=True, dp_enabled=dp_enabled, dp_epsilon=eps,
        vault_path=str(tmp_path / "vault.sqlite3"),
        audit_path=str(tmp_path / "audit.jsonl"),
        chunk_size=600, chunk_overlap=100,
    )
    return SecurePipeline(
        cfg, keys, _FakeHolder(), _FakeEvaluator(),
        EncryptedVault(cfg.vault_path), AuditLog(cfg.audit_path, keys),
        embedder, MockAtomic(), rng=np.random.default_rng(42),
    )


async def run_profile():
    tmp = Path(tempfile.mkdtemp())

    # -----------------------------------------------------------------------
    # 1. Ingest with fast embedder (not the bottleneck here)
    # -----------------------------------------------------------------------
    fast = make_pipeline(tmp / "fast", FakeEmbedder(), dp_enabled=True, eps=5000)
    for name, text in DOCS.items():
        await fast.ingest(name, text.encode(), actor="profiler")

    print("=" * 60)
    print("STAGE TIMINGS (fake HE, fast embedder)")
    print("=" * 60)
    queries = [
        "hydrocracker reactor temperature trip quench hydrogen",
        "boiler feedwater pH oxygen scavenger",
        "compressor surge anti-surge valve vibration bearing",
    ]
    for q in queries:
        r = await fast.search(q, actor="profiler")
        tm = r["timings_ms"]
        top = r["results"][0]["title"] if r["results"] else "—"
        print(f"\n  Query: {q[:55]}")
        print(f"  Top result: {top}")
        for stage, ms in tm.items():
            bar = "█" * max(1, int(ms / 5))
            print(f"    {stage:<35} {ms:7.2f} ms  {bar}")

    # -----------------------------------------------------------------------
    # 2. Slow embedder (simulates Ollama latency)
    # -----------------------------------------------------------------------
    slow = make_pipeline(tmp / "slow", FakeEmbedderSlow(), dp_enabled=True, eps=5000)
    for name, text in DOCS.items():
        await slow.ingest(name, text.encode(), actor="profiler")

    print("\n" + "=" * 60)
    print("STAGE TIMINGS (fake HE, slow embedder — simulates Ollama ~150 ms)")
    print("=" * 60)
    q = "hydrocracker reactor temperature trip"
    r = await slow.search(q, actor="profiler")
    tm = r["timings_ms"]
    for stage, ms in tm.items():
        bar = "█" * max(1, int(ms / 5))
        print(f"    {stage:<35} {ms:7.2f} ms  {bar}")

    # -----------------------------------------------------------------------
    # 3. Scaling: how does chunk count affect dot-product time?
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("SCALING: dot-product time vs chunk count (fake HE = numpy)")
    print("NOTE: replace with TenSEAL times from bench_he_latency.py on VM")
    print("=" * 60)
    for n_chunks in [10, 25, 50, 100, 200]:
        tmp2 = Path(tempfile.mkdtemp())
        mk = generate_master_key()
        keys = KeyRing.from_master_key(mk)
        cfg = EncryptionConfig(
            enabled=True, dp_enabled=False,
            vault_path=str(tmp2 / "v.db"), audit_path=str(tmp2 / "a.jsonl"),
            chunk_size=300, chunk_overlap=50,
        )
        vault = EncryptedVault(cfg.vault_path)
        audit = AuditLog(cfg.audit_path, keys)
        holder = _FakeHolder()
        ev = _FakeEvaluator()
        p = SecurePipeline(cfg, keys, holder, ev, vault, audit,
                           FakeEmbedder(), MockAtomic(), rng=np.random.default_rng(0))
        # ingest synthetic chunks
        big_text = " ".join([f"word{i} process equipment valve pump compressor boiler" for i in range(n_chunks * 5)])
        await p.ingest("synthetic.txt", big_text.encode(), actor="bench")
        actual = vault.stats()["chunks_encrypted"]

        t0 = time.perf_counter()
        for _ in range(3):
            await p.search("process equipment valve pump", actor="bench")
        elapsed_ms = (time.perf_counter() - t0) / 3 * 1000

        last_r = await p.search("process equipment valve pump", actor="bench")
        dot_ms = last_r["timings_ms"].get("homomorphic_dot_products", 0)
        load_ms = last_r["timings_ms"].get("load_ciphertexts", 0)
        embed_ms = last_r["timings_ms"].get("embed_query", 0)

        print(f"  {actual:4d} chunks  avg_total={elapsed_ms:6.1f} ms  "
              f"load={load_ms:.1f}  dots={dot_ms:.1f}  embed={embed_ms:.1f}")

    # -----------------------------------------------------------------------
    # 4. DP epsilon impact on recall
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("DP EPSILON vs SEARCH ACCURACY (fake HE)")
    print("=" * 60)
    QUERY = "hydrocracker reactor bed temperature high-high trip depressurisation"
    for eps in [1.0, 100.0, 500.0, 1000.0, 2000.0, 5000.0]:
        hits = 0
        for seed in range(10):
            t_tmp = Path(tempfile.mkdtemp())
            p = make_pipeline(t_tmp, FakeEmbedder(), dp_enabled=True, eps=eps)
            for name, text in DOCS.items():
                await p.ingest(name, text.encode(), actor="bench")
            r = await p.search(QUERY, actor="bench")
            if r["results"] and r["results"][0]["title"] == "hydrocracker_sop.txt":
                hits += 1
        print(f"  ε={eps:>8.0f}  recall@1 = {hits}/10")

    print("\n" + "=" * 60)
    print("DIAGNOSIS & RECOMMENDED FIXES")
    print("=" * 60)
    print("""
  BOTTLENECK 1 — Ollama embedding call (~150 ms per query)
    The embed call is a synchronous HTTP round-trip to localhost:11434.
    Fix: add a query embedding cache (LRU by query hash) so repeated
    queries skip the Ollama call entirely.

  BOTTLENECK 2 — CKKS dot products (20-35 ms × n_chunks on real CKKS)
    With N=8192 and 100+ chunks this is 2–4 s. The fix is either:
    (a) Slot packing: encode 4 chunks per ciphertext → 4× speedup
    (b) Reduce dims: nomic-embed Matryoshka to 256-d → fewer rotations
    (c) HE_CACHE_MAX_MB: ensure cache is warm (add warmup() at startup)

  BOTTLENECK 3 — Cold vault load on first search
    All ciphertexts are loaded + HMAC-verified on every cache miss.
    Fix: call _load_encrypted_docs at startup (warmup), not on first query.

  BOTTLENECK 4 — DP ε = 1.0 (default in config)
    At ε=1 search returns random chunks. Set DP_EPSILON=5000 in .env
    for useful retrieval while still blunting embedding-inversion attacks.
  """)


if __name__ == "__main__":
    asyncio.run(run_profile())
