"""Folder connector: the files of a local folder, incremental by content hash."""

from knobridge.connectors.folder.connector import FolderConnector, create_folder_connector

__all__ = ["FolderConnector", "create_folder_connector"]
