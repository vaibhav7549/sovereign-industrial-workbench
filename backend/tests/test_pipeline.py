"""Pipeline logic tests (ingest -> store -> search -> decrypt) against a mock Atomic.

HE here is a TEST-ONLY plaintext stand-in with the same interface as
encryption.he (it lives in this test file and cannot be enabled in the app), so
the orchestration, envelope, leakage guard, integrity checks and audit trail
can be tested without TenSEAL. test_he_tenseal.py runs the same flow with
real CKKS when tenseal is installed.
"""

import asyncio
import json

import numpy as np
import pytest

from conftest import HAVE_TENSEAL, MockAtomic
from encryption.audit import AuditLog
from encryption.he import HEParams, HEStats
from encryption.pipeline import EncryptionConfig, SecurePipeline, assert_no_plaintext
from encryption.vault import EncryptedVault, TamperError

DOCS = {
    "hydrocracker_sop.txt": (
        "Hydrocracker emergency depressurisation must be initiated when reactor bed temperature "
        "exceeds the high-high trip. Operators verify quench hydrogen flow and isolate the feed pump.\n\n"
        "Catalyst regeneration requires nitrogen purging and oxygen concentration below one percent."
    ),
    "boiler_manual.txt": (
        "Boiler feedwater chemistry: maintain pH between nine and ten, dose oxygen scavenger, "
        "and blow down the drum to control total dissolved solids.\n\n"
        "Safety valve lift testing is performed annually by the boiler inspector."
    ),
    "compressor_notes.txt": (
        "Centrifugal compressor surge control uses an anti-surge valve and recycle line. "
        "Vibration above the alarm limit requires a controlled shutdown and bearing inspection."
    ),
}


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


def make_pipeline(tmp_path, keys, embedder, atomic, dp_enabled=False, eps=1.0):
    cfg = EncryptionConfig(enabled=True, dp_enabled=dp_enabled, dp_epsilon=eps,
                           vault_path=str(tmp_path / "vault.sqlite3"),
                           audit_path=str(tmp_path / "audit.jsonl"), chunk_size=400, chunk_overlap=50)
    return SecurePipeline(cfg, keys, _FakeHolder(), _FakeEvaluator(),
                          EncryptedVault(cfg.vault_path), AuditLog(cfg.audit_path, keys), embedder, atomic,
                          rng=np.random.default_rng(0))


def run(coro):
    return asyncio.run(coro)


def ingest_all(p):
    return [run(p.ingest(name, text.encode(), actor="operator.v_88")) for name, text in DOCS.items()]


def test_ingest_sends_no_plaintext_to_atomic(tmp_path, keys, fake_embedder, mock_atomic):
    p = make_pipeline(tmp_path, keys, fake_embedder, mock_atomic)
    results = ingest_all(p)
    assert all(r["status"] == "ingested_encrypted" and r["atom_id"] for r in results)
    seen = mock_atomic.everything_seen()
    for name, text in DOCS.items():
        for sentence in text.replace("\n", " ").split(". "):
            frag = sentence.strip()[:30]
            if len(frag) >= 12:
                assert frag not in seen, f"plaintext fragment leaked to Atomic: {frag!r}"
        assert name not in seen  # titles are encrypted too
    # schema: plaintext_embedding is null, encrypted ref present
    content = next(iter(mock_atomic.atoms.values()))
    chunk_lines = [json.loads(l) for l in content.splitlines() if l.startswith('{"embedding_metadata"') or '"type":"chunk"' in l]
    assert chunk_lines and all(c["plaintext_embedding"] is None for c in chunk_lines)
    assert all(c["embedding_metadata"]["encryption_scheme"] == "CKKS" for c in chunk_lines)


def test_search_returns_correct_document_and_never_calls_atomic(tmp_path, keys, fake_embedder, mock_atomic):
    p = make_pipeline(tmp_path, keys, fake_embedder, mock_atomic)
    ingest_all(p)
    n_before = len(mock_atomic.received)
    res = run(p.search("what to do on compressor surge and high vibration", actor="op"))
    assert res["results"][0]["title"] == "compressor_notes.txt"
    res = run(p.search("boiler feedwater pH and oxygen scavenger dosing", actor="op"))
    assert res["results"][0]["title"] == "boiler_manual.txt"
    assert len(mock_atomic.received) == n_before  # search is local: Atomic learns nothing
    assert res["results"][0]["atom_id"]


