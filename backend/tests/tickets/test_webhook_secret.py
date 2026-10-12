"""Encryption of the ticket webhook secret bound to its assistant (unit tests, no database)."""

from __future__ import annotations

import uuid

import pytest

from knobridge.assistants.models import Assistant
from knobridge.core.crypto import DecryptionError, SecretBox
from knobridge.llm.credentials import CREDENTIALS_KEY_INFO
from knobridge.tickets.webhook_secret import (
    TICKET_WEBHOOK_KEY_INFO,
    open_webhook_secret,
    seal_webhook_secret,
)

ROOT = "test-secret-key-for-ticket-webhooks-0123456789"  # synthetic
SECRET = "kbw_" + "a" * 43  # synthetic


def _box(info: bytes = TICKET_WEBHOOK_KEY_INFO) -> SecretBox:
    return SecretBox.derive(ROOT, info=info)


def _assistant(workspace_id: uuid.UUID | None = None) -> Assistant:
    return Assistant(id=uuid.uuid4(), workspace_id=workspace_id or uuid.uuid4())


def test_webhook_secret_round_trip() -> None:
    assistant = _assistant()
    ciphertext = seal_webhook_secret(_box(), assistant, SECRET)
    assistant.ticket_webhook_secret_ciphertext = ciphertext

    assert SECRET not in ciphertext
    assert open_webhook_secret(_box(), assistant) == SECRET


def test_webhook_secret_absent_opens_as_none() -> None:
    assert open_webhook_secret(_box(), _assistant()) is None


def test_webhook_secret_bound_to_its_assistant() -> None:
    owner = _assistant()
    other = _assistant(owner.workspace_id)
    other.ticket_webhook_secret_ciphertext = seal_webhook_secret(_box(), owner, SECRET)

    with pytest.raises(DecryptionError):
        open_webhook_secret(_box(), other)


def test_webhook_secret_key_differs_from_provider_credentials() -> None:
    assistant = _assistant()
    assistant.ticket_webhook_secret_ciphertext = seal_webhook_secret(_box(), assistant, SECRET)

    with pytest.raises(DecryptionError):
        open_webhook_secret(_box(CREDENTIALS_KEY_INFO), assistant)
