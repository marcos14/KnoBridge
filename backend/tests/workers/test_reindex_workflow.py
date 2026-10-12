"""Reindexing a source end to end: ``SyncActions.reindex`` in a request-like transaction, then
the real ingestion workflow on the Temporal test server reprocesses every document."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from ingestion_harness import Harness, harness
from sqlalchemy import select

from knobridge.core.db import scoped_session, system_session
from knobridge.ingestion.models import Run, RunStatus
from knobridge.ingestion.reindex import SyncActions
from knobridge.tenancy.models import Membership

pytestmark = pytest.mark.integration

FILES = {
    "guia/senha.txt": b"Para trocar a senha, abra o menu Perfil e escolha Seguranca.",
    "faturamento.txt": b"O erro 42 no faturamento indica nota fiscal sem cliente.",
    "estoque.txt": b"O estoque minimo fica no cadastro do produto.",
}


async def _owner(h: Harness) -> uuid.UUID:
    async with system_session(h.factory) as db:
        user_id = await db.scalar(
            select(Membership.user_id).where(Membership.workspace_id == h.seeded.workspace_id)
        )
        assert user_id is not None
        return user_id


async def _reindex(h: Harness) -> Run:
    """Reindex inside a scoped transaction, as the API route does, and wait for the workflow."""
    actor = await _owner(h)
    workspace_id = h.seeded.workspace_id
    async with scoped_session(h.factory, workspace_id=workspace_id, user_id=actor) as db:
        run = await SyncActions(h.factory, h.starter, h.clock).reindex(
            db, workspace_id=workspace_id, actor_id=actor, source_id=h.seeded.source_id, ip=None
        )
    await h.handle().result()
    return await h.run(run.id)


def test_reindex_reprocesses_every_document(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        first = await h.sync()
        before = {key: doc.content_hash for key, doc in (await h.documents()).items()}
        ids = {key: doc.id for key, doc in (await h.documents()).items()}
        h.connector.fetched.clear()
        embedded = len(h.embeddings.provider.texts)

        run = await _reindex(h)
        documents = await h.documents()

        assert first.documents_new == len(FILES)
        assert (run.status, run.documents_new, run.documents_changed) == (
            RunStatus.SUCCEEDED,
            0,
            len(FILES),
        )
        assert sorted(h.connector.fetched) == sorted(FILES)
        assert {key: doc.content_hash for key, doc in documents.items()} == before
        assert {key: doc.id for key, doc in documents.items()} == ids
        assert run.chunks_written == len(await h.chunks()) == len(FILES)
        # Unchanged chunks reuse their vectors: reindexing costs no new embeddings.
        assert len(h.embeddings.provider.texts) == embedded
        assert (await h.source()).cursor is not None

    async def main() -> None:
        async with harness(app_database_url, FILES) as h:
            await body(h)

    asyncio.run(main())


def test_plain_sync_after_reindex_skips_again(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        await h.sync()
        await _reindex(h)
        h.connector.fetched.clear()

        run = await h.sync()

        assert (run.status, run.documents_new, run.documents_changed) == (
            RunStatus.SUCCEEDED,
            0,
            0,
        )
        assert h.connector.fetched == []

    async def main() -> None:
        async with harness(app_database_url, FILES) as h:
            await body(h)

    asyncio.run(main())
