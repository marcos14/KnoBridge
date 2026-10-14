"""The public key ``kbp_`` of a widget and its signing secret ``kbs_`` (``docs/specs/widget.md``).

The public key is not a secret: it goes in the host page and in the paths of the public
routes, so it is stored in clear. The signing secret is shown once and kept as AES-256-GCM
ciphertext (``docs/adr/0003-segredos-cifrados.md``) under a data key derived only for this
purpose and bound to its widget by associated data, so a ciphertext copied to another widget or
workspace does not decrypt. The server reads it back only to verify a signed identity (F3.2).
"""

from __future__ import annotations

import re
import secrets
import string

from knobridge.core.crypto import SecretBox
from knobridge.widget.models import Widget

PUBLIC_KEY_PREFIX = "kbp_"
PUBLIC_KEY_RANDOM_LENGTH = 24
PUBLIC_KEY_PATTERN = re.compile(r"^kbp_[a-z0-9]{24}$")
SIGNING_SECRET_PREFIX = "kbs_"  # noqa: S105 - the public prefix, not a secret
SIGNING_SECRET_PATTERN = re.compile(r"^kbs_[A-Za-z0-9_-]{43}$")
# HKDF label of the data key; a new label (v2) means a new key, never reuse this one.
SIGNING_SECRET_KEY_INFO = b"knobridge/widget-signing-secrets/v1"

_PUBLIC_KEY_ALPHABET = string.ascii_lowercase + string.digits


def generate_public_key() -> str:
    """A new ``kbp_<24 of [a-z0-9]>`` (about 124 bits; unique in the instance by constraint)."""
    suffix = "".join(secrets.choice(_PUBLIC_KEY_ALPHABET) for _ in range(PUBLIC_KEY_RANDOM_LENGTH))
    return PUBLIC_KEY_PREFIX + suffix


def is_public_key(value: str) -> bool:
    return PUBLIC_KEY_PATTERN.fullmatch(value) is not None


def generate_signing_secret() -> str:
    """A new ``kbs_<token_urlsafe(32)>`` (43 characters after the prefix)."""
    return SIGNING_SECRET_PREFIX + secrets.token_urlsafe(32)


def _associated_data(widget: Widget) -> bytes:
    return f"widget_signing_secret:{widget.workspace_id}:{widget.id}".encode()


def seal_signing_secret(box: SecretBox, widget: Widget, secret: str) -> str:
    """The ciphertext to store in ``widgets.signing_secret_ciphertext``."""
    return box.encrypt(secret, associated_data=_associated_data(widget))


def open_signing_secret(box: SecretBox, widget: Widget) -> str | None:
    """The secret in clear, only to verify an identity; ``None`` when there is none.

    Raises ``DecryptionError`` for a ciphertext of another key, purpose or widget.
    """
    if widget.signing_secret_ciphertext is None:
        return None
    return box.decrypt(widget.signing_secret_ciphertext, associated_data=_associated_data(widget))
