"""``SettingsConnectorFactory``: the connector of a source by kind, with the source's globs."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest

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


def test_connector_factory_refuses_runner_source(tmp_path: Path) -> None:
    factory = SettingsConnectorFactory(Settings(env="test", local_sources_root=tmp_path))
    source = _source(SourceKind.RUNNER, {"runner_id": str(uuid.uuid4()), "repository": "erp"})

    with pytest.raises(SourceUnavailableError) as raised:
        factory(source)

    assert raised.value.details == {"kind": "runner"}
