"""Reading an uploaded file of tickets: the format by extension, JSONL line by line and JSON
decoded one element at a time, without loading the file whole."""

from __future__ import annotations

import io
import json

import pytest

from knobridge.tickets import upload_files
from knobridge.tickets.upload_files import (
    INVALID_LINE,
    UploadEmptyError,
    UploadFormatUnsupportedError,
    UploadInvalidJsonError,
    count_json_elements,
    json_elements,
    jsonl_elements,
    upload_format,
)


class TrackedFile(io.BytesIO):
    """A file that remembers the furthest byte read."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.furthest = 0

    def read(self, size: int | None = -1, /) -> bytes:
        chunk = super().read(size)
        self.furthest = max(self.furthest, self.tell())
        return chunk


def _json(data: str | bytes) -> list[tuple[int, object]]:
    raw = data.encode() if isinstance(data, str) else data
    return list(json_elements(io.BytesIO(raw)))


@pytest.fixture
def tiny_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upload_files, "CHUNK_CHARS", 1)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [("tickets.json", "json"), ("export.JSONL", "jsonl"), ("dir/a.b.Json", "json")],
)
def test_upload_format_by_extension(filename: str, expected: str) -> None:
    assert upload_format(filename) == expected


@pytest.mark.parametrize("filename", ["tickets.csv", "tickets", None, "json"])
def test_upload_format_refuses_other_extensions(filename: str | None) -> None:
    with pytest.raises(UploadFormatUnsupportedError) as caught:
        upload_format(filename)

    assert caught.value.code == "upload_format_unsupported"
    assert caught.value.status_code == 422
    assert caught.value.details == {"filename": filename}


def test_jsonl_elements_numbers_lines_and_skips_blank_ones() -> None:
    data = b'\xef\xbb\xbf{"a": 1}\n\n   \r\n{"b": 2}\r\nnot json\n[1]\n\xff\xfe\n'

    elements = list(jsonl_elements(io.BytesIO(data)))

    assert elements == [
        (1, {"a": 1}),
        (4, {"b": 2}),
        (5, INVALID_LINE),
        (6, [1]),
        (7, INVALID_LINE),
    ]


def test_jsonl_elements_without_trailing_newline() -> None:
    assert list(jsonl_elements(io.BytesIO(b'{"a": 1}'))) == [(1, {"a": 1})]


def test_json_elements_reads_a_list() -> None:
    assert _json(' [ {"a": 1}, 2 , "x", null ] \n') == [(0, {"a": 1}), (1, 2), (2, "x"), (3, None)]


def test_json_elements_reads_the_items_object() -> None:
    assert _json('{"items": [{"a": 1}, {"b": 2}]}') == [(0, {"a": 1}), (1, {"b": 2})]


def test_json_elements_empty_list_and_items() -> None:
    assert _json("[]") == []
    assert _json('{ "items" : [ ] }') == []


def test_json_elements_skips_bom() -> None:
    assert _json(b'\xef\xbb\xbf[{"a": 1}]') == [(0, {"a": 1})]


@pytest.mark.usefixtures("tiny_chunks")
def test_json_elements_across_tiny_blocks() -> None:
    data = json.dumps(
        {"items": [{"title": "Ação nº 1 — ü"}, 12345, 1.5e3, True, "fim"]}, ensure_ascii=False
    )

    assert _json(data) == [
        (0, {"title": "Ação nº 1 — ü"}),
        (1, 12345),
        (2, 1500.0),
        (3, True),
        (4, "fim"),
    ]


def test_json_elements_streams_without_reading_the_whole_file() -> None:
    items = [{"external_id": f"T-{n}", "body": "x" * 500} for n in range(2000)]
    data = json.dumps(items).encode()
    file = TrackedFile(data)

    elements = json_elements(file)
    first = next(elements)

    assert first == (0, items[0])
    assert file.furthest < len(data) // 10
    assert sum(1 for _ in elements) == len(items) - 1


@pytest.mark.parametrize("data", ["", "  \n\t "])
def test_json_elements_blank_file_is_empty(data: str) -> None:
    with pytest.raises(UploadEmptyError) as caught:
        _json(data)

    assert caught.value.code == "upload_empty"


@pytest.mark.parametrize(
    "data",
    [
        '"text"',
        "42",
        '{"other": []}',
        '{"items": {}}',
        '{"items" []}',
        '{"items": [1]',
        '{"items": [1], "more": 2}',
        "[1, 2",
        "[1 2]",
        "[1, ]",
        "[{]",
        '[{"a": 1}] [2]',
        "[1] x",
        "[nope]",
    ],
)
def test_json_elements_malformed_file(data: str) -> None:
    with pytest.raises(UploadInvalidJsonError) as caught:
        _json(data)

    assert caught.value.code == "upload_invalid_json"
    assert caught.value.status_code == 422


def test_json_elements_refuses_bytes_that_are_not_utf8() -> None:
    with pytest.raises(UploadInvalidJsonError):
        _json(b'["\xff\xfe"]')


@pytest.mark.usefixtures("tiny_chunks")
def test_json_elements_cut_character_at_the_end_is_invalid() -> None:
    with pytest.raises(UploadInvalidJsonError):
        _json(b'["a"]' + "ç".encode()[:1])


def test_count_json_elements_counts_and_rewinds() -> None:
    file = io.BytesIO(b"[1, 2, 3]")

    assert count_json_elements(file) == 3
    assert file.tell() == 0
    assert list(json_elements(file)) == [(0, 1), (1, 2), (2, 3)]
