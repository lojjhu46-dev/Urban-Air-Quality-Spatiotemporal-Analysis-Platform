from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from src.dataset_storage import LocalDatasetStorage, dataset_storage_from_env


def _workspace_temp_dir() -> Path:
    root = Path.cwd() / "pytest-cache-files-dataset-storage"
    root.mkdir(exist_ok=True)
    path = root / f"case-{uuid.uuid4().hex}"
    path.mkdir()
    return path


def test_local_storage_keeps_existing_path() -> None:
    tmp_path = _workspace_temp_dir()
    try:
        source = tmp_path / "tokyo.parquet"
        source.write_bytes(b"demo")
        storage = LocalDatasetStorage()

        assert storage.put_file(source) == str(source)
        assert storage.get_file(str(source)) == source
        assert storage.exists(str(source))
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_dataset_storage_from_env_is_local() -> None:
    assert isinstance(dataset_storage_from_env(), LocalDatasetStorage)
