"""AES-GCM secret box with HKDF-derived keys (``knobridge.core.crypto``)."""

from __future__ import annotations

import base64

import pytest

from knobridge.core.crypto import KEY_BYTES, DecryptionError, SecretBox, derive_key

SECRET = "a-test-secret-key-with-at-least-32-chars"  # noqa: S105 - test value
OTHER_SECRET = "another-secret-key-with-at-least-32-chars"  # noqa: S105 - test value
INFO = b"knobridge/test/v1"
AD = b"workspace:1:record:2"


def _box(secret: str = SECRET, info: bytes = INFO) -> SecretBox:
    return SecretBox.derive(secret, info=info)


def test_encrypt_decrypt_roundtrip() -> None:
    box = _box()

    ciphertext = box.encrypt("sk-live-ação-1234", associated_data=AD)

    assert box.decrypt(ciphertext, associated_data=AD) == "sk-live-ação-1234"


def test_ciphertext_differs_each_time() -> None:
    box = _box()

    first = box.encrypt("same key", associated_data=AD)
    second = box.encrypt("same key", associated_data=AD)

    assert first != second
    assert "same key" not in first


def test_ciphertext_carries_key_version() -> None:
    ciphertext = _box().encrypt("value", associated_data=AD)

    assert ciphertext.startswith("v1.")


def test_wrong_key_fails() -> None:
    ciphertext = _box().encrypt("value", associated_data=AD)

    with pytest.raises(DecryptionError):
        _box(secret=OTHER_SECRET).decrypt(ciphertext, associated_data=AD)


def test_key_from_other_purpose_fails() -> None:
    ciphertext = _box().encrypt("value", associated_data=AD)

    with pytest.raises(DecryptionError):
        _box(info=b"knobridge/other/v1").decrypt(ciphertext, associated_data=AD)


def test_wrong_associated_data_fails() -> None:
    box = _box()
    ciphertext = box.encrypt("value", associated_data=AD)

    with pytest.raises(DecryptionError):
        box.decrypt(ciphertext, associated_data=b"workspace:9:record:2")


def test_tampered_ciphertext_fails() -> None:
    box = _box()
    ciphertext = box.encrypt("value", associated_data=AD)
    raw = bytearray(base64.urlsafe_b64decode(ciphertext[3:]))
    raw[-1] ^= 0x01
    tampered = "v1." + base64.urlsafe_b64encode(bytes(raw)).decode()

    with pytest.raises(DecryptionError, match="authenticate"):
        box.decrypt(tampered, associated_data=AD)


def test_unknown_key_version_fails() -> None:
    ciphertext = _box().encrypt("value", associated_data=AD)
    other_version = SecretBox(derive_key(SECRET, info=INFO), version=2)

    with pytest.raises(DecryptionError, match="version"):
        other_version.decrypt(ciphertext, associated_data=AD)


@pytest.mark.parametrize("payload", ["v1.abc", "v1.ação", "v1." + "A" * 8])
def test_malformed_ciphertext_fails(payload: str) -> None:
    with pytest.raises(DecryptionError, match="Malformed"):
        _box().decrypt(payload, associated_data=AD)


def test_derive_key_is_deterministic_per_purpose() -> None:
    key = derive_key(SECRET, info=INFO)

    assert len(key) == KEY_BYTES
    assert key == derive_key(SECRET, info=INFO)
    assert key != derive_key(SECRET, info=b"knobridge/other/v1")
