"""``sources.index_stats`` written when a run finishes (``RunLifecycle.finish`` with
``ingestion/index_stats.py``) against real Postgres: a folder source dominated by a directory
of generated files, a failed run keeping the previous value, a ticket source without
statistics, and the counts of another workspace and source never mixed in."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Mapping

import pytest
from ingestion_harness import Harness, Seeded, database, seed

from knobridge.audit.models import JSONValue
from knobridge.core.db import scoped_session
from knobridge.ingestion.models import (
    Chunk,
    Document,
    DocumentKind,
    Run,
    RunStatus,
    RunTrigger,
    Source,
)
from knobridge.ingestion.runs import RunScope
from knobridge.ingestion.source_config import SourceKind
from knobridge.llm.fake_embeddings import fake_vector

HASH = "0" * 64
VECTOR = fake_vector("synthetic chunk")
# 20 generated files with 20 chunks each and 100 ordinary ones with one: 400 of 505 chunks.
DOMINATED = {f"out/report{index}.txt": 20 for index in range(20)} | {
    f"src/m{index // 4}/f{index}.py": 1 for index in range(100)
}

type Body = Callable[[Harness], Awaitable[None]]


def _with_database(database_url: str, body: Body) -> None:
    async def main() -> None:
        async with database(database_url, {}) as h:
            await body(h)

    asyncio.run(main())


async def _write(
    h: Harness,
    seeded: Seeded,
    files: Mapping[str, int],
    *,
    source_id: uuid.UUID | None = None,
    commit_chunks: int = 0,
) -> None:
    """Documents with that many chunks each, plus one commit document."""
    source = seeded.source_id if source_id is None else source_id
    documents = [(key, DocumentKind.FILE, count) for key, count in files.items()]
    if commit_chunks:
        documents.append(("commit:abc", DocumentKind.COMMIT, commit_chunks))
    async with scoped_session(h.factory, workspace_id=seeded.workspace_id, user_id=None) as db:
        for key, kind, count in documents:
            document = Document(
                workspace_id=seeded.workspace_id,
                source_id=source,
                natural_key=key,
                kind=kind,
                title=key,
                uri=f"file:///sources/docs/{key}",
                content_hash=HASH,
            )
            db.add(document)
            await db.flush()
            db.add_all(
                Chunk(
                    workspace_id=seeded.workspace_id,
                    document_id=document.id,
                    collection_id=seeded.collection_id,
                    position=position,
                    content=f"{key} {position}",
                    meta={},
                    content_hash=HASH,
                    embedding_model="text-embedding-3-small",
                    embedding=VECTOR,
                )
                for position in range(count)
            )


async def _finish(
    h: Harness,
    status: RunStatus,
    *,
    seeded: Seeded | None = None,
    source_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """A running run of the source, closed with ``status``."""
    target = seeded or h.seeded
    source = target.source_id if source_id is None else source_id
    async with scoped_session(h.factory, workspace_id=target.workspace_id, user_id=None) as db:
        run = Run(
            workspace_id=target.workspace_id,
            source_id=source,
            trigger=RunTrigger.MANUAL,
            status=RunStatus.RUNNING,
        )
        db.add(run)
        await db.flush()
        run_id = run.id
    await h.lifecycle.finish(RunScope(target.workspace_id, source, run_id), status)
    return run_id


async def _stats(h: Harness, seeded: Seeded, source_id: uuid.UUID) -> dict[str, JSONValue] | None:
    async with scoped_session(h.factory, workspace_id=seeded.workspace_id, user_id=None) as db:
        source = await db.get_one(Source, source_id)
        return source.index_stats


async def _ticket_source(h: Harness) -> uuid.UUID:
    async with h.session() as db:
        source = Source(
            workspace_id=h.seeded.workspace_id,
            collection_id=h.seeded.collection_id,
            kind=SourceKind.TICKETS,
            name="Chamados",
            config={},
        )
        db.add(source)
        await db.flush()
        return source.id


@pytest.mark.integration
def test_finish_stores_index_stats_of_a_dominated_folder(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        await _write(h, h.seeded, DOMINATED, commit_chunks=5)

        run_id = await _finish(h, RunStatus.SUCCEEDED)
        stats = await _stats(h, h.seeded, h.seeded.source_id)

        assert stats is not None
        assert (stats["chunks"], stats["file_chunks"], stats["files"]) == (505, 500, 120)
        assert stats["run_id"] == str(run_id)
        assert stats["computed_at"] == "2026-10-10T12:00:00Z"
        assert stats["dominant"] == [
            {
                "kind": "directory",
                "pattern": "out/**",
                "files": 20,
                "chunks": 400,
                "share": 0.7921,
                "chunks_per_file": 20.0,
            }
        ]
        assert stats["suggested_exclude_globs"] == ["out/**"]

        await _finish(h, RunStatus.FAILED)
        await _finish(h, RunStatus.CANCELLED)

        assert await _stats(h, h.seeded, h.seeded.source_id) == stats

    _with_database(app_database_url, body)


@pytest.mark.integration
def test_finish_leaves_index_stats_null_for_ticket_sources(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        tickets = await _ticket_source(h)
        await _write(h, h.seeded, DOMINATED, source_id=tickets)

        await _finish(h, RunStatus.SUCCEEDED, source_id=tickets)

        assert await _stats(h, h.seeded, tickets) is None

    _with_database(app_database_url, body)


@pytest.mark.integration
def test_index_stats_count_only_the_source_of_its_workspace(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        other_workspace = await seed(h.factory, h.clock)
        other_source = await _ticket_source(h)
        await _write(h, other_workspace, DOMINATED)
        await _write(h, h.seeded, DOMINATED, source_id=other_source)
        await _write(h, h.seeded, {"docs/manual.md": 3, "docs/faq.md": 2})

        await _finish(h, RunStatus.SUCCEEDED)
        await _finish(h, RunStatus.SUCCEEDED, seeded=other_workspace)
        mine = await _stats(h, h.seeded, h.seeded.source_id)
        theirs = await _stats(h, other_workspace, other_workspace.source_id)

        assert mine is not None
        assert (mine["chunks"], mine["files"], mine["dominant"]) == (5, 2, [])
        assert theirs is not None
        assert (theirs["chunks"], theirs["files"]) == (500, 120)

    _with_database(app_database_url, body)
