"""Provider-neutral seams for persistence, search, jobs, and durable files."""

from research_navigator.data_plane.database import DatabaseDialect, database_dialect
from research_navigator.data_plane.storage import (
    Boto3R2Transport,
    LocalStorage,
    R2Storage,
    StorageKeyError,
    build_storage,
)

__all__ = [
    "DatabaseDialect",
    "LocalStorage",
    "Boto3R2Transport",
    "R2Storage",
    "StorageKeyError",
    "build_storage",
    "database_dialect",
]
