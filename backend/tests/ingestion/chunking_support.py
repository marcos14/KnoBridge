from __future__ import annotations

import asyncio
from collections.abc import Mapping

from knobridge.audit.models import JSONValue
from knobridge.connectors.base import DocumentRef, RawDocument
from knobridge.ingestion.chunk_base import ChunkDraft
from knobridge.ingestion.chunking import chunk_document
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.parsing import ParsedDocument, parse_document


def parsed(
    key: str,
    content: str,
    *,
    kind: DocumentKind = DocumentKind.FILE,
    metadata: Mapping[str, JSONValue] | None = None,
) -> ParsedDocument:
    """Run the real parser on a synthetic file or commit."""
    name = key.rpartition("/")[2]
    extension = name.rpartition(".")[2].lower() if "." in name else ""
    raw = RawDocument(
        ref=DocumentRef(key, kind),
        title=name,
        uri=f"file:///src/{key}",
        content=content.encode(),
        extension=extension,
        metadata={"path": key} if metadata is None else metadata,
    )
    return asyncio.run(parse_document(raw))


def chunks(
    key: str,
    content: str,
    *,
    kind: DocumentKind = DocumentKind.FILE,
    metadata: Mapping[str, JSONValue] | None = None,
) -> list[ChunkDraft]:
    return chunk_document(parsed(key, content, kind=kind, metadata=metadata))


def lines_of(chunk: ChunkDraft) -> tuple[object, object]:
    return chunk.meta.get("start_line"), chunk.meta.get("end_line")