def test_dp_large_epsilon_keeps_ranking_small_epsilon_destroys_it(tmp_path, keys, fake_embedder, mock_atomic):
    q = "hydrocracker reactor bed temperature trip depressurisation quench hydrogen"
    good = make_pipeline(tmp_path / "a", keys, fake_embedder, MockAtomic(), dp_enabled=True, eps=20000)
    ingest_all(good)
    assert run(good.search(q, actor="op"))["results"][0]["title"] == "hydrocracker_sop.txt"

    hits = 0
    for seed in range(12):
        bad = make_pipeline(tmp_path / f"b{seed}", keys, fake_embedder, MockAtomic(), dp_enabled=True, eps=1.0)
        bad.rng = np.random.default_rng(seed)
        ingest_all(bad)
        hits += run(bad.search(q, actor="op"))["results"][0]["title"] == "hydrocracker_sop.txt"
    assert hits <= 9  # ~chance level (2 of 5 chunks belong to the target doc); not reliable retrieval


def test_vault_tampering_is_detected(tmp_path, keys, fake_embedder, mock_atomic):
    p = make_pipeline(tmp_path, keys, fake_embedder, mock_atomic)
    ingest_all(p)
    uid = p.vault.chunk_meta(p.holder.context_id)[0][0]
    p.vault._db.execute("UPDATE chunks SET ct=? WHERE chunk_uid=?", (b"\x00" * 6144, uid))
    with pytest.raises(TamperError):
        run(p.search("anything", actor="op"))


def test_swapped_chunk_text_is_rejected(tmp_path, keys, fake_embedder, mock_atomic):
    p = make_pipeline(tmp_path, keys, fake_embedder, mock_atomic)
    ingest_all(p)
    rows = p.vault.chunk_meta(p.holder.context_id)
    a, b = rows[0][0], rows[1][0]
    ta = p.vault.get_text_ct(a)[0]
    p.vault._db.execute("UPDATE chunks SET text_ct=? WHERE chunk_uid=?", (ta, b))
    with pytest.raises(Exception):
        p.keys.decrypt_text(p.vault.get_text_ct(b)[0], f"{b}:chunk")


def test_atomic_offline_keeps_doc_in_vault(tmp_path, keys, fake_embedder):
    p = make_pipeline(tmp_path, keys, fake_embedder, MockAtomic(online=False))
    r = run(p.ingest("boiler_manual.txt", DOCS["boiler_manual.txt"].encode(), actor="op"))
    assert r["status"] == "ingested_encrypted_vault_only" and r["atom_id"] is None
    assert run(p.search("boiler safety valve", actor="op"))["results"]


def test_audit_log_has_no_plaintext_and_verifies(tmp_path, keys, fake_embedder, mock_atomic):
    p = make_pipeline(tmp_path, keys, fake_embedder, mock_atomic)
    ingest_all(p)
    query = "centrifugal compressor anti-surge valve recycle"
    run(p.search(query, actor="op"))
    raw = (tmp_path / "audit.jsonl").read_text()
    assert query not in raw and "Hydrocracker emergency" not in raw and "boiler_manual.txt" not in raw
    events = [json.loads(l)["event"] for l in raw.splitlines()]
    assert events.count("ingest_encrypted") == 3
    assert {"query_encrypted", "he_similarity_computed", "results_decrypted_at_boundary"} <= set(events)
    assert p.status()["audit_chain"]["ok"]


def test_status_counts(tmp_path, keys, fake_embedder, mock_atomic):
    p = make_pipeline(tmp_path, keys, fake_embedder, mock_atomic, dp_enabled=True, eps=5000)
    ingest_all(p)
    s = p.status()
    assert s["atoms_encrypted"] == 3 and s["documents_encrypted"] == 3
    assert s["dp_epsilon"] == 5000 and s["evaluator_has_secret_key"] is False


def test_leak_guard_trips():
    with pytest.raises(RuntimeError):
        assert_no_plaintext("header ... Operators verify quench hydrogen flow ...",
                            ["Operators verify quench hydrogen flow and isolate the feed pump."])
    assert_no_plaintext("only ciphertext gAAAAB...", ["Operators verify quench hydrogen flow"])


def test_empty_document_rejected(tmp_path, keys, fake_embedder, mock_atomic):
    p = make_pipeline(tmp_path, keys, fake_embedder, mock_atomic)
    with pytest.raises(ValueError):
        run(p.ingest("empty.txt", b"   \n  ", actor="op"))
