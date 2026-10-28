"""FastAPI integration test: /ingest/pdf -> /agent/query -> /agent/verify-encryption.

Needs fastapi + tenseal (skipped otherwise). The LLM is unreachable in CI, so
/agent/query exercises the air-gapped fallback path, which still runs the
encrypted retrieval first.
"""

import importlib
import io
import json

import pytest

from conftest import FakeEmbedder, MockAtomic, requires_tenseal

fastapi = pytest.importorskip("fastapi")
pytestmark = requires_tenseal


@pytest.fixture
def client(tmp_path, monkeypatch, master_key):
    monkeypatch.setenv("ENCRYPTION_ENABLED", "true")
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", master_key)
    monkeypatch.setenv("ENCRYPTION_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HE_CONTEXT_FILE", str(tmp_path / "he" / "ctx.enc"))
    monkeypatch.setenv("DIFFERENTIAL_PRIVACY_ENABLED", "false")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9/v1")  # unreachable -> fallback path
    monkeypatch.setenv("SERPAPI_KEY", "")
    import main

    main = importlib.reload(main)
    atomic = MockAtomic()
    monkeypatch.setattr(main, "call_mcp_tool", atomic)

    async def no_init():
        return None

    monkeypatch.setattr(main, "mcp_initialize", no_init)

    async def no_scholar(kw):
        return []

    monkeypatch.setattr(main, "search_scholar", no_scholar)
    import encryption.embedder as emb

    monkeypatch.setattr(emb.LocalEmbedder, "from_env", classmethod(lambda cls: FakeEmbedder()))
    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        c.atomic = atomic
        c.main = main
        yield c


def test_end_to_end(client):
    token = client.post("/login", params={"username": "operator.v_88"}).json()["token"]
    text = b"Centrifugal compressor surge control uses an anti-surge valve and recycle line."
    r = client.post("/ingest/pdf", params={"token": token},
                    files={"file": ("compressor.txt", io.BytesIO(text), "text/plain")}).json()
    assert r["status"] == "ingested_encrypted" and r["chunks"] == 1 and r["atom_id"]
    assert "anti-surge" not in client.atomic.everything_seen()

    q = client.post("/agent/query", params={"query": "anti-surge valve", "token": token}).json()
    assert q["encrypted_search"]["results"][0]["title"] == "compressor.txt"

    v = client.post("/agent/verify-encryption", params={"token": token}).json()
    assert v["encryption_status"] == "enabled" and v["atoms_encrypted"] == 1
    assert v["audit_chain"]["ok"]

    blocked = client.post("/agent/tool", params={"tool_name": "create_atom", "token": token},
                          json={"content": "plaintext"})
    assert blocked.status_code == 403
