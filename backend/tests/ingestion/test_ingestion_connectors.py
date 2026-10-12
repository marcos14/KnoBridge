"""``SettingsConnectorFactory``: the connector of a source by kind, with the source's globs."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest

from fakes.connector import FakeConnector
from knobridge.connectors.base import Connector
from knobridge.connectors.errors import SourceUnavailableError
from knobridge.connectors.folder.connector import FolderConnector
from knobridge.connectors.git.connector import GitConnector
from knobridge.core.settings import Settings
from knobridge.ingestion.connectors import SettingsConnectorFactory
from knobridge.ingestion.models import Source
from knobridge.ingestion.source_config import SourceKind


def _source(kind: SourceKind, config: dict[str, object], **globs: list[str]) -> Source:
    return Source(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        kind=kind,
        name="Fonte",
        config=config,
        include_globs=globs.get("include", []),
        exclude_globs=globs.get("exclude", []),
    )


def test_connector_factory_builds_folder_connector_with_source_globs(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    for name in ("leia.md", "notas.txt", "rascunho.md"):
        (docs / name).write_text("conteudo", encoding="utf-8")
    factory = SettingsConnectorFactory(Settings(env="test", local_sources_root=tmp_path))
    source = _source(
        SourceKind.FOLDER, {"path": str(docs)}, include=["*.md"], exclude=["rascunho.md"]
    )

    connector = factory(source)
    changes = asyncio.run(connector.list_changes(None))

    assert isinstance(connector, FolderConnector)
    assert [ref.key for ref in changes.added] == ["leia.md"]


def test_connector_factory_builds_git_connector(tmp_path: Path) -> None:
    factory = SettingsConnectorFactory(Settings(env="test", local_sources_root=tmp_path))

    connector = factory(_source(SourceKind.GIT, {"url": "https://example.test/repo.git"}))

    assert isinstance(connector, GitConnector)


def test_connector_factory_serves_runner_sources_with_the_knowledge_connector(
    tmp_path: Path,
) -> None:
    built: list[Source] = []
    fake = FakeConnector()

    def knowledge(source: Source) -> Connector:
        built.append(source)
        return fake

    factory = SettingsConnectorFactory(
        Settings(env="test", local_sources_root=tmp_path), knowledge=knowledge
    )
    # Not a config any parser accepts: the runner's config is never validated here.
    source = _source(SourceKind.RUNNER, {"anything": True})

    assert factory(source) is fake
    assert built == [source]


def test_connector_factory_without_knowledge_refuses_runner_sources(tmp_path: Path) -> None:
    factory = SettingsConnectorFactory(Settings(env="test", local_sources_root=tmp_path))

    with pytest.raises(SourceUnavailableError):
        factory(_source(SourceKind.RUNNER, {}))


def test_connector_factory_serves_tickets_sources_with_the_tickets_connector(
    tmp_path: Path,
) -> None:
    built: list[Source] = []
    fake = FakeConnector()

    def tickets(source: Source) -> Connector:
        built.append(source)
        return fake

    factory = SettingsConnectorFactory(
        Settings(env="test", local_sources_root=tmp_path), tickets=tickets
    )
    source = _source(SourceKind.TICKETS, {})

    assert factory(source) is fake
    assert built == [source]


def test_connector_factory_without_tickets_refuses_tickets_sources(tmp_path: Path) -> None:
    def knowledge(source: Source) -> Connector:
        return FakeConnector()

    factory = SettingsConnectorFactory(
        Settings(env="test", local_sources_root=tmp_path), knowledge=knowledge
    )

    with pytest.raises(SourceUnavailableError, match="tickets"):
        factory(_source(SourceKind.TICKETS, {}))
