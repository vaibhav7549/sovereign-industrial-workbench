"""Key management for the sovereign encryption layer.

One root secret (ENCRYPTION_MASTER_KEY, a Fernet-format key) is held only in the
backend's environment. Every purpose-specific key is derived from it with
HKDF-SHA256 and a distinct `info` label, so a key used for one job can never be
replayed for another (domain separation):

    text      AES-256-GCM key for chunk text / titles sent to Atomic
    he-wrap   AES-256-GCM key that wraps the CKKS secret context on disk
    vault-mac HMAC-SHA256 key that authenticates CKKS ciphertexts in the vault
    audit     HMAC-SHA256 key for the tamper-evident audit chain and query fingerprints

AES-GCM is used instead of raw Fernet because it supports associated data:
every ciphertext is bound to *where* it belongs (doc id, chunk index, purpose),
so a hostile storage server cannot swap one chunk's ciphertext for another's
without the swap being detected on decryption.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_HKDF_SALT = b"sovereign-workbench/encryption/v1"
_NONCE_BYTES = 12
_TEXT_PAD_BLOCK = 256  # pad plaintext to a multiple of this to blur exact lengths


class KeyConfigurationError(RuntimeError):
    """Raised when the master key is missing or malformed (fail closed)."""


def generate_master_key() -> str:
    """Return a new master key in Fernet format (urlsafe base64 of 32 random bytes)."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def _decode_master_key(raw: str | None) -> bytes:
    if not raw or raw.strip() in {"", "${ENCRYPTION_MASTER_KEY}", "changeme"}:
        raise KeyConfigurationError(
            "ENCRYPTION_MASTER_KEY is not set. Generate one with:\n"
            "  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"\n"
            "and provide it to the backend through the environment (never commit it)."
        )
    try:
        key = base64.urlsafe_b64decode(raw.strip().encode())
    except Exception as exc:  # pragma: no cover - defensive
        raise KeyConfigurationError("ENCRYPTION_MASTER_KEY is not valid urlsafe base64") from exc
    if len(key) != 32:
        raise KeyConfigurationError(
            f"ENCRYPTION_MASTER_KEY must decode to 32 bytes (got {len(key)}); use a Fernet key"
        )
    return key


def _hkdf(root: bytes, label: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=_HKDF_SALT, info=label.encode()).derive(root)


@dataclass(frozen=True)
class KeyRing:
    text_key: bytes
    he_wrap_key: bytes
    vault_mac_key: bytes
    audit_key: bytes
    key_id: str  # public, non-secret fingerprint so operators can tell keys apart

    # ----- construction ---------------------------------------------------
    @classmethod
    def from_master_key(cls, raw: str | None) -> "KeyRing":
        root = _decode_master_key(raw)
        return cls(
            text_key=_hkdf(root, "text"),
            he_wrap_key=_hkdf(root, "he-wrap"),
            vault_mac_key=_hkdf(root, "vault-mac"),
            audit_key=_hkdf(root, "audit"),
            key_id=hashlib.sha256(_hkdf(root, "key-id")).hexdigest()[:16],
        )

    @classmethod
    def from_env(cls) -> "KeyRing":
        return cls.from_master_key(os.getenv("ENCRYPTION_MASTER_KEY"))

    # ----- authenticated encryption ----------------------------------------
    @staticmethod
    def _seal(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
        nonce = os.urandom(_NONCE_BYTES)
        return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)

    @staticmethod
    def _open(key: bytes, blob: bytes, aad: bytes) -> bytes:
        return AESGCM(key).decrypt(blob[:_NONCE_BYTES], blob[_NONCE_BYTES:], aad)

    def encrypt_text(self, text: str, aad: str) -> str:
        """Encrypt text bound to `aad`; returns urlsafe base64. Length is padded to 256-byte buckets."""
        data = text.encode("utf-8")
        pad = (-(len(data) + 4)) % _TEXT_PAD_BLOCK
        framed = len(data).to_bytes(4, "big") + data + b"\x00" * pad
        return base64.urlsafe_b64encode(self._seal(self.text_key, framed, aad.encode())).decode()

    def decrypt_text(self, token: str, aad: str) -> str:
        framed = self._open(self.text_key, base64.urlsafe_b64decode(token.encode()), aad.encode())
        n = int.from_bytes(framed[:4], "big")
        return framed[4 : 4 + n].decode("utf-8")

    def wrap_he_context(self, serialized: bytes) -> bytes:
        return self._seal(self.he_wrap_key, serialized, b"he-context/v1")

    def unwrap_he_context(self, blob: bytes) -> bytes:
        return self._open(self.he_wrap_key, blob, b"he-context/v1")

    # ----- MACs ------------------------------------------------------------
    def vault_mac(self, ciphertext: bytes, binding: str) -> str:
        return hmac.new(self.vault_mac_key, binding.encode() + b"\x00" + ciphertext, hashlib.sha256).hexdigest()

    def audit_mac(self, data: bytes) -> str:
        return hmac.new(self.audit_key, data, hashlib.sha256).hexdigest()

    def fingerprint(self, text: str) -> str:
        """Keyed, non-reversible fingerprint (lets auditors with the key match a query; nobody else can)."""
        return hmac.new(self.audit_key, b"fp\x00" + text.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
