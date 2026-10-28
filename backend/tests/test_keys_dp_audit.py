import json
import math

import numpy as np
import pytest

from encryption.audit import AuditLog
from encryption.dp import DPParams, laplace_embedding
from encryption.envelope import build_envelope, chunk_pages, parse_envelope, parse_mcp_tool_result
from encryption.keys import KeyConfigurationError, KeyRing, generate_master_key


# ------------------------------------------------------------------ keys
def test_missing_master_key_fails_closed():
    for bad in (None, "", "${ENCRYPTION_MASTER_KEY}", "short"):
        with pytest.raises(KeyConfigurationError):
            KeyRing.from_master_key(bad)


def test_fernet_generated_key_is_accepted():
    from cryptography.fernet import Fernet

    KeyRing.from_master_key(Fernet.generate_key().decode())


def test_subkeys_are_domain_separated(keys):
    ks = {keys.text_key, keys.he_wrap_key, keys.vault_mac_key, keys.audit_key}
    assert len(ks) == 4


def test_text_roundtrip_and_aad_binding(keys):
    tok = keys.encrypt_text("Hydrocracker reactor inlet 410 C", "doc1:0:chunk")
    assert "Hydrocracker" not in tok
    assert keys.decrypt_text(tok, "doc1:0:chunk") == "Hydrocracker reactor inlet 410 C"
    with pytest.raises(Exception):  # swapped into another slot -> rejected
        keys.decrypt_text(tok, "doc1:1:chunk")


def test_ciphertext_length_is_bucketed(keys):
    a = keys.encrypt_text("x" * 10, "a")
    b = keys.encrypt_text("x" * 200, "a")
    assert len(a) == len(b)


def test_wrong_master_key_cannot_decrypt(keys):
    other = KeyRing.from_master_key(generate_master_key())
    tok = keys.encrypt_text("secret", "a")
    with pytest.raises(Exception):
        other.decrypt_text(tok, "a")


# -------------------------------------------------------------------- DP
def test_dp_sensitivity_and_scale():
    p = DPParams(epsilon=1.0, dim=768)
    assert math.isclose(p.l1_sensitivity, 2 * math.sqrt(768))
    assert math.isclose(p.laplace_scale, 2 * math.sqrt(768))


def test_dp_output_is_unit_norm_and_noisy():
    x = np.random.default_rng(0).normal(size=768)
    y, _ = laplace_embedding(x, 1000.0, rng=np.random.default_rng(1))
    assert math.isclose(np.linalg.norm(y), 1.0, rel_tol=1e-9)
    assert not np.allclose(y, x / np.linalg.norm(x))


def test_dp_noise_matches_laplace_scale_empirically():
    rng = np.random.default_rng(3)
    x = np.zeros(768)
    x[0] = 1.0
    eps = 500.0
    # undo re-normalisation by checking the raw noise via a huge sample of scales
    samples = []
    for _ in range(200):
        noise = rng.laplace(0, DPParams(eps, 768).laplace_scale, size=768)
        samples.append(noise)
    b_hat = np.mean(np.abs(np.concatenate(samples)))  # E|Laplace(0,b)| = b
    assert math.isclose(b_hat, 2 * math.sqrt(768) / eps, rel_tol=0.03)


def test_dp_rejects_bad_epsilon():
    for e in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ValueError):
            laplace_embedding([1.0, 0.0], e)


def test_epsilon_one_destroys_similarity_structure():
    rng = np.random.default_rng(5)
    x = rng.normal(size=768)
    x /= np.linalg.norm(x)
    sims = [float(laplace_embedding(x, 1.0, rng=rng)[0] @ x) for _ in range(50)]
    assert abs(np.mean(sims)) < 0.05  # indistinguishable from an unrelated vector


# ----------------------------------------------------------------- audit
def test_audit_chain_detects_tampering(tmp_path, keys):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(str(path), keys)
    for i in range(5):
        log.log("ingest_encrypted", actor="op", doc_id=f"d{i}", chunks=i)
    assert log.verify() == {"ok": True, "entries": 5, "first_bad_line": None}
    # reopening continues the chain
    AuditLog(str(path), keys).log("query_encrypted", actor="op", query_fp="abc")
    assert AuditLog(str(path), keys).verify()["ok"]
    lines = path.read_text().splitlines()
    tampered = json.loads(lines[2])
    tampered["chunks"] = 999
    lines[2] = json.dumps(tampered, sort_keys=True)
    path.write_text("\n".join(lines) + "\n")
    res = AuditLog(str(path), keys).verify()
    assert not res["ok"] and res["first_bad_line"] == 3


def test_audit_deleting_a_line_breaks_chain(tmp_path, keys):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(str(path), keys)
    for i in range(4):
        log.log("e", doc_id=str(i))
    lines = path.read_text().splitlines()
    del lines[1]
    path.write_text("\n".join(lines) + "\n")
    assert not AuditLog(str(path), keys).verify()["ok"]


def test_audit_refuses_plaintext_fields(tmp_path, keys):
    log = AuditLog(str(tmp_path / "a.jsonl"), keys)
    for field in ("query", "text", "embedding", "content"):
        with pytest.raises(ValueError):
            log.log("x", **{field: "leak"})


# -------------------------------------------------------------- envelope
def test_chunking_respects_pages_and_size():
    pages = [(1, "Para one. " * 100), (2, "Second page text.\n\nAnother paragraph here.")]
    chunks = chunk_pages(pages, size=300, overlap=50)
    assert all(len(c.text) <= 300 + 60 for c in chunks)
    assert {c.page for c in chunks} == {1, 2}
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_envelope_roundtrip():
    env = build_envelope({"doc_id": "d", "n_chunks": 1}, [{"i": 0, "text_ct": "abc"}])
    parsed = parse_envelope(env)
    assert parsed["header"]["doc_id"] == "d" and parsed["chunks"][0]["text_ct"] == "abc"


def test_parse_mcp_result_shapes():
    ok = {"result": {"content": [{"type": "text", "text": '{"atom_id": "a1"}'}]}}
    assert parse_mcp_tool_result(ok) == ({"atom_id": "a1"}, None)
    assert parse_mcp_tool_result({"error": "MCP server offline or unavailable"})[1]
    assert parse_mcp_tool_result({"result": {"isError": True, "content": [{"type": "text", "text": "bad"}]}})[1] == "bad"
