
"""CKKS homomorphic encryption for embeddings using TenSEAL.

KeyHolder owns the private CKKS context. HEEvaluator receives only the public
context and evaluates encrypted dot products without decrypting them.

Secret contexts are serialized using TenSEAL and sealed at rest using
KeyRing's authenticated encryption.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import tempfile
import time
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from .keys import KeyRing

try:
    import tenseal as ts
except ImportError:  # pragma: no cover
    ts = None


# Versioned marker for the encrypted context payload.
# The marker, context ID, and serialized context are all authenticated by
# KeyRing.wrap_he_context().
_CONTEXT_ENVELOPE_MAGIC = b"SWB-HE-CONTEXT\x02"
_CONTEXT_ID_LENGTH = 16


def _require_tenseal() -> None:
    if ts is None:
        raise RuntimeError(
            "tenseal is not installed; install a compatible TenSEAL package"
        )


def next_pow2(n: int) -> int:
    return 1 << (max(1, n) - 1).bit_length()


def _context_id(raw: bytes) -> str:
    """Legacy ID derivation for older context files."""
    return hashlib.sha256(raw).hexdigest()[:16]


def _pack_context(context_id: str, raw: bytes) -> bytes:
    """Pack an ID and serialized context for authenticated encryption."""
    try:
        encoded_id = context_id.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("context ID must be ASCII") from exc

    if len(encoded_id) != _CONTEXT_ID_LENGTH:
        raise ValueError("context ID must be exactly 16 ASCII characters")

    if not raw:
        raise ValueError("serialized context cannot be empty")

    return _CONTEXT_ENVELOPE_MAGIC + encoded_id + raw


def _unpack_context(payload: bytes) -> tuple[str, bytes]:
    """Unpack a versioned payload, or accept a legacy serialized context."""
    if not payload.startswith(_CONTEXT_ENVELOPE_MAGIC):
        # Backward compatibility with the previous on-disk format.
        return _context_id(payload), payload

    offset = len(_CONTEXT_ENVELOPE_MAGIC)
    end_id = offset + _CONTEXT_ID_LENGTH

    if len(payload) <= end_id:
        raise ValueError("truncated HE context envelope")

    try:
        context_id = payload[offset:end_id].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid HE context ID") from exc

    raw = payload[end_id:]
    if not raw:
        raise ValueError("empty serialized HE context")

    return context_id, raw


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
            "library": (
                f"TenSEAL {getattr(ts, '__version__', 'n/a')} "
                "(Microsoft SEAL)"
            ),
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

        params = cls(
            poly_modulus_degree=int(
                os.getenv("HE_POLY_MODULUS_DEGREE", "8192")
            ),
            coeff_mod_bit_sizes=sizes,
            global_scale_bits=int(
                os.getenv("HE_GLOBAL_SCALE_BITS", "40")
            ),
            n_threads=int(os.getenv("HE_THREADS", "1")),
        )
        params.validate()
        return params

    def validate(self) -> None:
        max_bits = {
            4096: 109,
            8192: 218,
            16384: 438,
            32768: 881,
        }

        if self.poly_modulus_degree not in max_bits:
            raise ValueError(
                "HE_POLY_MODULUS_DEGREE must be 4096, 8192, 16384 or 32768"
            )

        total_bits = sum(self.coeff_mod_bit_sizes)
        if total_bits > max_bits[self.poly_modulus_degree]:
            raise ValueError(
                f"coeff modulus {total_bits} bits exceeds the "
                f"128-bit-security limit of "
                f"{max_bits[self.poly_modulus_degree]} for "
                f"N={self.poly_modulus_degree}"
            )

        if len(self.coeff_mod_bit_sizes) < 3:
            raise ValueError(
                "need at least one multiplicative level (>= 3 moduli)"
            )


@dataclass
class HEStats:
    encryptions: int = 0
    dot_products: int = 0
    decryptions: int = 0
    seconds_encrypt: float = 0.0
    seconds_eval: float = 0.0
    seconds_decrypt: float = 0.0


class HEKeyHolder:
    """Owns the private CKKS context and performs decryption."""

    def __init__(
        self,
        secret_ctx: "ts.Context",
        params: HEParams,
        created_at: float,
        context_id: str = "",
    ):
        if not secret_ctx.is_private():
            raise ValueError("key holder needs a private context")

        self._ctx = secret_ctx
        self.params = params
        self.created_at = created_at
        self.stats = HEStats()

        public = secret_ctx.copy()
        public.make_context_public()

        self._public_bytes = public.serialize(
            save_public_key=True,
            save_secret_key=False,
            save_galois_keys=True,
            save_relin_keys=True,
        )

        self.context_id = context_id

    # ---- lifecycle ---------------------------------------------------------

    @classmethod
    def create(cls, params: HEParams) -> "tuple[HEKeyHolder, bytes]":
        """Create a private CKKS context and return its serialized bytes."""
        _require_tenseal()

        params.validate()

        ctx = ts.context(
            ts.SCHEME_TYPE.CKKS,
            poly_modulus_degree=params.poly_modulus_degree,
            coeff_mod_bit_sizes=list(params.coeff_mod_bit_sizes),
            n_threads=params.n_threads,
        )

        ctx.global_scale = 2 ** params.global_scale_bits
        ctx.generate_galois_keys()
        ctx.generate_relin_keys()

        raw = ctx.serialize(
            save_public_key=True,
            save_secret_key=True,
            save_galois_keys=True,
            save_relin_keys=True,
        )

        # The ID is independent of TenSEAL serialization behavior.
        context_id = secrets.token_hex(8)

        holder = cls(
            ctx,
            params,
            time.time(),
            context_id=context_id,
        )
        return holder, raw

    @classmethod
    def load_or_create(
        cls,
        path: str,
        keys: KeyRing,
        params: HEParams,
    ) -> "tuple[HEKeyHolder, bool]":
        """Load a sealed context or create and persist a new one."""
        _require_tenseal()
        params.validate()

        if os.path.exists(path):
            with open(path, "rb") as f:
                blob = f.read()

            # Authenticate and decrypt before interpreting any payload data.
            try:
                payload = keys.unwrap_he_context(blob)
            except Exception as exc:
                raise RuntimeError(
                    f"Cannot unseal HE context at {path}: "
                    "wrong ENCRYPTION_MASTER_KEY or tampered file"
                ) from exc

            try:
                context_id, raw = _unpack_context(payload)
                ctx = ts.context_from(raw, n_threads=params.n_threads)

                if not ctx.is_private():
                    raise ValueError("stored context has no secret key")

            except Exception as exc:
                raise RuntimeError(
                    f"Cannot load private HE context at {path}: "
                    "the stored context is invalid or incompatible"
                ) from exc

            holder = cls(
                ctx,
                params,
                os.path.getmtime(path),
                context_id=context_id,
            )
            return holder, False

        holder, raw = cls.create(params)
        payload = _pack_context(holder.context_id, raw)
        sealed = keys.wrap_he_context(payload)

        _atomic_write(path, sealed)
        return holder, True

    # ---- crypto ------------------------------------------------------------

    def public_context_bytes(self) -> bytes:
        """Return the public-only context serialization."""
        return self._public_bytes

    def pad(self, vec: Sequence[float]) -> List[float]:
        n = next_pow2(len(vec))

        if n > self.params.slots:
            raise ValueError(
                f"vector of {len(vec)} dims does not fit "
                f"{self.params.slots} CKKS slots"
            )

        out = [float(x) for x in vec]
        out.extend([0.0] * (n - len(out)))
        return out

    def encrypt(self, vec: Sequence[float]) -> bytes:
        started = time.perf_counter()

        ciphertext = ts.ckks_vector(
            self._ctx,
            self.pad(vec),
        ).serialize()

        self.stats.encryptions += 1
        self.stats.seconds_encrypt += time.perf_counter() - started
        return ciphertext

    def decrypt_vector(self, ct_bytes: bytes) -> List[float]:
        started = time.perf_counter()

        result = ts.ckks_vector_from(
            self._ctx,
            ct_bytes,
        ).decrypt()

        self.stats.decryptions += 1
        self.stats.seconds_decrypt += time.perf_counter() - started
        return result

    def decrypt_scores(
        self,
        encrypted_scores: Iterable["ts.CKKSVector"],
    ) -> List[float]:
        """Decrypt evaluator outputs using the private key."""
        started = time.perf_counter()
        secret_key = self._ctx.secret_key()

        result = [
            float(ciphertext.decrypt(secret_key)[0])
            for ciphertext in encrypted_scores
        ]

        self.stats.decryptions += len(result)
        self.stats.seconds_decrypt += time.perf_counter() - started
        return result


class HEEvaluator:
    """Evaluates ciphertexts using a public context without decryption."""

    def __init__(
        self,
        public_context_bytes: bytes,
        n_threads: int = 1,
    ):
        _require_tenseal()

        self._ctx = ts.context_from(
            public_context_bytes,
            n_threads=n_threads,
        )

        if self._ctx.is_private():
            raise ValueError("evaluator must not receive a secret key")

        self.stats = HEStats()

    def load(self, ct_bytes: bytes) -> "ts.CKKSVector":
        return ts.ckks_vector_from(self._ctx, ct_bytes)

    def dot_many(
        self,
        enc_query_bytes: bytes,
        enc_docs: Sequence["ts.CKKSVector"],
    ) -> List["ts.CKKSVector"]:
        """Return encrypted dot products without decrypting any input."""
        started = time.perf_counter()

        query = self.load(enc_query_bytes)
        result = [document.dot(query) for document in enc_docs]

        self.stats.dot_products += len(result)
        self.stats.seconds_eval += time.perf_counter() - started
        return result


def _atomic_write(path: str, data: bytes) -> None:
    """Atomically persist bytes with owner-only permissions."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    fd, temporary_path = tempfile.mkstemp(
        dir=directory,
        prefix=".he_ctx_",
    )

    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)

    except BaseException:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise
