"""Authenticated encryption of secrets at rest (AES-256-GCM).

Each kind of secret gets its own data key, derived from ``KNOBRIDGE_SECRET_KEY`` with HKDF
and a purpose-specific ``info`` label, so the CSRF HMAC key and every data key stay
independent even though they share one root secret.

Ciphertext text format: ``v<key version>.<base64url(nonce || ciphertext || tag)>``. The key
version lets a future rotation decrypt old rows with the previous key while new rows use the
current one. ``associated_data`` binds a ciphertext to its row (e.g. workspace and record
ids): moved to another row, it fails authentication instead of decrypting.
See docs/adr/0003-segredos-cifrados.md.
"""

from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

KEY_BYTES = 32  # AES-256
NONCE_BYTES = 12  # the GCM standard nonce size
CURRENT_KEY_VERSION = 1
# Fixed, public salt: HKDF only needs it to be constant; the secret is the root key.
_HKDF_SALT = b"knobridge/hkdf/v1"


class DecryptionError(Exception):
    """The ciphertext is malformed, from another key or row, or was tampered with."""


def derive_key(secret: str, *, info: bytes) -> bytes:
    """A 256-bit key derived from ``secret`` (HKDF-SHA256) for the purpose named by ``info``."""
    hkdf = HKDF(algorithm=hashes.SHA256(), length=KEY_BYTES, salt=_HKDF_SALT, info=info)
    return hkdf.derive(secret.encode("utf-8"))


class SecretBox:
    """Encrypts and decrypts text with one AES-GCM key tagged with its version."""

    def __init__(self, key: bytes, *, version: int = CURRENT_KEY_VERSION) -> None:
        self._aead = AESGCM(key)
        self._prefix = f"v{version}."

    @classmethod
    def derive(cls, secret: str, *, info: bytes) -> SecretBox:
        return cls(derive_key(secret, info=info))

    def encrypt(self, plaintext: str, *, associated_data: bytes) -> str:
        """Ciphertext text; a fresh random nonce each call, so equal inputs never match."""
        nonce = os.urandom(NONCE_BYTES)
        sealed = self._aead.encrypt(nonce, plaintext.encode("utf-8"), associated_data)
        return self._prefix + base64.urlsafe_b64encode(nonce + sealed).decode("ascii")

    def decrypt(self, ciphertext: str, *, associated_data: bytes) -> str:
        """The plaintext, or ``DecryptionError`` for anything that does not authenticate."""
        if not ciphertext.startswith(self._prefix):
            raise DecryptionError("Unknown key version.")
        try:
            raw = base64.urlsafe_b64decode(ciphertext[len(self._prefix) :].encode("ascii"))
        except (binascii.Error, UnicodeEncodeError) as exc:
            raise DecryptionError("Malformed ciphertext.") from exc
        nonce, sealed = raw[:NONCE_BYTES], raw[NONCE_BYTES:]
        if len(nonce) < NONCE_BYTES:
            raise DecryptionError("Malformed ciphertext.")
        try:
            plaintext = self._aead.decrypt(nonce, sealed, associated_data)
        except InvalidTag as exc:
            raise DecryptionError("Ciphertext does not authenticate.") from exc
        return plaintext.decode("utf-8")
