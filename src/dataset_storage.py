from __future__ import annotations

from pathlib import Path


class LocalDatasetStorage:
    def put_file(self, local_path: str | Path) -> str:
        return str(local_path)

    def get_file(self, storage_uri: str) -> Path:
        return Path(storage_uri)

    def exists(self, storage_uri: str) -> bool:
        return Path(storage_uri).exists()


def dataset_storage_from_env() -> LocalDatasetStorage:
    return LocalDatasetStorage()
