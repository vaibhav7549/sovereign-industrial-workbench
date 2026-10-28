import hashlib
import json
import os
import re
import sys
import uuid

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from encryption.keys import KeyRing, generate_master_key  # noqa: E402

DIM = 768


@pytest.fixture
def master_key():
    return generate_master_key()


@pytest.fixture
def keys(master_key):
    return KeyRing.from_master_key(master_key)


def hash_embed(text: str, dim: int = DIM) -> list:
    """Deterministic bag-of-words embedding: texts sharing words get similar vectors."""
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
    def __init__(self):
        self.calls = []

    async def __call__(self, texts, kind):
        self.calls.append((kind, len(texts)))
        return [hash_embed(t) for t in texts]


class MockAtomic:
    """Mimics Atomic's MCP JSON-RPC responses (create_atom/read_atom) and records everything it receives."""

    def __init__(self, online=True):
        self.online = online
        self.atoms = {}
        self.received = []  # every argument payload Atomic ever saw

    async def __call__(self, tool, args):
        self.received.append((tool, json.loads(json.dumps(args))))
        if not self.online:
            return {"error": "MCP server offline or unavailable"}
        if tool == "create_atom":
            atom_id = str(uuid.uuid4())
            self.atoms[atom_id] = args["content"]
            payload = {"atom_id": atom_id, "content_preview": args["content"][:200], "tags": [],
                       "embedding_status": "pending"}
        elif tool == "read_atom":
            payload = {"atom_id": args["atom_id"], "content": self.atoms.get(args["atom_id"], "")}
        else:
            payload = []
        return {"jsonrpc": "2.0", "id": 1,
                "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

    def everything_seen(self) -> str:
        return json.dumps(self.received)


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()


@pytest.fixture
def mock_atomic():
    return MockAtomic()


try:
    import tenseal  # noqa: F401
    HAVE_TENSEAL = True
except ImportError:
    HAVE_TENSEAL = False

requires_tenseal = pytest.mark.skipif(not HAVE_TENSEAL, reason="tenseal not installed")
