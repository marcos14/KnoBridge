from __future__ import annotations

import copy
from pathlib import Path

import pytest

from eval.matching import Citation, glob_matches, matcher_problem, matches, normalize
from eval.questions import QuestionsError, load_questions, parse_questions

VALID: dict[str, object] = {
    "version": 1,
    "level_rules": {
        "end_user": {"forbidden": ["ticket:*"]},
        "support": {"forbidden": []},
        "product_dev": {"forbidden": []},
    },
    "questions": [
        {
            "id": "eu-01",
            "level": "end_user",
            "kind": "how_to",
            "question": "Como faço?",
            "answerable": True,
            "expected_sources": {"any": ["path:manual-*.md"], "all": ["card:EVAL-C-001"]},
            "must_include": [["a", "b"]],
            "must_not_include": ["c"],
        },
        {
            "id": "eu-02",
            "level": "end_user",
            "kind": "unrelated",
            "question": "?",
            "answerable": False,
        },
    ],
}


EMPTY: list[str] = []


def test_parse_questions_reads_every_field() -> None:
    parsed = parse_questions(VALID)

    first, second = parsed.questions
    assert parsed.level_rules["end_user"] == ("ticket:*",)
    assert first.any_sources == ("path:manual-*.md",)
    assert first.all_sources == ("card:EVAL-C-001",)
    assert first.must_include == (("a", "b"),)
    assert first.must_not_include == ("c",)
    assert not first.needs_steps
    assert second.any_sources == ()


def _broken(path: tuple[object, ...], value: object, *, delete: bool = False) -> dict[str, object]:
    data = copy.deepcopy(VALID)
    target: object = data
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    if delete:
        del target[path[-1]]  # type: ignore[index]
    else:
        target[path[-1]] = value  # type: ignore[index]
    return data


@pytest.mark.parametrize(
    ("data", "where"),
    [
        ([], "$"),
        (_broken(("extra",), 1), "$.extra"),
        (_broken(("version",), 2), "$.version"),
        (_broken(("version",), True), "$.version"),
        (_broken(("level_rules", "support"), None, delete=True), "$.level_rules.support"),
        (_broken(("level_rules", "outro"), {"forbidden": []}), "$.level_rules.outro"),
        (_broken(("level_rules", "support", "forbidden"), "x"), "$.level_rules.support.forbidden"),
        (_broken(("level_rules", "support"), []), "$.level_rules.support"),
        (_broken(("level_rules", "support", "forbidden"), ["web:x"]), "forbidden[0]"),
        (_broken(("questions",), []), "$.questions"),
        (_broken(("questions",), {}), "$.questions"),
        (_broken(("questions", 0), "texto"), "$.questions[0]"),
        (_broken(("questions", 0, "id"), "Maiúsculo"), "$.questions[0].id"),
        (_broken(("questions", 1, "id"), "eu-01"), "$.questions[1].id"),
        (_broken(("questions", 0, "level"), "chefe"), "$.questions[0].level"),
        (_broken(("questions", 0, "kind"), "outro"), "$.questions[0].kind"),
        (_broken(("questions", 0, "question"), ""), "$.questions[0].question"),
        (_broken(("questions", 0, "question"), "x" * 2001), "$.questions[0].question"),
        (_broken(("questions", 0, "answerable"), "sim"), "$.questions[0].answerable"),
        (_broken(("questions", 0, "needs_steps"), 1), "$.questions[0].needs_steps"),
        (_broken(("questions", 0, "foo"), 1), "$.questions[0].foo"),
        (_broken(("questions", 0, "expected_sources"), None, delete=True), "expected_sources"),
        (_broken(("questions", 0, "expected_sources"), []), "expected_sources"),
        (_broken(("questions", 0, "expected_sources", "x"), []), "expected_sources.x"),
        (_broken(("questions", 0, "expected_sources", "any"), []), "expected_sources.any"),
        (_broken(("questions", 0, "expected_sources", "any"), ["path:/abs"]), "any[0]"),
        (_broken(("questions", 0, "expected_sources", "all"), ["ticket:"]), "all[0]"),
        (_broken(("questions", 0, "expected_sources", "any"), [3]), "any[0]"),
        (_broken(("questions", 0, "must_include"), "a"), "must_include"),
        (_broken(("questions", 0, "must_include"), [EMPTY]), "must_include[0]"),
        (_broken(("questions", 0, "must_include"), ["a"]), "must_include[0]"),
        (_broken(("questions", 0, "must_not_include"), [""]), "must_not_include[0]"),
    ],
)
def test_parse_questions_rejects_with_the_path(data: object, where: str) -> None:
    with pytest.raises(QuestionsError) as raised:
        parse_questions(data)

    assert where in raised.value.path


