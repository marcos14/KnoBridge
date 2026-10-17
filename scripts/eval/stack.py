"""Preparation and cleanup of the evaluation resources on the stack, only through the panel
routes (docs/specs/avaliacao.md, "Preparação" and "Encerramento")."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

import httpx

from eval.client import ApiError, KnoBridgeClient, Upload
from eval.clock import Clock
from eval.config import FAKE_PROVIDER_KEY, INDEX_POLL_SECONDS, EvalConfig
from eval.jsonx import (
    as_object,
    get_list,
    get_opt_float,
    get_opt_int,
    get_opt_object,
    get_opt_str,
    get_str,
)
from eval.questions import LEVELS

Progress = Callable[[str], None]


class SetupError(Exception):
    """Preparation or indexing failed; the run stops with exit code 1."""


@dataclass(frozen=True)
class SourceSpec:
    suffix: str
    kind: str
    corpus_entry: str
    min_level: str | None


SOURCES = (
    SourceSpec("manual", "folder", "manual", None),
    SourceSpec("interno", "folder", "interno", "support"),
    SourceSpec("codigo", "folder", "codigo", "product_dev"),
    SourceSpec("chamados", "tickets", "chamados.jsonl", None),
    SourceSpec("cards", "cards", "cards.jsonl", None),
)


@dataclass
class Created:
    """What the run created or changed, so the cleanup knows what to undo."""

    provider_ids: list[str] = field(default_factory=list[str])
    collection_id: str | None = None
    source_ids: list[str] = field(default_factory=list[str])
    product_id: str | None = None
    api_key_id: str | None = None
    original_levels: dict[str, dict[str, object]] = field(
        default_factory=dict[str, dict[str, object]]
    )


@dataclass(frozen=True)
class Prepared:
    product: dict[str, object]
    levels: dict[str, dict[str, object]]
    api_key: str
    index: list[dict[str, object]]


def _create_provider(
    client: KnoBridgeClient, created: Created, name: str, kind: str, key: str | None
) -> str:
    body: dict[str, object] = {
        "name": name,
        "kind": kind,
        "api_key": FAKE_PROVIDER_KEY if key is None else key,
    }
    provider_id = get_str(client.create("providers", body), "id", "$")
    created.provider_ids.append(provider_id)
    return provider_id


def _create_providers(
    client: KnoBridgeClient, config: EvalConfig, created: Created
) -> tuple[str, str]:
    chat_id = _create_provider(
        client, created, f"{config.prefix}-chat", config.chat_provider, config.chat_key
    )
    if config.embedding_provider == config.chat_provider and config.embedding_key is None:
        return chat_id, chat_id
    embedding_id = _create_provider(
        client,
        created,
        f"{config.prefix}-embedding",
        config.embedding_provider,
        config.embedding_key,
    )
    return chat_id, embedding_id


def _start_folder(client: KnoBridgeClient, source_id: str) -> str:
    try:
        return get_str(client.post(f"sources/{source_id}/sync"), "id", "$")
    except ApiError as error:
        if error.code != "sync_already_running":
            raise
        last_run = get_opt_object(client.get(f"sources/{source_id}"), "last_run", "$")
        if last_run is None:
            raise
        return get_str(last_run, "id", "$.last_run")


def _start_source(
    client: KnoBridgeClient, config: EvalConfig, spec: SourceSpec, source_id: str
) -> str:
    """Start the first sync of a source and return its run id."""
    if spec.kind == "folder":
        return _start_folder(client, source_id)
    path = config.corpus_dir / spec.corpus_entry
    result = client.upload(
        f"sources/{source_id}/{spec.kind}/upload", Upload(spec.corpus_entry, path.read_bytes())
    )
    counts = as_object(result.get("counts"), "$.counts")
    rejected = get_opt_int(counts, "rejected", "$.counts") or 0
    run_id = get_opt_str(result, "run_id", "$")
    if rejected or run_id is None:
        sync = get_opt_str(result, "sync", "$")
        raise SetupError(f"upload of {spec.corpus_entry} rejected {rejected} item(s), sync {sync}")
    return run_id


def _create_sources(
    client: KnoBridgeClient, config: EvalConfig, created: Created, collection_id: str
) -> dict[str, tuple[SourceSpec, str]]:
    runs: dict[str, tuple[SourceSpec, str]] = {}
    for spec in SOURCES:
        source_config: dict[str, object] = {}
        if spec.kind == "folder":
            source_config["path"] = f"{config.sources_root.rstrip('/')}/{spec.corpus_entry}"
        body: dict[str, object] = {
            "collection_id": collection_id,
            "kind": spec.kind,
            "name": f"{config.prefix}-{spec.suffix}",
            "config": source_config,
        }
        if spec.min_level is not None:
            body["min_level"] = spec.min_level
        source_id = get_str(client.create("sources", body), "id", "$")
        created.source_ids.append(source_id)
        runs[source_id] = (spec, _start_source(client, config, spec, source_id))
    return runs


def _wait_for_index(
    client: KnoBridgeClient,
    config: EvalConfig,
    runs: dict[str, tuple[SourceSpec, str]],
    clock: Clock,
    progress: Progress,
) -> dict[str, dict[str, object]]:
    deadline = clock.monotonic() + config.index_timeout
    pending = dict(runs)
    finished: dict[str, dict[str, object]] = {}
    while True:
        for source_id, (spec, run_id) in list(pending.items()):
            run = client.get(f"runs/{run_id}")
            status = get_str(run, "status", "$")
            if status == "succeeded":
                finished[source_id] = run
                del pending[source_id]
                progress(f"indexed {config.prefix}-{spec.suffix}")
            elif status in ("failed", "cancelled"):
                error = get_opt_str(run, "error", "$") or "no detail"
                raise SetupError(f"indexing of {config.prefix}-{spec.suffix} {status}: {error}")
        if not pending:
            return finished
        if clock.monotonic() >= deadline:
            names = ", ".join(f"{config.prefix}-{spec.suffix}" for spec, _ in pending.values())
            raise SetupError(f"indexing did not finish in {config.index_timeout:g} s: {names}")
        clock.sleep(INDEX_POLL_SECONDS)


def _index_entry(source: dict[str, object], run: dict[str, object]) -> dict[str, object]:
    stats = get_opt_object(source, "index_stats", "$")
    dominant: list[dict[str, object]] = []
    chunks = get_opt_int(run, "chunks_written", "$")
    if stats is not None:
        chunks = get_opt_int(stats, "chunks", "$.index_stats")
        for i, raw in enumerate(get_list(stats, "dominant", "$.index_stats")):
            path = f"$.index_stats.dominant[{i}]"
            group = as_object(raw, path)
            dominant.append(
                {
                    "kind": get_str(group, "kind", path),
                    "pattern": get_str(group, "pattern", path),
                    "share": get_opt_float(group, "share", path),
                }
            )
    return {
        "name": get_str(source, "name", "$"),
        "kind": get_str(source, "kind", "$"),
        "documents": get_opt_int(source, "document_count", "$"),
        "chunks": chunks,
        "dominant": dominant,
    }


def _configure_levels(
    client: KnoBridgeClient, config: EvalConfig, created: Created, provider_id: str
) -> dict[str, dict[str, object]]:
    for i, raw in enumerate(get_list(client.get("levels"), "items", "$")):
        item = as_object(raw, f"$.items[{i}]")
        created.original_levels[get_str(item, "level", f"$.items[{i}]")] = {
            "provider_id": item.get("provider_id"),
            "model": item.get("model"),
            "temperature": item.get("temperature"),
            "max_steps": item.get("max_steps", 1),
        }
    effective: dict[str, dict[str, object]] = {}
    for level in LEVELS:
        body: dict[str, object] = {"provider_id": provider_id, "model": config.models[level]}
        if level in config.max_steps:
            body["max_steps"] = config.max_steps[level]
        updated = client.patch(f"levels/{level}", body)
        effective[level] = {
            "model": get_opt_str(updated, "model", "$"),
            "max_steps": get_opt_int(updated, "max_steps", "$"),
        }
    return effective


def prepare(
    client: KnoBridgeClient, config: EvalConfig, created: Created, clock: Clock, progress: Progress
) -> Prepared:
    client.login(config.email, config.password)
    chat_id, embedding_id = _create_providers(client, config, created)
    collection = client.create(
        "collections",
        {
            "name": config.prefix,
            "provider_id": embedding_id,
            "embedding_model": config.embedding_model,
        },
    )
    collection_id = get_str(collection, "id", "$")
    created.collection_id = collection_id
    runs = _create_sources(client, config, created, collection_id)
    progress(f"waiting for {len(runs)} sources to index")
    finished = _wait_for_index(client, config, runs, clock, progress)
    index = [
        _index_entry(client.get(f"sources/{source_id}"), finished[source_id])
        for source_id in created.source_ids
    ]
    product = client.create(
        "products",
        {
            "name": config.prefix,
            "collection_ids": [collection_id],
            "rerank": config.rerank,
            "min_similarity": config.min_similarity,
        },
    )
    created.product_id = get_str(product, "id", "$")
    levels = _configure_levels(client, config, created, chat_id)
    key = client.create(
        "api-keys",
        {"name": config.prefix, "product_ids": [created.product_id], "max_level": "product_dev"},
    )
    created.api_key_id = get_str(as_object(key.get("api_key"), "$.api_key"), "id", "$.api_key")
    return Prepared(product=product, levels=levels, api_key=get_str(key, "key", "$"), index=index)


def _attempt(progress: Progress, what: str, action: Callable[[], object]) -> None:
    try:
        action()
    except (ApiError, ValueError, httpx.HTTPError) as error:
        progress(f"cleanup: could not {what}: {error}")


def teardown(
    client: KnoBridgeClient, config: EvalConfig, created: Created, progress: Progress
) -> None:
    """Undo what ``prepare`` did; every step runs even when an earlier one fails."""
    if created.api_key_id is not None:
        revoke = f"api-keys/{created.api_key_id}/revoke"
        _attempt(progress, "revoke the API key", partial(client.post, revoke))
    for level, body in created.original_levels.items():
        _attempt(
            progress, f"restore the level {level}", partial(client.patch, f"levels/{level}", body)
        )
    if not config.cleanup:
        return
    targets: list[tuple[str, str]] = []
    if created.product_id is not None:
        targets.append(("the product", f"products/{created.product_id}"))
    targets += [("a source", f"sources/{source_id}") for source_id in created.source_ids]
    if created.collection_id is not None:
        targets.append(("the collection", f"collections/{created.collection_id}"))
    targets += [("a credential", f"providers/{pid}") for pid in created.provider_ids]
    for what, resource in targets:
        _attempt(progress, f"delete {what}", partial(client.delete, resource))
