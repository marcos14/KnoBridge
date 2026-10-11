"""Build the connector of a ``Source`` from its kind, validated config and globs.

The ingestion engine depends on ``ConnectorFactory`` (not on the concrete connectors), so tests
inject a factory that returns an in-memory connector and no filesystem or Git is touched.
Runner sources are served by the internal ``knowledge`` connector (``harness/``), which the
caller hands in: it reads the database, and this module does not import the harness.
"""

from __future__ import annotations

from typing import Protocol, cast

from knobridge.connectors.base import Connector
from knobridge.connectors.errors import SourceUnavailableError
from knobridge.connectors.folder.connector import create_folder_connector
from knobridge.connectors.git.connector import create_git_connector
from knobridge.core.settings import Settings
from knobridge.ingestion.models import Source
from knobridge.ingestion.source_config import FolderSourceConfig, GitSourceConfig, SourceKind


class ConnectorFactory(Protocol):
    def __call__(self, source: Source) -> Connector: ...


class SettingsConnectorFactory:
    """The production factory: roots and size limits come from settings; ``knowledge`` builds
    the connector of runner sources."""

    def __init__(self, settings: Settings, *, knowledge: ConnectorFactory | None = None) -> None:
        self._settings = settings
        self._knowledge = knowledge

    def __call__(self, source: Source) -> Connector:
        if source.kind == SourceKind.RUNNER:
            # The config of a runner source is the runner's business: the knowledge items are
            # read from the database whatever it says, so it is not validated here.
            if self._knowledge is None:
                raise SourceUnavailableError("runner sources are not indexed here")
            return self._knowledge(source)
        config = source.typed_config()
        globs = {
            "include_globs": tuple(source.include_globs),
            "exclude_globs": tuple(source.exclude_globs),
        }
        if isinstance(config, FolderSourceConfig):
            return create_folder_connector(config, self._settings, **globs)
        # Runner sources returned above, so only Git is left.
        return create_git_connector(cast(GitSourceConfig, config), self._settings, **globs)