def test_parse_questions_accepts_unanswerable_with_sources() -> None:
    data = _broken(("questions", 1, "expected_sources"), {"any": []})

    assert parse_questions(data).questions[1].any_sources == ()


def test_load_questions_reports_missing_and_invalid_files(tmp_path: Path) -> None:
    broken = tmp_path / "q.json"
    broken.write_text("{", encoding="utf-8")

    with pytest.raises(QuestionsError, match="cannot read"):
        load_questions(tmp_path / "nao-existe.json")
    with pytest.raises(QuestionsError, match="invalid JSON"):
        load_questions(broken)


def test_normalize_lowercases_strips_accents_and_spaces() -> None:
    assert normalize("  Liberação   de\nCRÉDITO ") == "liberacao de credito"


@pytest.mark.parametrize(
    ("glob", "path", "expected"),
    [
        ("interno-*", "interno-esquema-do-banco.md", True),
        ("interno-*", "sub/interno-a.md", False),
        ("src/**", "src/credito/exposicao.ts", True),
        ("**/exposicao.ts", "exposicao.ts", True),
        ("**/exposicao.ts", "src/credito/exposicao.ts", True),
        ("src/*.ts", "src/credito/exposicao.ts", False),
        ("manual-a.md", "manual-a.md", True),
        ("manual-a.md", "manual-aXmd", False),
    ],
)
def test_glob_matches_segments_and_depth(glob: str, path: str, expected: bool) -> None:
    assert glob_matches(glob, path) is expected


@pytest.mark.parametrize(
    ("matcher", "citation", "expected"),
    [
        ("path:manual-*", Citation(1, "file", "manual-a.md#L1-L2", "manual-a.md"), True),
        ("path:manual-*", Citation(1, "ticket", "ticket:A", None), False),
        ("ticket:*", Citation(1, "ticket", "ticket:EVAL-T-001", None), True),
        ("ticket:EVAL-T-001", Citation(1, "ticket", "ticket:EVAL-T-001", None), True),
        ("ticket:EVAL-T-002", Citation(1, "ticket", "ticket:EVAL-T-001", None), False),
        ("ticket:*", Citation(1, "card", "card:EVAL-C-001", None), False),
        ("card:*", Citation(1, "card", None, None), False),
        ("card:*", Citation(1, "card", "outro", None), False),
    ],
)
def test_matches_by_kind_and_uri(matcher: str, citation: Citation, expected: bool) -> None:
    assert matches(matcher, citation) is expected


@pytest.mark.parametrize(
    ("matcher", "problem"),
    [
        ("path:src/**", None),
        ("ticket:*", None),
        ("card:EVAL-C-001", None),
        ("semprefixo", "expected path"),
        ("web:x", "unknown matcher prefix"),
        ("path:", "relative glob"),
        ("card:", "external_id"),
    ],
)
def test_matcher_problem_explains_invalid_matchers(matcher: str, problem: str | None) -> None:
    found = matcher_problem(matcher)

    assert found == problem if problem is None else problem in str(found)
