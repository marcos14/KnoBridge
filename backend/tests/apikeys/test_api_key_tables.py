"""The key model and the conversation writer resolve every foreign key on their own.

``conversations`` points at ``api_keys`` by table name and ``conversations/`` does not import
``apikeys/``; the API module that writes conversations loads ``ApiKey``. A fresh interpreter is
the only way to see a missing table: in this test session every model is already imported.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

API_KEY_ALONE = """
from knobridge.apikeys.models import ApiKey

for foreign_key in ApiKey.__table__.foreign_keys:
    foreign_key.column  # raises NoReferencedTableError when the target is not loaded
"""

CONVERSATION_WRITER = """
import knobridge.api.conversations
from knobridge.conversations.models import Conversation

for foreign_key in Conversation.__table__.foreign_keys:
    foreign_key.column
"""


@pytest.mark.parametrize("code", [API_KEY_ALONE, CONVERSATION_WRITER])
def test_tables_resolve_foreign_keys_in_a_fresh_interpreter(code: str) -> None:
    result = subprocess.run(  # noqa: S603 - this interpreter, fixed code
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
