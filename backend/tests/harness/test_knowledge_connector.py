"""The internal ``knowledge`` connector over real Postgres: items not discarded as documents, the
incremental cursor by hash, fetch with Markdown and citation metadata, and workspace isolation."""

from __future__ import annotations

import uuid

import pytest
from harness_support import (
    Seeded,
    SessionFactory,
    base_rows,
    rule_item,
    run_db,
    runner_source,
    seed,
)
from sqlalchemy import update

from knobridge.connectors.base import OPEN_ACL, Acl, ChangeSet, DocumentRef, RawDocument
from knobridge.connectors.errors import DocumentNotFoundError, InvalidCursorError
from knobridge.core.db import system_session
from knobridge.harness.knowledge_connector import KnowledgeConnector, KnowledgeConnectorFactory
from knobridge.harness.models import (
    HarnessModule,
    KnowledgeConfidence,
    KnowledgeItem,
    KnowledgeReviewStatus,
)
from knobridge.ingestion.models import DocumentKind, Source

pytestmark = pytest.mark.integration


def _connector(factory: SessionFactory, seeded: Seeded) -> KnowledgeConnector:
    return KnowledgeConnector(factory, workspace_id=seeded.workspace_id, source_id=seeded.source_id)


async def _add(factory: SessionFactory, seeded: Seeded, key: str, **fields: object) -> uuid.UUID:
    async with system_session(factory) as db:
        item = rule_item(seeded, key)
        for name, value in fields.items():
            setattr(item, name, value)
        db.add(item)
        await db.flush()
        return item.id


async def _set(factory: SessionFactory, item_id: uuid.UUID, **values: object) -> None:
    async with system_session(factory) as db:
        await db.execute(update(KnowledgeItem).where(KnowledgeItem.id == item_id).values(**values))


def _keys(refs: tuple[DocumentRef, ...]) -> list[str]:
    return [ref.key for ref in refs]


