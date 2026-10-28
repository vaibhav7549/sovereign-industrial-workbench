"""CKKS homomorphic encryption for embeddings (Option A), built on TenSEAL.

Roles (enforced in code, so the evaluator can later move to another host):

  KeyHolder  - owns the secret key. Encrypts embeddings/queries, decrypts final
               similarity scores only. Lives in the backend process.
  Evaluator  - owns ONLY the public context (public + relinearisation + Galois
               keys, secret key dropped). Computes Enc(q) . Enc(d) for every
               stored chunk without being able to decrypt anything.

Parameters: N = 8192, coeff modulus [60, 40, 40, 60] (200 bits; SEAL's 128-bit
security bound for N = 8192 is 218 bits), scale 2^40. One ct x ct
multiplication + rescale consumes one level; one level remains spare.

Vectors are zero-padded to the next power of two (768 -> 1024) so TenSEAL's
rotate-and-sum in .dot() takes log2(1024) = 10 rotations instead of 18.

At rest the secret context is serialised with TenSEAL's own format (not
pickle - unpickling untrusted files executes code) and sealed with AES-256-GCM
under a key derived from ENCRYPTION_MASTER_KEY.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from .keys import KeyRing

try:  # TenSEAL is a hard requirement only when encryption is enabled
    import tenseal as ts
except ImportError:  # pragma: no cover - surfaced as a clear runtime error
    ts = None


def _require_tenseal():
    if ts is None:
        raise RuntimeError("tenseal is not installed; `pip install tenseal` (Python 3.8-3.12 wheels)")


def next_pow2(n: int) -> int:
    return 1 << (max(1, n) - 1).bit_length()


@dataclass(frozen=True)
class HEParams:
    poly_modulus_degree: int = 8192
    coeff_mod_bit_sizes: tuple = (60, 40, 40, 60)
    global_scale_bits: int = 40
    n_threads: int = 1

    @property
    def slots(self) -> int:
        return self.poly_modulus_degree // 2

    def describe(self) -> dict:
        return {
            "scheme": "CKKS",
            "library": f"TenSEAL {getattr(ts, '__version__', 'n/a')} (Microsoft SEAL)",
            "poly_modulus_degree": self.poly_modulus_degree,
            "coeff_mod_bit_sizes": list(self.coeff_mod_bit_sizes),
            "total_coeff_modulus_bits": sum(self.coeff_mod_bit_sizes),
            "global_scale": f"2^{self.global_scale_bits}",
            "security_level": "128-bit (HomomorphicEncryption.org standard)",
            "slots": self.slots,
        }

    @classmethod
    def from_env(cls) -> "HEParams":
        import json

        raw = os.getenv("HE_COEFF_MOD_BIT_LENGTHS", "[60, 40, 40, 60]")
        sizes = tuple(int(x) for x in json.loads(raw))
        p = cls(
            poly_modulus_degree=int(os.getenv("HE_POLY_MODULUS_DEGREE", "8192")),
            coeff_mod_bit_sizes=sizes,
            global_scale_bits=int(os.getenv("HE_GLOBAL_SCALE_BITS", "40")),
            n_threads=int(os.getenv("HE_THREADS", "1")),
        )
        p.validate()
        return p

    def validate(self) -> None:
        max_bits = {4096: 109, 8192: 218, 16384: 438, 32768: 881}
        if self.poly_modulus_degree not in max_bits:
            raise ValueError("HE_POLY_MODULUS_DEGREE must be 4096, 8192, 16384 or 32768")
        if sum(self.coeff_mod_bit_sizes) > max_bits[self.poly_modulus_degree]:
            raise ValueError(
                f"coeff modulus {sum(self.coeff_mod_bit_sizes)} bits exceeds the 128-bit-security "
                f"limit of {max_bits[self.poly_modulus_degree]} for N={self.poly_modulus_degree}"
            )
        if len(self.coeff_mod_bit_sizes) < 3:
            raise ValueError("need at least one multiplicative level (>= 3 moduli)")


@dataclass
class HEStats:
    encryptions: int = 0
    dot_products: int = 0
    decryptions: int = 0
    seconds_encrypt: float = 0.0
    seconds_eval: float = 0.0
    seconds_decrypt: float = 0.0


class HEKeyHolder:
    """Owns the secret CKKS context. Only this object can decrypt."""

    def __init__(self, secret_ctx: "ts.Context", params: HEParams, created_at: float):
        if not secret_ctx.is_private():
            raise ValueError("key holder needs a private context")
        self._ctx = secret_ctx
        self.params = params
        self.created_at = created_at
        self.stats = HEStats()
        public = secret_ctx.copy()
        public.make_context_public()
        self._public_bytes = public.serialize(
            save_public_key=True, save_secret_key=False, save_galois_keys=True, save_relin_keys=True
        )
        self.context_id = hashlib.sha256(self._public_bytes).hexdigest()[:16]

    # ---- lifecycle ---------------------------------------------------------
    @classmethod
    def create(cls, params: HEParams) -> "HEKeyHolder":
        _require_tenseal()
        ctx = ts.context(
            ts.SCHEME_TYPE.CKKS,
            poly_modulus_degree=params.poly_modulus_degree,
            coeff_mod_bit_sizes=list(params.coeff_mod_bit_sizes),
            n_threads=params.n_threads,
        )
        ctx.global_scale = 2 ** params.global_scale_bits
        ctx.generate_galois_keys()
        ctx.generate_relin_keys()
        return cls(ctx, params, time.time())

    @classmethod
    def load_or_create(cls, path: str, keys: KeyRing, params: HEParams) -> tuple["HEKeyHolder", bool]:
        """Load the sealed context from `path`, or create + seal a new one. Returns (holder, created)."""
        _require_tenseal()
        if os.path.exists(path):
            with open(path, "rb") as f:
                blob = f.read()
            try:
                raw = keys.unwrap_he_context(blob)
            except Exception as exc:
                raise RuntimeError(
                    f"Cannot unseal HE context at {path}: wrong ENCRYPTION_MASTER_KEY or tampered file"
                ) from exc
            ctx = ts.context_from(raw, n_threads=params.n_threads)
            holder = cls(ctx, params, os.path.getmtime(path))
            return holder, False
        holder = cls.create(params)
        raw = holder._ctx.serialize(
            save_public_key=True, save_secret_key=True, save_galois_keys=True, save_relin_keys=True
        )
        _atomic_write(path, keys.wrap_he_context(raw))
        return holder, True

    # ---- crypto ------------------------------------------------------------
    def public_context_bytes(self) -> bytes:
        return self._public_bytes

    def pad(self, vec: Sequence[float]) -> List[float]:
        n = next_pow2(len(vec))
        if n > self.params.slots:
            raise ValueError(f"vector of {len(vec)} dims does not fit {self.params.slots} CKKS slots")
        out = [float(x) for x in vec]
        out.extend([0.0] * (n - len(out)))
        return out

    def encrypt(self, vec: Sequence[float]) -> bytes:
        t = time.perf_counter()
        ct = ts.ckks_vector(self._ctx, self.pad(vec)).serialize()
        self.stats.encryptions += 1
        self.stats.seconds_encrypt += time.perf_counter() - t
        return ct

    def decrypt_vector(self, ct_bytes: bytes) -> List[float]:
        t = time.perf_counter()
        out = ts.ckks_vector_from(self._ctx, ct_bytes).decrypt()
        self.stats.decryptions += 1
        self.stats.seconds_decrypt += time.perf_counter() - t
        return out

    def decrypt_scores(self, encrypted_scores: Iterable["ts.CKKSVector"]) -> List[float]:
        """Decrypt evaluator outputs (each a 1-slot ciphertext) using the secret key."""
        t = time.perf_counter()
        sk = self._ctx.secret_key()
        out = [float(v.decrypt(sk)[0]) for v in encrypted_scores]
        self.stats.decryptions += len(out)
        self.stats.seconds_decrypt += time.perf_counter() - t
        return out


class HEEvaluator:
    """Computes on ciphertexts with the PUBLIC context only. Cannot decrypt."""

    def __init__(self, public_context_bytes: bytes, n_threads: int = 1):
        _require_tenseal()
        self._ctx = ts.context_from(public_context_bytes, n_threads=n_threads)
        if self._ctx.is_private():  # defence in depth: refuse a secret key here
            raise ValueError("evaluator must not receive a secret key")
        self.stats = HEStats()

    def load(self, ct_bytes: bytes) -> "ts.CKKSVector":
        return ts.ckks_vector_from(self._ctx, ct_bytes)

    def dot_many(self, enc_query_bytes: bytes, enc_docs: Sequence["ts.CKKSVector"]) -> List["ts.CKKSVector"]:
        """Return Enc(<q, d_i>) for every encrypted doc vector - no decryption anywhere."""
        t = time.perf_counter()
        q = self.load(enc_query_bytes)
        out = [d.dot(q) for d in enc_docs]
        self.stats.dot_products += len(out)
        self.stats.seconds_eval += time.perf_counter() - t
        return out


def _atomic_write(path: str, data: bytes) -> None:
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".he_ctx_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
