"""The ingestion workflow end to end: Temporal test server, real Postgres, in-memory connector
and the recording fake embedding provider."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest
from ingestion_harness import API_KEY, MODEL, START, Harness, harness
from sqlalchemy import func, select, update
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import CancelledError

from fakes.embedding_provider import RecordingEmbeddingProvider
from knobridge.ingestion.errors import SyncAlreadyRunningError, SyncNotRunningError
from knobridge.ingestion.models import Run, RunErrorStage, RunStatus, Source
from knobridge.llm.errors import ProviderAuthError, ProviderUnavailableError
from knobridge.llm.fake_embeddings import normalized_words
from knobridge.llm.pricing import EmbeddingPriceTable
from knobridge.workers.ingestion import BATCH_SIZE

pytestmark = pytest.mark.integration

FILES = {
    "guia/senha.txt": b"Para trocar a senha, abra o menu Perfil e escolha Seguranca.",
    "faturamento.txt": b"O erro 42 no faturamento indica nota fiscal sem cliente.",
}

type Body = Callable[[Harness], Awaitable[None]]


def _scenario(
    database_url: str,
    files: dict[str, bytes],
    body: Body,
    *,
    batch_size: int = BATCH_SIZE,
    model: str = MODEL,
) -> None:
    async def main() -> None:
        async with harness(database_url, files, batch_size=batch_size, model=model) as h:
            await body(h)

    asyncio.run(main())


def _long_text(last_line: str) -> bytes:
    lines = [f"Linha {index}: o faturamento consulta a tabela de clientes." for index in range(80)]
    return "\n".join([*lines, last_line]).encode()


def test_ingestion_indexes_new_documents(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        run = await h.sync()
        documents = await h.documents()
        chunks = await h.chunks()
        source = await h.source()

        assert (run.status, run.documents_new, run.documents_changed) == (
            RunStatus.SUCCEEDED,
            2,
            0,
        )
        assert (run.started_at, run.finished_at, run.error) == (START, START, None)
        assert run.chunks_written == len(chunks) == 2
        assert set(documents) == set(FILES)
        assert {doc.indexed_at for doc in documents.values()} == {START}
        assert documents["faturamento.txt"].uri == "fake://faturamento.txt"
        assert {chunk.embedding_model for chunk in chunks} == {MODEL}
        assert all(chunk.content.startswith("path: ") for chunk in chunks)
        displays = sorted(str(chunk.meta["display"]) for chunk in chunks)
        assert displays == sorted(text.decode() for text in FILES.values())
        assert source.cursor is not None
        assert await h.items(run.id) == []
        assert set(h.sources_seen) == {h.seeded.source_id}

    _scenario(app_database_url, FILES, body)


def test_ingestion_reprocesses_only_changed(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        await h.sync()
        first_ids = {key: doc.id for key, doc in (await h.documents()).items()}
        h.connector.fetched.clear()
        h.connector.put("faturamento.txt", b"O erro 43 no faturamento indica cliente bloqueado.")

        run = await h.sync()
        documents = await h.documents()

        assert (run.documents_new, run.documents_changed) == (0, 1)
        assert h.connector.fetched == ["faturamento.txt"]
        assert {key: doc.id for key, doc in documents.items()} == first_ids
        assert any("erro 43" in chunk.content for chunk in await h.chunks())

    _scenario(app_database_url, FILES, body)


def test_ingestion_skips_listed_documents_with_unchanged_hash(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        await h.sync()
        async with h.session() as db:
            await db.execute(
                update(Source).where(Source.id == h.seeded.source_id).values(cursor=None)
            )
        embedded = len(h.embeddings.provider.texts)

        run = await h.sync()

        assert (run.documents_new, run.documents_changed, run.chunks_written) == (0, 0, 0)
        assert len(h.embeddings.provider.texts) == embedded

    _scenario(app_database_url, FILES, body)


def test_ingestion_removes_deleted_documents(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        await h.sync()
        h.connector.delete("guia/senha.txt")

        run = await h.sync()
        documents = await h.documents()
        chunks = await h.chunks()

        assert (run.status, run.documents_removed) == (RunStatus.SUCCEEDED, 1)
        assert set(documents) == {"faturamento.txt"}
        assert {chunk.document_id for chunk in chunks} == {documents["faturamento.txt"].id}

    _scenario(app_database_url, FILES, body)


def test_ingestion_reuses_embedding_cache_by_chunk_hash(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        await h.sync()
        before = {chunk.content_hash: list(chunk.embedding) for chunk in await h.chunks()}
        provider = h.embeddings.provider
        provider.texts.clear()
        h.connector.put("longo.txt", _long_text("Linha final: texto novo sobre estoque."))

        run = await h.sync()
        after = await h.chunks()

        reused = [chunk for chunk in after if chunk.content_hash in before]
        assert len(before) >= 3
        assert reused
        assert len(provider.texts) == len(after) - len(reused)
        assert all(list(chunk.embedding) == before[chunk.content_hash] for chunk in reused)
        assert run.documents_changed == 1

    _scenario(app_database_url, {"longo.txt": _long_text("Linha final: texto original.")}, body)


def test_ingestion_fully_cached_document_skips_provider(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        await h.sync()
        calls = h.embeddings.provider.calls
        # New raw bytes (new hash), but trailing blank lines do not reach any chunk.
        h.connector.put("faturamento.txt", FILES["faturamento.txt"] + b"\n\n\n")

        run = await h.sync()

        assert (run.documents_changed, run.chunks_written, run.embedding_tokens) == (1, 1, 0)
        assert h.embeddings.provider.calls == calls

    _scenario(app_database_url, FILES, body)


def test_ingestion_document_error_recorded_and_run_continues(app_database_url: str) -> None:
    files = {**FILES, "binario.dat": b"\x00\x01\x02", "sumiu.txt": b"vai sumir"}

    async def body(h: Harness) -> None:
        h.connector.missing.add("sumiu.txt")

        run = await h.sync()
        errors = sorted(await h.errors(run.id), key=lambda error: error.document_key)

        assert (run.status, run.documents_new, run.documents_failed) == (
            RunStatus.SUCCEEDED,
            2,
            2,
        )
        assert [(e.document_key, e.stage, e.code) for e in errors] == [
            ("binario.dat", RunErrorStage.PARSE, "unsupported_format"),
            ("sumiu.txt", RunErrorStage.FETCH, "document_not_found"),
        ]
        assert set(await h.documents()) == set(FILES)

    _scenario(app_database_url, files, body)


def test_ingestion_cursor_saved_only_on_success(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        provider = h.embeddings.provider
        provider.error = ProviderAuthError("The provider refused the key.", provider="fake")

        failed = await h.sync()
        source_after_failure = await h.source()
        items_after_failure = await h.items(failed.id)
        provider.error = None
        succeeded = await h.sync()

        assert failed.status is RunStatus.FAILED
        assert failed.error == "provider_auth_failed: The provider refused the key."
        assert failed.finished_at == START
        assert (failed.pending_cursor, source_after_failure.cursor) == (None, None)
        assert items_after_failure == []
        assert provider.calls == 2  # one failed call (not retried: permanent) + the rerun
        assert succeeded.status is RunStatus.SUCCEEDED
        assert (await h.source()).cursor is not None

    _scenario(app_database_url, FILES, body)


def test_ingestion_retries_transient_provider_failure(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        h.embeddings.provider = RecordingEmbeddingProvider(
            ProviderUnavailableError("The provider is unavailable.", provider="fake"),
            fail_times=1,
        )

        run = await h.sync()

        assert (run.status, run.documents_new) == (RunStatus.SUCCEEDED, 2)
        assert h.embeddings.provider.calls == 2

    _scenario(app_database_url, FILES, body)


def test_ingestion_cancel_marks_cancelled(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        h.connector.gate = asyncio.Event()
        run = await h.start()
        await h.connector.fetch_started.wait()

        await h.starter.cancel(h.seeded.source_id)
        with pytest.raises(WorkflowFailureError) as failure:
            await h.handle().result()
        cancelled = await h.run(run.id)

        assert isinstance(failure.value.cause, CancelledError)
        assert cancelled.status is RunStatus.CANCELLED
        assert cancelled.finished_at == START
        assert (await h.source()).cursor is None
        assert await h.items(run.id) == []

    _scenario(app_database_url, FILES, body)


def test_ingestion_cancel_without_running_sync_is_refused(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        with pytest.raises(SyncNotRunningError):
            await h.starter.cancel(h.seeded.source_id)

    _scenario(app_database_url, FILES, body)


def test_ingestion_single_run_per_source(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        h.connector.gate = asyncio.Event()
        first = await h.start()
        await h.connector.fetch_started.wait()

        with pytest.raises(SyncAlreadyRunningError):
            await h.start()
        async with h.session() as db:
            runs = await db.scalar(
                select(func.count()).select_from(Run).where(Run.source_id == h.seeded.source_id)
            )
        h.connector.gate.set()
        result = await h.handle().result()
        second = await h.sync()

        assert runs == 1
        assert result == "succeeded"
        assert (await h.run(first.id)).status is RunStatus.SUCCEEDED
        assert second.status is RunStatus.SUCCEEDED

    _scenario(app_database_url, FILES, body)


def test_ingestion_records_tokens_and_cost(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        run = await h.sync()
        texts = h.embeddings.provider.texts
        tokens = sum(max(1, len(normalized_words(text))) for text in texts)

        assert run.embedding_tokens == tokens
        assert tokens > 0
        assert run.cost_usd == EmbeddingPriceTable().cost(MODEL, tokens)
        assert h.embeddings.calls[0].api_key == API_KEY
        assert h.embeddings.provider.models == [MODEL]
        assert h.embeddings.provider.closed == 1

    _scenario(app_database_url, FILES, body)


def test_ingestion_cost_unknown_for_unpriced_model(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        run = await h.sync()

        assert run.embedding_tokens > 0
        assert run.cost_usd is None

    _scenario(app_database_url, FILES, body, model="modelo-sem-preco")


def test_ingestion_processes_documents_in_batches(app_database_url: str) -> None:
    files = {f"doc{index}.txt": f"Documento numero {index}".encode() for index in range(5)}

    async def body(h: Harness) -> None:
        run = await h.sync()

        assert (run.status, run.documents_new, run.chunks_written) == (RunStatus.SUCCEEDED, 5, 5)
        assert h.embeddings.provider.calls == 3

    _scenario(app_database_url, files, body, batch_size=2)
