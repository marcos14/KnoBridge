"""Knowledge items of a runner source through the real ingestion steps (production connector
factory with the ``knowledge`` connector, real Postgres, fake embeddings): indexed as
``knowledge`` documents, reindexed when edited or approved, removed when discarded."""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pytest
from ingestion_harness import Harness, credentials, database
from sqlalchemy import select, update

from knobridge.core.db import system_session
from knobridge.core.settings import Settings
from knobridge.harness.knowledge_connector import KnowledgeConnectorFactory
from knobridge.harness.models import (
    HarnessModule,
    KnowledgeConfidence,
    KnowledgeItem,
    KnowledgeItemKind,
    KnowledgeReviewStatus,
    Runner,
)
from knobridge.ingestion.connectors import SettingsConnectorFactory
from knobridge.ingestion.indexer import Indexer
from knobridge.ingestion.models import (
    Chunk,
    Document,
    DocumentKind,
    Run,
    RunStatus,
    RunTrigger,
    Source,
)
from knobridge.ingestion.runs import RunLifecycle, RunScope
from knobridge.ingestion.source_config import SourceKind
from knobridge.ingestion.sync import start_sync
from knobridge.levels.level import ResponseLevel
from knobridge.llm.pricing import EmbeddingPriceTable

pytestmark = pytest.mark.integration

COMMIT = "3f2a9c1e5b7d4a6f8e0c2b4d6f8a0c2e4b6d8f0a"
EXCERPT = "if (!cliente.cnpj) {\n  throw new Erro();\n}"


@dataclass
class KnowledgeWorld:
    h: Harness
    source_id: uuid.UUID
    module_id: uuid.UUID

    @property
    def workspace_id(self) -> uuid.UUID:
        return self.h.seeded.workspace_id


type Body = Callable[[KnowledgeWorld], Awaitable[None]]


def _scenario(database_url: str, body: Body) -> None:
    async def main() -> None:
        async with database(database_url, {}) as h:
            await body(await _world(h))

    asyncio.run(main())


async def _world(h: Harness) -> KnowledgeWorld:
    async with system_session(h.factory) as db:
        runner = Runner(
            workspace_id=h.seeded.workspace_id,
            name="Runner",
            token_prefix=secrets.token_hex(4),
            token_hash="0" * 64,
        )
        db.add(runner)
        await db.flush()
        source = Source(
            workspace_id=h.seeded.workspace_id,
            collection_id=h.seeded.collection_id,
            kind=SourceKind.RUNNER,
            name="ERP",
            config={"runner_id": str(runner.id), "repository": "erp"},
        )
        db.add(source)
        await db.flush()
        module = HarnessModule(
            workspace_id=h.seeded.workspace_id,
            source_id=source.id,
            key="src-faturamento",
            title="src/faturamento",
            paths=["src/faturamento/"],
        )
        db.add(module)
        await db.flush()
        return KnowledgeWorld(h, source.id, module.id)


async def _add_rule(world: KnowledgeWorld, key: str = "src-faturamento.R001") -> uuid.UUID:
    async with system_session(world.h.factory) as db:
        item = KnowledgeItem(
            workspace_id=world.workspace_id,
            source_id=world.source_id,
            module_id=world.module_id,
            kind=KnowledgeItemKind.RULE,
            key=key,
            title="Nota fiscal exige CNPJ do cliente",
            content={
                "enunciado": "A nota só é emitida se o cliente tiver CNPJ válido.",
                "quando": "Ao emitir a nota.",
                "mensagem": "Informe o CNPJ do cliente.",
                "resolucao": "Completar o cadastro.",
                "parametros": [],
                "classificacao": "intencional",
                "relevancia": "alta",
            },
            evidence=[
                {
                    "path": "src/faturamento/notas.ts",
                    "start_line": 80,
                    "end_line": 82,
                    "symbol": "emitirNota",
                    "excerpt": EXCERPT,
                    "excerpt_truncated": False,
                    "excerpt_omitted": None,
                    "redacted": False,
                }
            ],
            commit_sha=COMMIT,
            generated_by="harness:claude_code",
        )
        db.add(item)
        await db.flush()
        return item.id


