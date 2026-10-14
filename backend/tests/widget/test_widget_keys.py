"""Public key ``kbp_`` and signing secret ``kbs_`` of a widget: formats, randomness and the
ciphertext bound to its widget (unit tests, no database)."""

from __future__ import annotations

import uuid

import pytest

from knobridge.core.crypto import DecryptionError, SecretBox
from knobridge.widget.keys import (
    PUBLIC_KEY_PATTERN,
    SIGNING_SECRET_KEY_INFO,
    SIGNING_SECRET_PATTERN,
    generate_public_key,
    generate_signing_secret,
    is_public_key,
    open_signing_secret,
    seal_signing_secret,
)
from knobridge.widget.models import Widget

SECRET = "a-test-root-secret-with-at-least-32-chars"  # noqa: S105 - test value


def _widget(workspace_id: uuid.UUID | None = None) -> Widget:
    return Widget(id=uuid.uuid4(), workspace_id=workspace_id or uuid.uuid4())


def test_generate_public_key_format_and_randomness() -> None:
    keys = {generate_public_key() for _ in range(50)}

    assert len(keys) == 50
    assert all(PUBLIC_KEY_PATTERN.fullmatch(key) for key in keys)


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("kbp_3k9x2m4q7w8e1r5t6y0u2i4o", True),
        ("kbp_3K9X2M4Q7W8E1R5T6Y0U2I4O", False),
        ("kbp_short", False),
        ("kbk_3k9x2m4q7w8e1r5t6y0u2i4o", False),
        ("kbp_3k9x2m4q7w8e1r5t6y0u2i4o/", False),
    ],
)
def test_is_public_key(value: str, valid: bool) -> None:
    assert is_public_key(value) is valid


def test_generate_signing_secret_format() -> None:
    secret = generate_signing_secret()

    assert SIGNING_SECRET_PATTERN.fullmatch(secret)
    assert secret != generate_signing_secret()


def test_signing_secret_sealed_and_opened_for_its_widget() -> None:
    box = SecretBox.derive(SECRET, info=SIGNING_SECRET_KEY_INFO)
    widget = _widget()
    secret = generate_signing_secret()

    sealed = seal_signing_secret(box, widget, secret)
    widget.signing_secret_ciphertext = sealed

    assert secret not in sealed
    assert open_signing_secret(box, widget) == secret


def test_signing_secret_of_another_widget_does_not_open() -> None:
    box = SecretBox.derive(SECRET, info=SIGNING_SECRET_KEY_INFO)
    owner, other = _widget(), _widget()
    other.signing_secret_ciphertext = seal_signing_secret(box, owner, generate_signing_secret())

    with pytest.raises(DecryptionError):
        open_signing_secret(box, other)


def test_open_signing_secret_without_secret_is_none() -> None:
    box = SecretBox.derive(SECRET, info=SIGNING_SECRET_KEY_INFO)

    assert open_signing_secret(box, _widget()) is None
