"""Measure the privacy/utility trade-off of Laplace DP on embeddings.

Usage
-----
Synthetic corpus (no model needed, indicative only):
    python scripts/bench_dp_utility.py

Real corpus (recommended before choosing DP_EPSILON for a deployment):
    python scripts/bench_dp_utility.py --ollama http://localhost:11434 \
        --model nomic-embed-text --pairs pairs.jsonl
  where each line of pairs.jsonl is {"query": "...", "passage": "..."} and the
  passage is the correct answer for the query.

Reports recall@1 / recall@5 of the correct passage when both stored passages
and the query are noised with the same epsilon (exactly what the pipeline does).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from encryption.dp import laplace_embedding  # noqa: E402

EPSILONS = [1, 10, 100, 500, 1_000, 2_000, 5_000, 10_000, 50_000, math.inf]


def _unit(m: np.ndarray) -> np.ndarray:
    return m / np.linalg.norm(m, axis=-1, keepdims=True)


def synthetic_corpus(n_docs=300, dim=768, n_topics=15, seed=7):
    """Anisotropic corpus shaped like real sentence-embedding geometry.

    Targets (measured on the generated data and printed): cos(query, its passage)
    ~0.75-0.8, cos(passage, same-topic passage) ~0.6, cos(unrelated) ~0.4.
    """
    rng = np.random.default_rng(seed)
    common = _unit(rng.normal(size=dim))           # shared "language" direction
    topics = _unit(rng.normal(size=(n_topics, dim)))
    topic_of = rng.integers(0, n_topics, size=n_docs)
    specific = _unit(rng.normal(size=(n_docs, dim)))
    docs = _unit(0.62 * common + 0.55 * topics[topic_of] + 0.55 * specific)
    queries = _unit(docs + 0.62 * _unit(rng.normal(size=(n_docs, dim))))
    return docs, queries


def ollama_corpus(url: str, model: str, pairs_path: str):
    import urllib.request

    pairs = [json.loads(l) for l in open(pairs_path, encoding="utf-8") if l.strip()]

    def embed(texts):
        req = urllib.request.Request(
            url.rstrip("/") + "/api/embed",
            data=json.dumps({"model": model, "input": texts}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=600) as r:
            return np.array(json.load(r)["embeddings"], dtype=np.float64)

    docs = _unit(embed(["search_document: " + p["passage"] for p in pairs]))
    queries = _unit(embed(["search_query: " + p["query"] for p in pairs]))
    return docs, queries


def recall(docs, queries, eps, rng, trials=3):
    r1 = r5 = 0.0
    for _ in range(trials if math.isfinite(eps) else 1):
        if math.isfinite(eps):
            d = np.stack([laplace_embedding(v, eps, rng=rng)[0] for v in docs])
            q = np.stack([laplace_embedding(v, eps, rng=rng)[0] for v in queries])
        else:
            d, q = docs, queries
        scores = q @ d.T
        ranks = (scores > scores[np.arange(len(q)), np.arange(len(q))][:, None]).sum(axis=1)
        r1 += float(np.mean(ranks < 1))
        r5 += float(np.mean(ranks < 5))
    n = trials if math.isfinite(eps) else 1
    return r1 / n, r5 / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama")
    ap.add_argument("--model", default="nomic-embed-text")
    ap.add_argument("--pairs")
    ap.add_argument("--json-out")
    args = ap.parse_args()

    if args.ollama and args.pairs:
        docs, queries = ollama_corpus(args.ollama, args.model, args.pairs)
        source = f"ollama:{args.model} ({len(docs)} pairs)"
    else:
        docs, queries = synthetic_corpus()
        source = f"synthetic ({len(docs)} docs, dim {docs.shape[1]})"

    n, dim = docs.shape
    s = docs @ docs.T
    off = s[~np.eye(n, dtype=bool)]
    print(f"corpus: {source}")
    print(f"geometry: cos(query, own passage) mean={np.mean(np.sum(docs*queries,1)):.3f}  "
          f"cos(passage, other) mean={off.mean():.3f}  p95={np.percentile(off,95):.3f}")
    print(f"random-guess recall@1={1/n:.4f} recall@5={min(5,n)/n:.4f}\n")
    print(f"{'epsilon':>9} {'noise b':>9} {'recall@1':>9} {'recall@5':>9}")
    rng = np.random.default_rng(1234)
    rows = []
    for eps in EPSILONS:
        r1, r5 = recall(docs, queries, eps, rng)
        b = (2 * math.sqrt(dim) / eps) if math.isfinite(eps) else 0.0
        rows.append({"epsilon": eps if math.isfinite(eps) else "inf (no DP)", "noise_b": b,
                     "recall_at_1": r1, "recall_at_5": r5})
        print(f"{str(rows[-1]['epsilon']):>9} {b:9.4f} {r1:9.3f} {r5:9.3f}")
    if args.json_out:
        json.dump({"source": source, "dim": dim, "n": n, "rows": rows}, open(args.json_out, "w"), indent=2)


if __name__ == "__main__":
    main()
