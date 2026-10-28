"""Local encrypted vector vault.

Why CKKS ciphertexts live here and not inside Atomic atoms:
  * Atomic cannot compute on CKKS ciphertexts (Rust + sqlite-vec, plaintext
    similarity only), so the evaluator has to run next to the backend anyway.
  * A fresh N=8192 ciphertext is ~300-400 KB. Put into an atom's markdown, it
    would be re-chunked, re-embedded and auto-tagged by Atomic's own pipeline
    (hundreds of wasted embedding calls per chunk on a 1-core box).
The atom in Atomic carries the ciphertext's SHA-256 so the two stores can be
cross-checked; the vault row carries an HMAC so tampering is detected on load.

Nothing in this database is plaintext: rows hold CKKS ciphertexts, AES-GCM
sealed chunk text, and non-sensitive metadata (ids, sizes, timestamps, epsilon).
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_uid      TEXT PRIMARY KEY,
    doc_id         TEXT NOT NULL,
    atom_id        TEXT,
    chunk_index    INTEGER NOT NULL,
    page           INTEGER,
    dim            INTEGER NOT NULL,
    he_context_id  TEXT NOT NULL,
    ct             BLOB NOT NULL,
    ct_sha256      TEXT NOT NULL,
    ct_mac         TEXT NOT NULL,
    text_ct        TEXT NOT NULL,
    dp_epsilon     REAL,
    created_at     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE TABLE IF NOT EXISTS docs (
    doc_id      TEXT PRIMARY KEY,
    atom_id     TEXT,
    title_ct    TEXT NOT NULL,
    n_chunks    INTEGER NOT NULL,
    created_by  TEXT,
    created_at  REAL NOT NULL
);
"""


@dataclass
class ChunkRow:
    chunk_uid: str
    doc_id: str
    atom_id: Optional[str]
    chunk_index: int
    page: Optional[int]
    dim: int
    he_context_id: str
    ct: bytes
    ct_sha256: str
    ct_mac: str
    text_ct: str
    dp_epsilon: Optional[float]
    created_at: float


class TamperError(RuntimeError):
    pass


class EncryptedVault:
    def __init__(self, path: str, cache_max_bytes: int = 512 * 1024 * 1024):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        # deserialised-ciphertext cache: chunk_uid -> object (evaluator-owned)
        self._cache: "OrderedDict[str, object]" = OrderedDict()
        self._cache_bytes = 0
        self._cache_max = cache_max_bytes

    # ---- writes -------------------------------------------------------------
    def put_document(self, doc_id: str, title_ct: str, rows: List[ChunkRow], created_by: str) -> None:
        with self._lock:
            self._db.execute("BEGIN")
            try:
                self._db.execute(
                    "INSERT INTO docs(doc_id, atom_id, title_ct, n_chunks, created_by, created_at) VALUES (?,?,?,?,?,?)",
                    (doc_id, None, title_ct, len(rows), created_by, time.time()),
                )
                self._db.executemany(
                    "INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        (r.chunk_uid, r.doc_id, r.atom_id, r.chunk_index, r.page, r.dim, r.he_context_id,
                         r.ct, r.ct_sha256, r.ct_mac, r.text_ct, r.dp_epsilon, r.created_at)
                        for r in rows
                    ],
                )
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def set_atom_id(self, doc_id: str, atom_id: str) -> None:
        with self._lock:
            self._db.execute("UPDATE docs SET atom_id=? WHERE doc_id=?", (atom_id, doc_id))
            self._db.execute("UPDATE chunks SET atom_id=? WHERE doc_id=?", (atom_id, doc_id))

    def delete_document(self, doc_id: str) -> None:
        with self._lock:
            uids = [r[0] for r in self._db.execute("SELECT chunk_uid FROM chunks WHERE doc_id=?", (doc_id,))]
            self._db.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
            self._db.execute("DELETE FROM docs WHERE doc_id=?", (doc_id,))
            for u in uids:
                hit = self._cache.pop(u, None)
                if hit is not None:
                    self._cache_bytes -= hit[1]

    # ---- reads --------------------------------------------------------------
    def chunk_meta(self, he_context_id: str) -> List[tuple]:
        """(chunk_uid, doc_id, atom_id, chunk_index, page, ct_sha256, ct_mac, length) - no blob load."""
        with self._lock:
            return list(self._db.execute(
                "SELECT chunk_uid, doc_id, atom_id, chunk_index, page, ct_sha256, ct_mac, length(ct) "
                "FROM chunks WHERE he_context_id=? ORDER BY created_at, chunk_index", (he_context_id,)
            ))

    def get_ct(self, chunk_uid: str) -> bytes:
        with self._lock:
            row = self._db.execute("SELECT ct FROM chunks WHERE chunk_uid=?", (chunk_uid,)).fetchone()
        if not row:
            raise KeyError(chunk_uid)
        return row[0]

    def get_text_ct(self, chunk_uid: str) -> tuple[str, str, int, Optional[int]]:
        with self._lock:
            row = self._db.execute(
                "SELECT text_ct, doc_id, chunk_index, page FROM chunks WHERE chunk_uid=?", (chunk_uid,)
            ).fetchone()
        if not row:
            raise KeyError(chunk_uid)
        return row

    def get_doc(self, doc_id: str) -> Optional[tuple]:
        with self._lock:
            return self._db.execute(
                "SELECT doc_id, atom_id, title_ct, n_chunks, created_at FROM docs WHERE doc_id=?", (doc_id,)
            ).fetchone()

    def stats(self) -> dict:
        docs, atoms = self._db.execute("SELECT COUNT(*), COUNT(atom_id) FROM docs").fetchone()
        chunks, ct_bytes = self._db.execute("SELECT COUNT(*), COALESCE(SUM(length(ct)),0) FROM chunks").fetchone()
        contexts = [r[0] for r in self._db.execute("SELECT DISTINCT he_context_id FROM chunks")]
        eps = [r[0] for r in self._db.execute("SELECT DISTINCT dp_epsilon FROM chunks")]
        return {
            "documents": docs,
            "atoms_encrypted": atoms,
            "chunks_encrypted": chunks,
            "ciphertext_bytes": ct_bytes,
            "he_context_ids": contexts,
            "dp_epsilons_in_store": eps,
        }

    # ---- evaluator cache ----------------------------------------------------
    def cache_get(self, chunk_uid: str):
        hit = self._cache.get(chunk_uid)
        if hit is None:
            return None
        self._cache.move_to_end(chunk_uid)
        return hit[0]

    def cache_put(self, chunk_uid: str, obj, size: int) -> None:
        if chunk_uid in self._cache:
            return
        self._cache[chunk_uid] = (obj, size)
        self._cache_bytes += size
        while self._cache_bytes > self._cache_max and self._cache:
            _, (_, s) = self._cache.popitem(last=False)
            self._cache_bytes -= s


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
