"""Encryption at rest of the ticket webhook signing secret of a product.

The server signs every delivery with the ``kbw_`` secret, so it must read it back: it is kept
as AES-256-GCM ciphertext (``docs/adr/0003-segredos-cifrados.md``) under a data key derived only
for this purpose (``TICKET_WEBHOOK_KEY_INFO``) and bound to its product by associated data,
so a ciphertext copied to another product or workspace does not decrypt.
"""

from __future__ import annotations

from knobridge.core.crypto import SecretBox
from knobridge.products.models import Product

# HKDF label of the data key; a new label (v2) means a new key, never reuse this one.
TICKET_WEBHOOK_KEY_INFO = b"knobridge/ticket-webhook-secrets/v1"


def _associated_data(product: Product) -> bytes:
    # Still ``assistant_``: migration 0018 kept the ids, so the stored ciphertexts still open.
    return f"assistant_ticket_webhook:{product.workspace_id}:{product.id}".encode()


def seal_webhook_secret(box: SecretBox, product: Product, secret: str) -> str:
    """The ciphertext to store in ``products.ticket_webhook_secret_ciphertext``."""
    return box.encrypt(secret, associated_data=_associated_data(product))


def open_webhook_secret(box: SecretBox, product: Product) -> str | None:
    """The secret in clear, only to sign a delivery; ``None`` when none was generated.

    Raises ``DecryptionError`` for a ciphertext of another key, purpose or product.
    """
    if product.ticket_webhook_secret_ciphertext is None:
        return None
    return box.decrypt(
        product.ticket_webhook_secret_ciphertext, associated_data=_associated_data(product)
    )
