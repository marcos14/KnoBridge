import re
from pathlib import Path

import pytest

from knobridge.levels.defaults import DEFAULT_INSTRUCTIONS
from knobridge.levels.level import ResponseLevel

SPEC = Path(__file__).resolve().parents[3] / "docs" / "specs" / "produtos-e-niveis.md"


def _spec_text(level: ResponseLevel) -> str:
    spec = SPEC.read_text(encoding="utf-8")
    found = re.search(rf"\*\*`{level.value}` \([^)]*\)\*\*:\n\n```text\n(.*?)\n```", spec, re.S)
    assert found is not None, level
    return found.group(1)


@pytest.mark.parametrize("level", list(ResponseLevel))
def test_default_instructions_match_the_spec_word_for_word(level: ResponseLevel) -> None:
    assert DEFAULT_INSTRUCTIONS[level] == _spec_text(level)


def test_default_instructions_keep_planning_out_of_end_user() -> None:
    # The F4.2 rehearsal of plan 0009 saw a small end-user model plan a feature on request.
    assert "Planejar funcionalidades novas" in DEFAULT_INSTRUCTIONS[ResponseLevel.END_USER]