async def _update(world: KnowledgeWorld, item_id: uuid.UUID, **values: object) -> None:
    async with system_session(world.h.factory) as db:
        await db.execute(update(KnowledgeItem).where(KnowledgeItem.id == item_id).values(**values))


async def _sync(world: KnowledgeWorld) -> Run:
    """One harness run of the runner source through the production connector factory."""
    h = world.h
    connectors = SettingsConnectorFactory(
        Settings(env="test"), knowledge=KnowledgeConnectorFactory(h.factory)
    )
    lifecycle = RunLifecycle(h.factory, h.clock, connectors, EmbeddingPriceTable())
    indexer = Indexer(h.factory, h.clock, connectors, credentials(h.clock).reveal_key, h.embeddings)
    run = await start_sync(
        h.factory,
        h.starter,
        h.clock,
        workspace_id=world.workspace_id,
        source_id=world.source_id,
        trigger=RunTrigger.HARNESS,
    )
    scope = RunScope(world.workspace_id, world.source_id, run.id)
    await lifecycle.open(scope)
    total = await lifecycle.list_changes(scope)
    for start in range(0, total, 50):
        await indexer.process_batch(scope, start, 50)
    await lifecycle.finish(scope, RunStatus.SUCCEEDED)
    return await h.run(run.id)


async def _documents(world: KnowledgeWorld) -> dict[str, Document]:
    async with world.h.session() as db:
        rows = await db.scalars(select(Document).where(Document.source_id == world.source_id))
        return {row.natural_key: row for row in rows}


async def _chunks(world: KnowledgeWorld) -> list[Chunk]:
    async with world.h.session() as db:
        rows = await db.scalars(
            select(Chunk)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.source_id == world.source_id)
            .order_by(Chunk.position)
        )
        return list(rows)


def test_knowledge_items_are_indexed_as_knowledge_documents(app_database_url: str) -> None:
    async def body(world: KnowledgeWorld) -> None:
        await _add_rule(world)
        await _add_rule(world, "src-faturamento.R002")

        run = await _sync(world)
        again = await _sync(world)
        documents = await _documents(world)

        assert (run.status, run.trigger, run.documents_new) == (
            RunStatus.SUCCEEDED,
            RunTrigger.HARNESS,
            2,
        )
        assert (again.documents_new, again.documents_changed, again.embedding_tokens) == (0, 0, 0)
        document = documents["src-faturamento.R001"]
        assert (document.kind, document.uri, document.title) == (
            DocumentKind.KNOWLEDGE,
            "knowledge:src-faturamento.R001",
            "Nota fiscal exige CNPJ do cliente",
        )

    _scenario(app_database_url, body)


def test_knowledge_chunk_meta_carries_evidence(app_database_url: str) -> None:
    async def body(world: KnowledgeWorld) -> None:
        await _add_rule(world)

        await _sync(world)
        chunks = await _chunks(world)

        assert len(chunks) == 2
        first = chunks[0]
        assert {key: first.meta[key] for key in ("kind", "item_key", "module", "confidence")} == {
            "kind": "knowledge",
            "item_key": "src-faturamento.R001",
            "module": "src-faturamento",
            "confidence": "inferido",
        }
        assert all(
            chunk.meta["evidence"]
            == [
                {
                    "path": "src/faturamento/notas.ts",
                    "start_line": 80,
                    "end_line": 82,
                    "symbol": "emitirNota",
                    "excerpt": EXCERPT,
                }
            ]
            for chunk in chunks
        )
        assert first.content.startswith("item: src-faturamento.R001\n")

    _scenario(app_database_url, body)


