"""Build the connector of a ``Source`` from its kind, validated config and globs.

The ingestion engine depends on ``ConnectorFactory`` (not on the concrete connectors), so tests
inject a factory that returns an in-memory connector and no filesystem or Git is touched.
"""

from __future__ import annotations

from typing import Protocol

from knobridge.connectors.base import Connector
from knobridge.connectors.folder.connector import create_folder_connector
from knobridge.connectors.git.connector import create_git_connector
from knobridge.core.settings import Settings
from knobridge.ingestion.models import Source
from knobridge.ingestion.source_config import FolderSourceConfig


class ConnectorFactory(Protocol):
    def __call__(self, source: Source) -> Connector: ...


class SettingsConnectorFactory:
    """The production factory: roots and size limits come from settings."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def __call__(self, source: Source) -> Connector:
        config = source.typed_config()
        globs = {
            "include_globs": tuple(source.include_globs),
            "exclude_globs": tuple(source.exclude_globs),
        }
        if isinstance(config, FolderSourceConfig):
            return create_folder_connector(config, self._settings, **globs)
        return create_git_connector(config, self._settings, **globs)
