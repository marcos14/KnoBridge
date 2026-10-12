"""Reading an uploaded file of tickets as a stream of elements (docs/specs/chamados.md, "Upload
no painel").

Pure (no database, network or clock) and incremental: neither format is ever loaded whole.
``.jsonl`` is read line by line; a line that is not JSON is an element of its own
(``INVALID_LINE``) and the others go on. ``.json`` is a list of elements, or ``{"items": [...]}``
like the body of the API, decoded one element at a time from a growing buffer; the buffer only
holds the element being decoded (it doubles while an element is incomplete, so a large element
costs linear time). A malformed ``.json`` is an error of the whole file, so the caller checks it
in a first pass (``count_json_elements``) before writing anything.
"""

from __future__ import annotations

import codecs
import json
from collections.abc import Iterator
from enum import Enum
from pathlib import PurePosixPath
from typing import BinaryIO, Literal

from knobridge.core.errors import ValidationError

type UploadFormat = Literal["json", "jsonl"]

CHUNK_CHARS = 64 * 1024
_WHITESPACE = " \t\n\r"
_DECODER = json.JSONDecoder()


class InvalidLine(Enum):
    """A ``.jsonl`` line that is not valid JSON."""

    INVALID_LINE = "invalid_line"


INVALID_LINE = InvalidLine.INVALID_LINE


class UploadFormatUnsupportedError(ValidationError):
    code = "upload_format_unsupported"


class UploadInvalidJsonError(ValidationError):
    code = "upload_invalid_json"


class UploadEmptyError(ValidationError):
    code = "upload_empty"


def upload_format(filename: str | None) -> UploadFormat:
    """The format by the file name's extension (``.json`` or ``.jsonl``, any case)."""
    extension = PurePosixPath(filename or "").suffix.lower()
    if extension == ".json":
        return "json"
    if extension == ".jsonl":
        return "jsonl"
    raise UploadFormatUnsupportedError(
        "The file must be .json or .jsonl.", details={"filename": filename}
    )


def jsonl_elements(file: BinaryIO) -> Iterator[tuple[int, object]]:
    """``(line number from 1, element or INVALID_LINE)`` of the non-blank lines."""
    for number, line in enumerate(file, start=1):
        if not line.strip():
            continue
        try:
            # From bytes, ``json.loads`` detects the encoding and skips a UTF-8 BOM.
            yield number, json.loads(line)
        except ValueError:  # JSONDecodeError and UnicodeDecodeError alike
            yield number, INVALID_LINE


def _invalid(message: str) -> UploadInvalidJsonError:
    return UploadInvalidJsonError(message)


class _JsonReader:
    """A cursor over the text of the file, refilled from the stream on demand."""

    def __init__(self, file: BinaryIO) -> None:
        self._file = file
        # Incremental: a character cut at the end of a block waits for the next one; the BOM
        # of the first block is dropped.
        self._decoder = codecs.getincrementaldecoder("utf-8-sig")()
        self._buffer = ""
        self._pos = 0
        self._eof = False

    def _fill(self, size: int) -> bool:
        """Append the text of up to ``size`` more bytes; ``False`` at the end of the file."""
        if self._eof:
            return False
        raw = self._file.read(size)
        self._eof = not raw
        try:
            text = self._decoder.decode(raw, final=self._eof)
        except UnicodeDecodeError as exc:
            raise _invalid("The file is not UTF-8 text.") from exc
        self._buffer = self._buffer[self._pos :] + text
        self._pos = 0
        # The last block may hold only part of a character: read on until text or the end.
        return bool(text) or self._fill(size)

    def peek(self) -> str:
        """The next non-whitespace character (consumed whitespace), or ``""`` at the end."""
        while True:
            while self._pos < len(self._buffer) and self._buffer[self._pos] in _WHITESPACE:
                self._pos += 1
            if self._pos < len(self._buffer):
                return self._buffer[self._pos]
            if not self._fill(CHUNK_CHARS):
                return ""

    def expect(self, char: str) -> None:
        if self.peek() != char:
            raise _invalid(f"Expected {char!r} in the JSON file.")
        self._pos += 1

    def value(self) -> object:
        """Decode the JSON value at the cursor, reading more while it is incomplete."""
        self.peek()
        chunk = CHUNK_CHARS
        while True:
            try:
                value, end = _DECODER.raw_decode(self._buffer, self._pos)
            except json.JSONDecodeError as exc:
                if not self._fill(max(chunk, len(self._buffer))):
                    raise _invalid("The file is not valid JSON.") from exc
                chunk *= 2
                continue
            # A number or literal ending at the buffer's end may go on in the next block.
            if end == len(self._buffer) and self._fill(chunk):
                continue
            self._pos = end
            return value


def _array(reader: _JsonReader) -> Iterator[object]:
    reader.expect("[")
    if reader.peek() == "]":
        reader.expect("]")
        return
    while True:
        yield reader.value()
        if reader.peek() == "]":
            reader.expect("]")
            return
        reader.expect(",")


def json_elements(file: BinaryIO) -> Iterator[tuple[int, object]]:
    """``(position from 0, element)`` of a ``.json`` list or ``{"items": [...]}``; raises
    ``upload_invalid_json`` at the first malformed byte (``upload_empty`` for a blank file)."""
    reader = _JsonReader(file)
    first = reader.peek()
    if first == "":
        raise UploadEmptyError("The file is empty.")
    if first == "{":
        reader.expect("{")
        if reader.value() != "items":
            raise _invalid('The JSON object must be {"items": [...]}.')
        reader.expect(":")
    elif first != "[":
        raise _invalid('The JSON file must be a list or {"items": [...]}.')
    if reader.peek() != "[":
        raise _invalid('The JSON object must be {"items": [...]}.')
    yield from enumerate(_array(reader))
    if first == "{":
        reader.expect("}")
    if reader.peek() != "":
        raise _invalid("Unexpected content after the JSON value.")


def count_json_elements(file: BinaryIO) -> int:
    """The first pass over a ``.json`` file: the number of elements, or the error of the file.
    Rewinds the file for the second pass."""
    total = sum(1 for _ in json_elements(file))
    file.seek(0)
    return total
