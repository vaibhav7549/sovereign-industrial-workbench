"""Real CKKS tests (skipped automatically when tenseal is not installed)."""

import asyncio
import os

import numpy as np
import pytest

from conftest import MockAtomic, requires_tenseal
from encryption.he import HEEvaluator, HEKeyHolder, HEParams, next_pow2

pytestmark = requires_tenseal


@pytest.fixture(scope="module")
def holder():
    return HEKeyHolder.create(HEParams())


def unit(rng, d=768):
    v = rng.normal(size=d)
    return v / np.linalg.norm(v)


def test_next_pow2():
    assert next_pow2(768) == 1024 and next_pow2(1024) == 1024 and next_pow2(1025) == 2048


def test_encrypt_decrypt_roundtrip(holder):
    v = unit(np.random.default_rng(0))
    out = np.array(holder.decrypt_vector(holder.encrypt(v)))
    assert out.shape == (1024,)
    assert np.max(np.abs(out[:768] - v)) < 1e-4 and np.max(np.abs(out[768:])) < 1e-4


def test_ciphertext_reveals_nothing_obvious(holder):
    v = unit(np.random.default_rng(1))
    ct = holder.encrypt(v)
    assert v.astype(np.float64).tobytes()[:64] not in ct
    assert holder.encrypt(v) != ct  # probabilistic encryption


def test_encrypted_dot_matches_plaintext(holder):
    rng = np.random.default_rng(2)
    ev = HEEvaluator(holder.public_context_bytes())
    q = unit(rng)
    docs = [unit(rng) for _ in range(20)]
    enc = ev.dot_many(holder.encrypt(q), [ev.load(holder.encrypt(d)) for d in docs])
    he_scores = np.array(holder.decrypt_scores(enc))
    plain = np.array([d @ q for d in docs])
    assert np.max(np.abs(he_scores - plain)) < 1e-3
    assert list(np.argsort(-he_scores)[:5]) == list(np.argsort(-plain)[:5])


def test_evaluator_cannot_decrypt(holder):
    ev = HEEvaluator(holder.public_context_bytes())
    assert not ev._ctx.has_secret_key() and ev._ctx.is_public()
    vec = ev.load(holder.encrypt([0.5] * 8))
    with pytest.raises(Exception):
        vec.decrypt()


def test_sealed_context_roundtrip_and_wrong_key(tmp_path, keys, master_key):
    from encryption.keys import KeyRing, generate_master_key

    path = str(tmp_path / "ctx.enc")
    h1, created = HEKeyHolder.load_or_create(path, keys, HEParams())
    assert created and oct(os.stat(path).st_mode)[-3:] == "600"
    raw = open(path, "rb").read()
    assert b"tenseal" not in raw.lower()  # sealed, not a readable serialisation
    h2, created2 = HEKeyHolder.load_or_create(path, keys, HEParams())
    assert not created2 and h2.context_id == h1.context_id
    ct = h1.encrypt([0.25] * 16)
    assert abs(h2.decrypt_vector(ct)[0] - 0.25) < 1e-4
    with pytest.raises(RuntimeError):
        HEKeyHolder.load_or_create(path, KeyRing.from_master_key(generate_master_key()), HEParams())


def test_insecure_params_rejected():
    with pytest.raises(ValueError):
        HEParams(poly_modulus_degree=8192, coeff_mod_bit_sizes=(60, 60, 60, 60)).validate()


def test_full_pipeline_with_real_ckks(tmp_path, keys, fake_embedder):
    from encryption.audit import AuditLog
    from encryption.pipeline import EncryptionConfig, SecurePipeline
    from encryption.vault import EncryptedVault
    from test_pipeline import DOCS

    cfg = EncryptionConfig(enabled=True, dp_enabled=False, context_file=str(tmp_path / "ctx.enc"),
                           vault_path=str(tmp_path / "v.sqlite3"), audit_path=str(tmp_path / "a.jsonl"),
                           chunk_size=400, chunk_overlap=50)
    atomic = MockAtomic()
    p = SecurePipeline.build(cfg, embed=fake_embedder, mcp_call=atomic, keys=keys)
    for name, text in DOCS.items():
        asyncio.run(p.ingest(name, text.encode(), actor="op"))
    res = asyncio.run(p.search("compressor surge anti-surge valve vibration", actor="op"))
    assert res["results"][0]["title"] == "compressor_notes.txt"
    assert p.status()["audit_chain"]["ok"]
    assert "Centrifugal compressor" not in atomic.everything_seen()