def test_edited_item_reindexed_with_edited_content(app_database_url: str) -> None:
    async def body(world: KnowledgeWorld) -> None:
        item_id = await _add_rule(world)
        await _sync(world)
        await _update(
            world,
            item_id,
            edited={
                "title": "Nota pede CNPJ",
                "content": {
                    "enunciado": "Sem CNPJ válido, a nota não sai.",
                    "quando": "Sempre.",
                    "mensagem": None,
                    "resolucao": "Cadastrar o CNPJ.",
                    "parametros": [],
                    "classificacao": "observado",
                    "relevancia": "media",
                },
            },
        )

        run = await _sync(world)
        document = (await _documents(world))["src-faturamento.R001"]
        displays = [str(chunk.meta["display"]) for chunk in await _chunks(world)]

        assert (run.documents_changed, run.documents_new) == (1, 0)
        assert document.title == "Nota pede CNPJ"
        assert displays[0].startswith("# Nota pede CNPJ\n\nSem CNPJ válido, a nota não sai.")
        assert not any("CNPJ do cliente" in display for display in displays)

    _scenario(app_database_url, body)


def test_approved_item_reindexed_as_revisado(app_database_url: str) -> None:
    async def body(world: KnowledgeWorld) -> None:
        item_id = await _add_rule(world)
        await _sync(world)
        await _update(
            world,
            item_id,
            review_status=KnowledgeReviewStatus.APPROVED,
            confidence=KnowledgeConfidence.REVIEWED,
        )

        run = await _sync(world)

        assert run.documents_changed == 1
        assert {str(chunk.meta["confidence"]) for chunk in await _chunks(world)} == {"revisado"}

    _scenario(app_database_url, body)


async def _chunk_levels(world: KnowledgeWorld) -> list[tuple[list[str], ResponseLevel]]:
    return [
        ([str(heading) for heading in chunk.meta["headings"]], chunk.min_level)  # type: ignore[union-attr]
        for chunk in await _chunks(world)
    ]


def test_inferred_item_is_for_support_and_its_evidence_never_for_the_end_user(
    app_database_url: str,
) -> None:
    title = "Nota fiscal exige CNPJ do cliente"

    async def body(world: KnowledgeWorld) -> None:
        item_id = await _add_rule(world)
        await _sync(world)
        inferred_document = (await _documents(world))["src-faturamento.R001"].min_level
        inferred = await _chunk_levels(world)
        await _update(
            world,
            item_id,
            review_status=KnowledgeReviewStatus.APPROVED,
            confidence=KnowledgeConfidence.REVIEWED,
        )
        await _sync(world)
        reviewed_document = (await _documents(world))["src-faturamento.R001"].min_level
        reviewed = await _chunk_levels(world)

        assert inferred_document is ResponseLevel.SUPPORT
        assert inferred == [
            ([title], ResponseLevel.SUPPORT),
            ([title, "Evidências"], ResponseLevel.SUPPORT),
        ]
        # Approved: the rule reaches the end user (the source's level); the evidence, with
        # paths and code excerpts, stays for support and above.
        assert reviewed_document is None
        assert reviewed == [
            ([title], ResponseLevel.END_USER),
            ([title, "Evidências"], ResponseLevel.SUPPORT),
        ]

    _scenario(app_database_url, body)


def test_discarded_item_removed_from_index(app_database_url: str) -> None:
    async def body(world: KnowledgeWorld) -> None:
        item_id = await _add_rule(world)
        await _add_rule(world, "src-faturamento.R002")
        await _sync(world)
        await _update(world, item_id, review_status=KnowledgeReviewStatus.DISCARDED)

        run = await _sync(world)
        documents = await _documents(world)

        assert run.documents_removed == 1
        assert list(documents) == ["src-faturamento.R002"]
        assert {str(chunk.meta["item_key"]) for chunk in await _chunks(world)} == {
            "src-faturamento.R002"
        }

    _scenario(app_database_url, body)
