"""The minimum level written by the ingestion and changed by an admin, against real Postgres
(``docs/specs/produtos-e-niveis.md``, "Nível mínimo de fonte, de documento e de trecho"): a
folder source keeps its documents for the end user but its code for development, the effective
level of a chunk is the highest of the source's, the document's and its own, and changing the
level of a source recomputes its chunks at once, without reindexing."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest
from ingestion_harness import Harness, ScriptedConnector, credentials, database
from sqlalchemy import select, update

from knobridge.audit.service import AuditService
from knobridge.connectors.base import DocumentRef, RawDocument
from knobridge.ingestion.chunk_base import ChunkDraft
from knobridge.ingestion.indexer import document_min_level
from knobridge.ingestion.models import Chunk, Document, Run, RunStatus, Source
from knobridge.ingestion.parsing import ParsedDocument, ParsedKind
from knobridge.ingestion.source_config import SourceKind
from knobridge.ingestion.source_levels import change_source_level
from knobridge.ingestion.store import chunk_min_level
from knobridge.levels.level import ResponseLevel
from knobridge.retrieval.search import SearchHit, SearchService

END_USER, SUPPORT, PRODUCT_DEV = ResponseLevel
MANUAL = b"# Fechamento\n\nO fechamento de caixa exige o relatorio Z antes da sangria.\n"
CODE = (
    b"def fechar_caixa():\n    # fechamento de caixa exige o relatorio Z\n"
    b"    emitir_relatorio_z()\n"
)
QUERY = "fechamento caixa relatorio"

type Levels = dict[str, tuple[ResponseLevel | None, set[ResponseLevel]]]
type Body = Callable[[Harness], Awaitable[None]]


class _ExtensionConnector(ScriptedConnector):
    """The fake connector with the extension of the key, so ``.py`` parses as code."""

    async def fetch(self, ref: DocumentRef) -> RawDocument:
        raw = await super().fetch(ref)
        return RawDocument(
            ref=raw.ref,
            title=raw.title,
            uri=raw.uri,
            content=raw.content,
            extension=ref.key.rsplit(".", 1)[-1],
        )


def _scenario(database_url: str, body: Body) -> None:
    async def main() -> None:
        async with database(database_url, {}) as h:
            h.connector = _ExtensionConnector({"manual.md": MANUAL, "caixa.py": CODE})
            await body(h)

    asyncio.run(main())


async def _sync(h: Harness) -> Run:
    run = await h.start()
    scope = h.scope(run.id)
    await h.lifecycle.open(scope)
    total = await h.lifecycle.list_changes(scope)
    for start in range(0, total, 50):
        await h.indexer.process_batch(scope, start, 50)
    await h.lifecycle.finish(scope, RunStatus.SUCCEEDED)
    return await h.run(run.id)


async def _levels(h: Harness) -> Levels:
    """Per document key: its own level and the levels of its chunks."""
    documents = await h.documents()
    chunks = await h.chunks()
    return {
        key: (doc.min_level, {chunk.min_level for chunk in chunks if chunk.document_id == doc.id})
        for key, doc in documents.items()
    }


async def _set_level(h: Harness, level: ResponseLevel) -> None:
    async with h.session() as db:
        source = await db.get_one(Source, h.seeded.source_id)
        await change_source_level(
            db, AuditService(h.clock), source=source, level=level, actor_id=None, ip=None
        )


async def _search(h: Harness, level: ResponseLevel) -> list[SearchHit]:
    service = SearchService(credentials(h.clock), h.embeddings)
    async with h.session() as db:
        return await service.search(
            db,
            workspace_id=h.seeded.workspace_id,
            collection_ids=[h.seeded.collection_id],
            query=QUERY,
            level=level,
        )


@pytest.mark.integration
def test_folder_code_is_for_development_and_documents_for_everyone(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        await _sync(h)
        levels = await _levels(h)
        end_user = await _search(h, END_USER)
        developer = await _search(h, PRODUCT_DEV)

        assert levels == {
            "manual.md": (None, {END_USER}),
            "caixa.py": (PRODUCT_DEV, {PRODUCT_DEV}),
        }
        # The code matches the question, and still never reaches an end-user answer.
        assert [hit.document.natural_key for hit in end_user] == ["manual.md"]
        assert {hit.document.natural_key for hit in developer} == {"manual.md", "caixa.py"}

    _scenario(app_database_url, body)


@pytest.mark.integration
def test_source_level_change_recomputes_chunks_without_reindexing(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        await _sync(h)
        embedded = h.embeddings.provider.calls
        await _set_level(h, SUPPORT)
        raised = await _levels(h)
        await _set_level(h, END_USER)
        lowered = await _levels(h)

        assert raised == {
            "manual.md": (None, {SUPPORT}),
            "caixa.py": (PRODUCT_DEV, {PRODUCT_DEV}),
        }
        # The refinement of the code only raises its level: lowering the source never
        # exposes it.
        assert lowered == {
            "manual.md": (None, {END_USER}),
            "caixa.py": (PRODUCT_DEV, {PRODUCT_DEV}),
        }
        assert h.embeddings.provider.calls == embedded

    _scenario(app_database_url, body)


@pytest.mark.integration
def test_next_batch_stores_chunks_with_the_new_source_level(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        async with h.session() as db:
            await db.execute(
                update(Source).where(Source.id == h.seeded.source_id).values(min_level=SUPPORT)
            )

        await _sync(h)

        assert (await _levels(h))["manual.md"] == (None, {SUPPORT})

    _scenario(app_database_url, body)


@pytest.mark.integration
def test_chunk_level_keeps_the_highest_refinement(app_database_url: str) -> None:
    """A chunk refined above its document and source (``meta.min_level``) keeps it."""

    async def body(h: Harness) -> None:
        await _sync(h)
        async with h.session() as db:
            manual_id = await db.scalar(
                select(Document.id).where(
                    Document.source_id == h.seeded.source_id, Document.natural_key == "manual.md"
                )
            )
            await db.execute(
                update(Chunk)
                .where(Chunk.document_id == manual_id)
                .values(meta=Chunk.meta.op("||")({"min_level": "support"}))
            )
        await _set_level(h, END_USER)

        assert (await _levels(h))["manual.md"] == (None, {SUPPORT})

    _scenario(app_database_url, body)


def _parsed(kind: ParsedKind) -> ParsedDocument:
    return ParsedDocument(
        ref=DocumentRef("x"),
        uri="fake://x",
        content_hash="0" * 64,
        kind=kind,
        title="x",
        markdown="x",
    )


def _raw(level: ResponseLevel | None) -> RawDocument:
    return RawDocument(
        ref=DocumentRef("x"), title="x", uri="fake://x", content=b"x", min_level=level
    )


@pytest.mark.parametrize(
    ("kind", "parsed", "connector", "expected"),
    [
        (SourceKind.FOLDER, ParsedKind.CODE, None, PRODUCT_DEV),
        (SourceKind.FOLDER, ParsedKind.MARKDOWN, None, None),
        (SourceKind.GIT, ParsedKind.CODE, None, None),
        (SourceKind.RUNNER, ParsedKind.KNOWLEDGE, SUPPORT, SUPPORT),
        (SourceKind.FOLDER, ParsedKind.CODE, SUPPORT, PRODUCT_DEV),
    ],
)
def test_document_min_level_refinements(
    kind: SourceKind,
    parsed: ParsedKind,
    connector: ResponseLevel | None,
    expected: ResponseLevel | None,
) -> None:
    assert document_min_level(kind, _raw(connector), _parsed(parsed)) == expected


def test_unknown_chunk_refinement_is_ignored() -> None:
    draft = ChunkDraft(
        position=0,
        content="x",
        display="x",
        meta={"min_level": "admin"},
        tokens=1,
        content_hash="h",
    )

    assert chunk_min_level(END_USER, None, draft) is END_USER
    assert chunk_min_level(END_USER, SUPPORT, draft) is SUPPORT
