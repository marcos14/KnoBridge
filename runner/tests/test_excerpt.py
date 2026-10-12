from __future__ import annotations

import pytest

from knobridge_runner.excerpt import (
    REDACTED,
    cut,
    is_sensitive_file,
    make_excerpt,
    redact,
)

# Secrets are assembled at run time so the secret scanner never sees them in the source.
AWS = "AKIA" + "Q" * 16
GITHUB = "ghp" + "_" + "a" * 36
OPENAI = "sk-" + "proj-" + "b" * 24
SLACK = "xoxb" + "-" + "1" * 12
GOOGLE = "AIza" + "c" * 35
RUNNER = "kbr" + "_abcd1234_" + "D" * 43
JWT = "eyJ" + "e" * 12 + "." + "f" * 12 + "." + "g" * 12
PRIVATE_KEY = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nzzzz\n-----END RSA PRIVATE KEY-----"


def numbered(count: int) -> list[str]:
    return [f"line {index}" for index in range(1, count + 1)]


@pytest.mark.parametrize("secret", [AWS, GITHUB, OPENAI, SLACK, GOOGLE, RUNNER, JWT])
def test_redact_replaces_whole_token(secret: str) -> None:
    text, count = redact(f"value = call({secret!r})")

    assert secret not in text
    assert REDACTED in text
    assert count == 1


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('password = "hunter22"', f'password = "{REDACTED}"'),
        ("DB_PASSWD: s3cr3t!", f"DB_PASSWD: {REDACTED}"),
        ("client-secret=abcd", f"client-secret={REDACTED}"),
        ('"apiKey": "zzzz9"', f'"apiKey": "{REDACTED}"'),
        ("postgres://app:pa55word@db:5432/x", f"postgres://app:{REDACTED}@db:5432/x"),
    ],
)
def test_redact_replaces_only_the_value(line: str, expected: str) -> None:
    assert redact(line) == (expected, 1)


def test_redact_counts_a_token_inside_an_assignment_once() -> None:
    text, count = redact(f'api_key = "{OPENAI}"')

    assert text == f'api_key = "{REDACTED}"'
    assert count == 1


def test_redact_removes_private_key_block_even_without_end() -> None:
    whole, count = redact(f"before\n{PRIVATE_KEY}\nafter")
    open_ended, _ = redact("x\n-----BEGIN PRIVATE KEY-----\nMIIE\nrest")

    assert whole == f"before\n{REDACTED}\nafter"
    assert count == 1
    assert open_ended == f"x\n{REDACTED}"


def test_redact_keeps_short_values_and_plain_text() -> None:
    assert redact("token = 12; max_items = 5") == ("token = 12; max_items = 5", 0)


def test_cut_adds_ellipsis_only_when_needed() -> None:
    assert cut("abc", 3) == "abc"
    assert cut("abcd", 3) == "ab…"


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "app/.env.production",
        "certs/server.PEM",
        "keys/deploy.key",
        "store.p12",
        "a.pfx",
        "b.jks",
        "c.keystore",
        "home/id_rsa",
        "id_ed25519.pub",
        ".npmrc",
        ".pypirc",
        ".netrc",
        ".git-credentials",
        "config/credentials.json",
        "config/secrets.yaml",
    ],
)
def test_sensitive_file_names(path: str) -> None:
    assert is_sensitive_file(path)


@pytest.mark.parametrize(
    "path", [".env.example", ".env.sample", ".env.template", "src/env.py", "keys.md"]
)
def test_regular_file_names(path: str) -> None:
    assert not is_sensitive_file(path)


def test_sensitive_files_never_excerpted() -> None:
    excerpt = make_excerpt("deploy/.env", ["TOKEN=abc"], 1, 1, 30)

    assert excerpt.text is None
    assert excerpt.omitted == "sensitive_file"
    assert excerpt.redactions == 0


def test_excerpt_disabled_with_zero_lines() -> None:
    excerpt = make_excerpt("src/a.py", ["x"], 1, 1, 0)

    assert (excerpt.text, excerpt.omitted) == (None, "disabled")


def test_excerpt_truncated_to_limit() -> None:
    excerpt = make_excerpt("src/a.py", numbered(100), 10, 50, 5)

    assert excerpt.text == "\n".join(f"line {index}" for index in range(10, 15))
    assert excerpt.truncated
    assert excerpt.omitted is None


def test_excerpt_within_limit_is_not_truncated() -> None:
    excerpt = make_excerpt("src/a.py", numbered(10), 2, 3, 30)

    assert excerpt.text == "line 2\nline 3"
    assert not excerpt.truncated


def test_excerpt_cuts_long_lines() -> None:
    excerpt = make_excerpt("src/a.py", ["x" * 500], 1, 1, 30)

    assert excerpt.text == "x" * 399 + "…"
    assert excerpt.truncated


def test_excerpt_cuts_total_to_8_kib() -> None:
    lines = ["é" * 300 for _ in range(30)]

    excerpt = make_excerpt("src/a.py", lines, 1, 30, 30)

    assert excerpt.text is not None
    assert len(excerpt.text.encode("utf-8")) <= 8 * 1024
    assert excerpt.text.endswith("…")
    assert excerpt.truncated


def test_excerpt_redacts_secrets() -> None:
    lines = ["def connect():", f'    password = "{RUNNER}"', f"    key = {AWS!r}"]

    excerpt = make_excerpt("src/db.py", lines, 1, 3, 30)

    assert excerpt.text is not None
    assert RUNNER not in excerpt.text
    assert AWS not in excerpt.text
    assert excerpt.text.count(REDACTED) == 2
    assert excerpt.redactions == 2