def test_knowledge_connector_lists_non_discarded_items(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> ChangeSet:
        seeded = await seed(factory)
        await _add(factory, seeded, "src-faturamento.R003")
        await _add(
            factory, seeded, "src-faturamento.R002", review_status=KnowledgeReviewStatus.DISCARDED
        )
        return await _connector(factory, seeded).list_changes(None)

    changes = run_db(app_database_url, scenario)

    assert _keys(changes.added) == ["src-faturamento.R001", "src-faturamento.R003"]
    assert {ref.kind for ref in changes.added} == {DocumentKind.KNOWLEDGE}
    assert (changes.changed, changes.removed) == ((), ())
    assert changes.cursor["kind"] == "knowledge"
    assert changes.cursor["version"] == 1
    items = changes.cursor["items"]
    assert isinstance(items, dict)
    assert sorted(items) == ["src-faturamento.R001", "src-faturamento.R003"]


def test_knowledge_connector_reports_changed_and_removed_by_hash(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[ChangeSet, ChangeSet]:
        seeded = await seed(factory)
        kept = await _add(factory, seeded, "src-faturamento.R002")
        gone = await _add(factory, seeded, "src-faturamento.R003")
        connector = _connector(factory, seeded)
        first = await connector.list_changes(None)
        unchanged = await connector.list_changes(first.cursor)
        await _set(factory, seeded.item_id, edited={"title": "Outro título"})
        await _set(factory, kept, confidence=KnowledgeConfidence.REVIEWED)
        await _set(factory, gone, review_status=KnowledgeReviewStatus.DISCARDED)
        await _add(factory, seeded, "src-faturamento.R004")
        return unchanged, await connector.list_changes(unchanged.cursor)

    unchanged, changes = run_db(app_database_url, scenario)

    assert unchanged.is_empty
    assert _keys(changes.added) == ["src-faturamento.R004"]
    assert _keys(changes.changed) == ["src-faturamento.R001", "src-faturamento.R002"]
    assert _keys(changes.removed) == ["src-faturamento.R003"]


def test_knowledge_connector_fetch_returns_markdown_and_citation_meta(
    app_database_url: str,
) -> None:
    async def scenario(factory: SessionFactory) -> tuple[ChangeSet, RawDocument, Acl]:
        seeded = await seed(factory)
        await _set(factory, seeded.item_id, edited={"title": "Nota pede CNPJ"})
        connector = _connector(factory, seeded)
        changes = await connector.list_changes(None)
        ref = DocumentRef("src-faturamento.R001", DocumentKind.KNOWLEDGE)
        return changes, await connector.fetch(ref), await connector.permissions(ref)

    changes, raw, acl = run_db(app_database_url, scenario)

    assert raw.title == "Nota pede CNPJ"
    assert raw.uri == "knowledge:src-faturamento.R001"
    assert raw.extension == "md"
    assert raw.text.startswith("# Nota pede CNPJ\n\nA nota só é emitida com CNPJ válido.\n")
    assert dict(raw.metadata) == {
        "kind": "knowledge",
        "item_key": "src-faturamento.R001",
        "item_kind": "rule",
        "module": "src-faturamento",
        "confidence": "inferido",
        "title": "Nota pede CNPJ",
        "evidence": [
            {
                "path": "src/notas.ts",
                "start_line": 80,
                "end_line": 92,
                "symbol": None,
                "excerpt": None,
            }
        ],
    }
    items = changes.cursor["items"]
    assert isinstance(items, dict)
    assert raw.content_hash == items["src-faturamento.R001"]
    assert acl == OPEN_ACL


def test_knowledge_connector_fetch_of_discarded_item_is_not_found(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        await _set(factory, seeded.item_id, review_status=KnowledgeReviewStatus.DISCARDED)
        await _connector(factory, seeded).fetch(
            DocumentRef("src-faturamento.R001", DocumentKind.KNOWLEDGE)
        )

    with pytest.raises(DocumentNotFoundError):
        run_db(app_database_url, scenario)


def test_knowledge_connector_rejects_a_foreign_cursor(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        connector = _connector(factory, seeded)
        await connector.test_connection()
        await connector.list_changes({"kind": "folder", "version": 1, "entries": {}})

    with pytest.raises(InvalidCursorError):
        run_db(app_database_url, scenario)


def test_knowledge_connector_isolated_by_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[list[str], list[str]]:
        seeded = await seed(factory)
        other = await seed(factory)
        await _add(factory, other, "src-faturamento.R009")
        # The connector of one workspace pointed at the other's source finds nothing.
        forged = KnowledgeConnector(
            factory, workspace_id=seeded.workspace_id, source_id=other.source_id
        )
        own = await _connector(factory, seeded).list_changes(None)
        return _keys(own.added), _keys((await forged.list_changes(None)).added)

    own, forged = run_db(app_database_url, scenario)

    assert own == ["src-faturamento.R001"]
    assert forged == []


def test_knowledge_connector_factory_builds_for_the_source(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> list[str]:
        async with system_session(factory) as db:
            workspace, runner, collection = await base_rows(db)
            source = runner_source(workspace.id, collection.id, runner.id, "erp")
            db.add(source)
            await db.flush()
            module = HarnessModule(
                workspace_id=workspace.id,
                source_id=source.id,
                key="src-core",
                title="src/core",
                paths=["src/core/"],
            )
            db.add(module)
            await db.flush()
            seeded = Seeded(
                workspace.id,
                collection.id,
                runner.id,
                "",
                source.id,
                module.id,
                uuid.uuid4(),
                uuid.uuid4(),
            )
            db.add(rule_item(seeded, "src-core.R001"))
            stored = await db.get_one(Source, source.id)
        connector = KnowledgeConnectorFactory(factory)(stored)
        return _keys((await connector.list_changes(None)).added)

    assert run_db(app_database_url, scenario) == ["src-core.R001"]
