"""The ticket tables resolve every foreign key with only their own module imported.

The worker loads ``knobridge.tickets.models`` without the chat models; when ``ticket_requests``
pointed at ``messages`` and ``conversations`` that nobody had imported, the first flush of a
delivery failed with ``NoReferencedTableError``. A fresh interpreter is the only way to see it:
in this test session every model is already imported.
"""

from __future__ import annotations

import subprocess
import sys

CHECK = """
from knobridge.tickets.models import IngestToken, TicketInboxItem, TicketRequest

for model in (IngestToken, TicketInboxItem, TicketRequest):
    for foreign_key in model.__table__.foreign_keys:
        foreign_key.column  # raises NoReferencedTableError when the target is not loaded
"""


def test_ticket_tables_resolve_foreign_keys_on_their_own() -> None:
    result = subprocess.run(  # noqa: S603 - this interpreter, fixed code
        [sys.executable, "-c", CHECK], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
