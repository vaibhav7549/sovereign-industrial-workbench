"""Tamper-evident audit trail for every encrypt / compute / decrypt event.

Each JSON line carries `prev` (the MAC of the previous line) and `mac`
(HMAC-SHA256 under the audit key, over the canonical JSON of the entry with
`prev`). Editing, deleting or re-ordering any line breaks the chain, and
without ENCRYPTION_MASTER_KEY an attacker cannot recompute it.

What is logged: event type, actor, ids, counts, sizes, ciphertext digests,
epsilon, timings, keyed query fingerprints.
What is never logged: plaintext text, queries, embeddings, keys, scores of
individual chunks beyond the top-K returned to the user.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from .keys import KeyRing

_FORBIDDEN_KEYS = {"text", "query", "content", "embedding", "plaintext", "secret_key", "master_key", "chunk_text"}
GENESIS = "0" * 64


class AuditLog:
    def __init__(self, path: str, keys: KeyRing):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self._keys = keys
        self._lock = threading.Lock()
        self._prev = self._last_mac()

    def _last_mac(self) -> str:
        if not os.path.exists(self.path):
            return GENESIS
        last = None
        with open(self.path, "rb") as f:
            for line in f:
                if line.strip():
                    last = line
        if last is None:
            return GENESIS
        try:
            return json.loads(last)["mac"]
        except Exception:
            return GENESIS

    def log(self, event: str, actor: str | None = None, **fields: Any) -> dict:
        bad = _FORBIDDEN_KEYS.intersection(fields)
        if bad:  # programming error: refuse rather than leak
            raise ValueError(f"refusing to write sensitive field(s) to audit log: {sorted(bad)}")
        with self._lock:
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "event": event,
                "actor": actor,
                "key_id": self._keys.key_id,
                **fields,
                "prev": self._prev,
            }
            body = json.dumps(entry, sort_keys=True, separators=(",", ":"), default=str).encode()
            entry["mac"] = self._keys.audit_mac(body)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")
            self._prev = entry["mac"]
            return entry

    def verify(self) -> dict:
        """Recompute the chain. Returns {"ok", "entries", "first_bad_line"}."""
        if not os.path.exists(self.path):
            return {"ok": True, "entries": 0, "first_bad_line": None}
        prev = GENESIS
        n = 0
        with open(self.path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if not line.strip():
                    continue
                n += 1
                try:
                    entry = json.loads(line)
                    mac = entry.pop("mac")
                    if entry.get("prev") != prev:
                        return {"ok": False, "entries": n, "first_bad_line": i, "reason": "chain broken"}
                    body = json.dumps(entry, sort_keys=True, separators=(",", ":"), default=str).encode()
                    if self._keys.audit_mac(body) != mac:
                        return {"ok": False, "entries": n, "first_bad_line": i, "reason": "bad MAC"}
                    prev = mac
                except Exception as exc:
                    return {"ok": False, "entries": n, "first_bad_line": i, "reason": f"unparseable: {exc}"}
        return {"ok": True, "entries": n, "first_bad_line": None}


class Timer:
    def __enter__(self):
        self.t = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = round((time.perf_counter() - self.t) * 1000, 2)
