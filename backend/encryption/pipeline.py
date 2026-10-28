"""End-to-end encrypted ingestion and search (Option A + Option C).

    ingest:  file -> text -> chunks -> embed (local model) -> DP noise -> CKKS encrypt
             -> vault (ciphertexts) + Atomic (AES-GCM envelope, no plaintext)
    search:  query -> embed -> DP noise -> CKKS encrypt -> evaluator computes
             Enc(<q, d_i>) with the public context only -> key holder decrypts the
             scores -> top-K chunk text decrypted at the response boundary

Trust boundary: the backend process (this module + the local LLM) is trusted
and sees plaintext transiently. Atomic, its database and backups, the vault
files at rest and the evaluator are NOT trusted with plaintext.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, List, Optional, Sequence

import numpy as np

from .audit import AuditLog, Timer
from .dp import DPParams, laplace_embedding
from .envelope import SOURCE_SCHEME, build_envelope, chunk_pages, extract_pages, parse_mcp_tool_result
from .he import HEEvaluator, HEKeyHolder, HEParams
from .keys import KeyRing
from .vault import ChunkRow, EncryptedVault, TamperError, sha256_hex

McpCall = Callable[[str, dict], Awaitable[dict]]
EmbedFn = Callable[[List[str], str], Awaitable[List[List[float]]]]


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class EncryptionConfig:
    enabled: bool = True
    dp_enabled: bool = True
    dp_epsilon: float = 1.0
    dp_delta: float = 1e-5
    dp_apply_to_queries: bool = True
    he: HEParams = field(default_factory=HEParams)
    context_file: str = "/data/he/he_context.enc"
    vault_path: str = "/data/he/vault.sqlite3"
    audit_path: str = "/data/audit/encryption_audit.jsonl"
    chunk_size: int = 1200
    chunk_overlap: int = 200
    top_k: int = 5
    max_chunks_per_doc: int = 400
    embed_model: str = "nomic-embed-text"
    cache_max_mb: int = 512

    @classmethod
    def from_env(cls) -> "EncryptionConfig":
        data_dir = os.getenv("ENCRYPTION_DATA_DIR", "/data")
        return cls(
            enabled=_env_bool("ENCRYPTION_ENABLED", False),
            dp_enabled=_env_bool("DIFFERENTIAL_PRIVACY_ENABLED", True),
            dp_epsilon=float(os.getenv("DP_EPSILON", "1.0")),
            dp_delta=float(os.getenv("DP_DELTA", "1e-5")),
            dp_apply_to_queries=_env_bool("DP_APPLY_TO_QUERIES", True),
            he=HEParams.from_env(),
            context_file=os.getenv("HE_CONTEXT_FILE", os.path.join(data_dir, "he", "he_context.enc")),
            vault_path=os.getenv("HE_VAULT_PATH", os.path.join(data_dir, "he", "vault.sqlite3")),
            audit_path=os.getenv("AUDIT_LOG_PATH", os.path.join(data_dir, "audit", "encryption_audit.jsonl")),
            chunk_size=int(os.getenv("CHUNK_SIZE_CHARS", "1200")),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP_CHARS", "200")),
            top_k=int(os.getenv("HE_SEARCH_TOP_K", "5")),
            max_chunks_per_doc=int(os.getenv("MAX_CHUNKS_PER_DOC", "400")),
            embed_model=os.getenv("EMBED_MODEL", "nomic-embed-text"),
            cache_max_mb=int(os.getenv("HE_CACHE_MAX_MB", "512")),
        )


class SecurePipeline:
    def __init__(self, cfg: EncryptionConfig, keys: KeyRing, holder: HEKeyHolder, evaluator: HEEvaluator,
                 vault: EncryptedVault, audit: AuditLog, embed: EmbedFn, mcp_call: McpCall,
                 rng: Optional[np.random.Generator] = None):
        self.cfg = cfg
        self.keys = keys
        self.holder = holder
        self.evaluator = evaluator
        self.vault = vault
        self.audit = audit
        self.embed = embed
        self.mcp_call = mcp_call
        self.rng = rng
        self._he_lock = asyncio.Lock()  # SEAL objects are not shared across threads concurrently

    # ------------------------------------------------------------------ build
    @classmethod
    def build(cls, cfg: EncryptionConfig, embed: EmbedFn, mcp_call: McpCall,
              keys: Optional[KeyRing] = None) -> "SecurePipeline":
        keys = keys or KeyRing.from_env()
        audit = AuditLog(cfg.audit_path, keys)
        with Timer() as t:
            holder, created = HEKeyHolder.load_or_create(cfg.context_file, keys, cfg.he)
        evaluator = HEEvaluator(holder.public_context_bytes(), n_threads=cfg.he.n_threads)
        vault = EncryptedVault(cfg.vault_path, cache_max_bytes=cfg.cache_max_mb * 1024 * 1024)
        audit.log("he_context_created" if created else "he_context_loaded", actor="system",
                  he_context_id=holder.context_id, ms=t.ms, **{"params": cfg.he.describe()})
        return cls(cfg, keys, holder, evaluator, vault, audit, embed, mcp_call)

    # ------------------------------------------------------------- primitives
    def dp_noise(self, embedding: Sequence[float]) -> tuple[List[float], Optional[DPParams]]:
        if not self.cfg.dp_enabled:
            v = np.asarray(embedding, dtype=np.float64)
            n = np.linalg.norm(v)
            return (v / n if n else v).tolist(), None
        noisy, params = laplace_embedding(embedding, self.cfg.dp_epsilon, rng=self.rng)
        return noisy.tolist(), params

    async def encrypt_embedding(self, embedding: Sequence[float]) -> bytes:
        async with self._he_lock:
            return await asyncio.to_thread(self.holder.encrypt, embedding)

    # ----------------------------------------------------------------- ingest
    async def ingest(self, filename: str, data: bytes, actor: str) -> dict:
        t0 = time.perf_counter()
        doc_id = str(uuid.uuid4())
        pages = extract_pages(filename, data)
        chunks = chunk_pages(pages, self.cfg.chunk_size, self.cfg.chunk_overlap)
        if not chunks:
            raise ValueError("no extractable text in document")
        if len(chunks) > self.cfg.max_chunks_per_doc:
            raise ValueError(f"document produces {len(chunks)} chunks (limit MAX_CHUNKS_PER_DOC="
                             f"{self.cfg.max_chunks_per_doc})")

        with Timer() as t_embed:
            embeddings = await self.embed([c.text for c in chunks], "document")
        dim = len(embeddings[0])
        if any(len(e) != dim for e in embeddings):
            raise ValueError("embedding model returned inconsistent dimensions")

        now = time.time()
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows: List[ChunkRow] = []
        records: List[dict] = []
        dp_desc = None
        with Timer() as t_he:
            for c, emb in zip(chunks, embeddings):
                noisy, dp_params = self.dp_noise(emb)
                dp_desc = dp_params.describe() if dp_params else None
                ct = await self.encrypt_embedding(noisy)
                uid = f"{doc_id}:{c.index}"
                ct_hash = sha256_hex(ct)
                rows.append(ChunkRow(
                    chunk_uid=uid, doc_id=doc_id, atom_id=None, chunk_index=c.index, page=c.page, dim=dim,
                    he_context_id=self.holder.context_id, ct=ct, ct_sha256=ct_hash,
                    ct_mac=self.keys.vault_mac(ct, uid), text_ct=self.keys.encrypt_text(c.text, f"{uid}:chunk"),
                    dp_epsilon=self.cfg.dp_epsilon if dp_params else None, created_at=now,
                ))
                records.append({
                    "i": c.index,
                    "text_ct": rows[-1].text_ct,
                    "plaintext_embedding": None,
                    "encrypted_embedding_ref": {"store": "backend-vault", "chunk_uid": uid,
                                                "sha256": ct_hash, "bytes": len(ct)},
                    "embedding_metadata": {
                        "model": self.cfg.embed_model, "dim": dim,
                        "dp_noise_applied": bool(dp_params), "dp_epsilon": rows[-1].dp_epsilon,
                        "encryption_scheme": "CKKS", "he_context_id": self.holder.context_id,
                        "timestamp": stamp,
                    },
                })
        title_ct = self.keys.encrypt_text(filename or "untitled", f"{doc_id}:title")
        self.vault.put_document(doc_id, title_ct, rows, created_by=actor)

        header = {"v": 1, "doc_id": doc_id, "title_ct": title_ct, "n_chunks": len(chunks),
                  "text_cipher": "AES-256-GCM", "he": self.cfg.he.describe() | {"context_id": self.holder.context_id},
                  "dp": dp_desc, "key_id": self.keys.key_id, "source": "ingestion", "encrypted_at": stamp}
        envelope = build_envelope(header, records)
        assert_no_plaintext(envelope, [c.text for c in chunks] + [filename])

        with Timer() as t_mcp:
            resp = await self.mcp_call("create_atom", {"content": envelope, "source_url": SOURCE_SCHEME + doc_id})
        payload, err = parse_mcp_tool_result(resp)
        atom_id = (payload or {}).get("atom_id") if not err else None
        if atom_id:
            self.vault.set_atom_id(doc_id, atom_id)

        total_ct = sum(len(r.ct) for r in rows)
        self.audit.log(
            "ingest_encrypted", actor=actor, doc_id=doc_id, atom_id=atom_id, chunks=len(chunks), dim=dim,
            he_context_id=self.holder.context_id, ciphertext_bytes=total_ct,
            ct_sha256=[r.ct_sha256[:16] for r in rows], dp=dp_desc,
            title_fp=self.keys.fingerprint(filename or ""), envelope_bytes=len(envelope),
            atomic_status="stored" if atom_id else f"not stored: {err}",
            ms={"embed": t_embed.ms, "dp_and_encrypt": t_he.ms, "atomic": t_mcp.ms,
                "total": round((time.perf_counter() - t0) * 1000, 2)},
        )
        return {
            "atom_id": atom_id,
            "doc_id": doc_id,
            "status": "ingested_encrypted" if atom_id else "ingested_encrypted_vault_only",
            "chunks": len(chunks),
            "atomic_error": err,
            "encryption_metadata": {
                "text_cipher": "AES-256-GCM (HKDF-derived key, AAD-bound to doc/chunk)",
                "embedding_scheme": "CKKS", "he_context_id": self.holder.context_id,
                "ciphertext_bytes_total": total_ct, "embedding_model": self.cfg.embed_model, "dim": dim,
                "differential_privacy": dp_desc, "plaintext_sent_to_atomic": False, "encrypted_at": stamp,
                "timings_ms": {"embed": t_embed.ms, "dp_and_encrypt": t_he.ms, "atomic": t_mcp.ms},
            },
        }

    # ----------------------------------------------------------------- search
    def _load_encrypted_docs(self):
        meta = self.vault.chunk_meta(self.holder.context_id)
        objs = []
        for uid, doc_id, atom_id, idx, page, ct_hash, ct_mac, size in meta:
            obj = self.vault.cache_get(uid)
            if obj is None:
                ct = self.vault.get_ct(uid)
                if self.keys.vault_mac(ct, uid) != ct_mac or sha256_hex(ct) != ct_hash:
                    raise TamperError(f"vault ciphertext for {uid} failed integrity check")
                obj = self.evaluator.load(ct)
                self.vault.cache_put(uid, obj, size)
            objs.append(obj)
        return meta, objs

    async def search(self, query: str, actor: str, top_k: Optional[int] = None) -> dict:
        top_k = top_k or self.cfg.top_k
        timings = {}
        with Timer() as t:
            q_emb = (await self.embed([query], "query"))[0]
        timings["embed_query"] = t.ms
        apply_dp = self.cfg.dp_enabled and self.cfg.dp_apply_to_queries
        with Timer() as t:
            if apply_dp:
                noisy, _ = laplace_embedding(q_emb, self.cfg.dp_epsilon, rng=self.rng)
                q_vec = noisy.tolist()
            else:
                v = np.asarray(q_emb, dtype=np.float64)
                q_vec = (v / (np.linalg.norm(v) or 1.0)).tolist()
            enc_q = await self.encrypt_embedding(q_vec)
        timings["dp_and_encrypt_query"] = t.ms
        q_fp = self.keys.fingerprint(query)
        self.audit.log("query_encrypted", actor=actor, query_fp=q_fp, query_chars=len(query),
                       dp_applied=apply_dp, dp_epsilon=self.cfg.dp_epsilon if apply_dp else None,
                       ct_sha256=sha256_hex(enc_q)[:16], ct_bytes=len(enc_q))

        async with self._he_lock:
            with Timer() as t:
                meta, docs = await asyncio.to_thread(self._load_encrypted_docs)
            timings["load_ciphertexts"] = t.ms
            if not docs:
                return {"results": [], "searched_chunks": 0, "timings_ms": timings,
                        "note": "no encrypted chunks for the active HE context"}
            with Timer() as t:
                enc_scores = await asyncio.to_thread(self.evaluator.dot_many, enc_q, docs)
            timings["homomorphic_dot_products"] = t.ms
            self.audit.log("he_similarity_computed", actor="evaluator", query_fp=q_fp, chunks=len(docs),
                           he_context_id=self.holder.context_id, ms=t.ms, secret_key_present=False)
            with Timer() as t:
                scores = await asyncio.to_thread(self.holder.decrypt_scores, enc_scores)
            timings["decrypt_scores"] = t.ms

        order = np.argsort(scores)[::-1][:top_k]
        results = []
        with Timer() as t:
            for i in order:
                uid, doc_id, atom_id, idx, page, *_ = meta[i]
                text_ct, _, _, _ = self.vault.get_text_ct(uid)
                text = self.keys.decrypt_text(text_ct, f"{uid}:chunk")
                doc = self.vault.get_doc(doc_id)
                title = self.keys.decrypt_text(doc[2], f"{doc_id}:title") if doc else None
                results.append({"atom_id": atom_id, "doc_id": doc_id, "chunk_index": idx, "page": page,
                                "title": title, "score": round(float(scores[i]), 4),
                                "preview": text[:300], "text": text})
        timings["decrypt_results"] = t.ms
        timings["total"] = round(sum(timings.values()), 2)
        self.audit.log("results_decrypted_at_boundary", actor=actor, query_fp=q_fp, returned=len(results),
                       searched_chunks=len(docs), chunk_uids=[r["doc_id"] + ":" + str(r["chunk_index"]) for r in results],
                       ms=timings)
        return {"results": results, "searched_chunks": len(docs), "timings_ms": timings,
                "dp": {"applied_to_query": apply_dp, "epsilon": self.cfg.dp_epsilon if apply_dp else None}}

    # ----------------------------------------------------------------- status
    def status(self) -> dict:
        st = self.vault.stats()
        active = self.holder.context_id
        orphaned = [c for c in st["he_context_ids"] if c != active]
        return {
            "encryption_status": "enabled",
            "dp_enabled": self.cfg.dp_enabled,
            "dp_epsilon": self.cfg.dp_epsilon if self.cfg.dp_enabled else None,
            "dp_delta": self.cfg.dp_delta,
            "dp_mechanism": "Laplace, per-embedding local DP, L1 sensitivity 2*sqrt(d)",
            "atoms_encrypted": st["atoms_encrypted"],
            "documents_encrypted": st["documents"],
            "chunks_encrypted": st["chunks_encrypted"],
            "ciphertext_bytes": st["ciphertext_bytes"],
            "dp_epsilons_in_store": st["dp_epsilons_in_store"],
            "he": self.cfg.he.describe() | {"context_id": active},
            "chunks_under_other_contexts": orphaned,
            "key_id": self.keys.key_id,
            "evaluator_has_secret_key": False,
            "audit_chain": self.audit.verify(),
            "he_stats": vars(self.holder.stats) | {"dot_products": self.evaluator.stats.dot_products,
                                                    "seconds_eval": self.evaluator.stats.seconds_eval},
        }


def assert_no_plaintext(envelope: str, secrets: Sequence[str], min_len: int = 24) -> None:
    """Fail closed if any sizeable plaintext fragment would be sent to Atomic."""
    for s in secrets:
        if not s:
            continue
        s = s.strip()
        probes = [s] if len(s) < min_len else [s[i:i + min_len] for i in range(0, len(s) - min_len + 1, max(1, len(s) // 8))]
        for p in probes:
            if len(p) >= 8 and p in envelope:
                raise RuntimeError("plaintext leak guard tripped: refusing to send document to Atomic")
