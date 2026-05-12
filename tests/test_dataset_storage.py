from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from src.dataset_storage import (
    DatasetStorageConfig,
    LocalDatasetStorage,
    SupabaseDatasetStorage,
    dataset_storage_from_config,
    is_remote_storage_uri,
)


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


def test_dataset_storage_factory_defaults_to_local() -> None:
    assert isinstance(dataset_storage_from_config(DatasetStorageConfig()), LocalDatasetStorage)
    assert isinstance(dataset_storage_from_config(DatasetStorageConfig(mode="unknown")), LocalDatasetStorage)


def test_supabase_storage_requires_config() -> None:
    with pytest.raises(ValueError, match="supabase_url"):
        dataset_storage_from_config(DatasetStorageConfig(mode="supabase"))


def test_supabase_storage_builds_uri_and_upload_request(monkeypatch) -> None:
    tmp_path = _workspace_temp_dir()
    try:
        source = tmp_path / "tokyo.parquet"
        source.write_bytes(b"demo")
        requests_seen: list[tuple[str, str, dict[str, str], bytes]] = []

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

        def fake_request(method, url, *, headers, data, timeout):  # noqa: ANN001
            del timeout
            requests_seen.append((method, url, headers, data))
            return FakeResponse()

        monkeypatch.setattr("src.dataset_storage.requests.request", fake_request)

        storage = SupabaseDatasetStorage(
            supabase_url="https://project.supabase.co",
            service_role_key="service-key",
            bucket="aq-data",
        )

        uri = storage.put_file(source)

        assert uri == "supabase://aq-data/tokyo.parquet"
        assert requests_seen[0][0] == "POST"
        assert requests_seen[0][1] == "https://project.supabase.co/storage/v1/object/aq-data/tokyo.parquet"
        assert requests_seen[0][2]["authorization"] == "Bearer service-key"
        assert requests_seen[0][2]["x-upsert"] == "true"
        assert requests_seen[0][3] == b"demo"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_supabase_storage_downloads_to_cache(monkeypatch) -> None:
    tmp_path = _workspace_temp_dir()
    try:
        cache_dir = tmp_path / "cache"
        requests_seen: list[tuple[str, str]] = []

        class FakeResponse:
            content = b"cached"

            def raise_for_status(self) -> None:
                return None

        def fake_get(url, *, headers, timeout):  # noqa: ANN001
            del headers, timeout
            requests_seen.append(("GET", url))
            return FakeResponse()

        monkeypatch.setattr("src.dataset_storage.requests.get", fake_get)

        storage = SupabaseDatasetStorage(
            supabase_url="https://project.supabase.co/",
            service_role_key="service-key",
            bucket="aq-data",
            cache_dir=cache_dir,
        )

        local_path = storage.get_file("supabase://aq-data/agent_runs/tokyo.parquet")

        assert local_path == cache_dir / "aq-data" / "agent_runs" / "tokyo.parquet"
        assert local_path.read_bytes() == b"cached"
        assert requests_seen == [
            ("GET", "https://project.supabase.co/storage/v1/object/authenticated/aq-data/agent_runs/tokyo.parquet")
        ]
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_is_remote_storage_uri() -> None:
    assert is_remote_storage_uri("supabase://aq-data/tokyo.parquet")
    assert not is_remote_storage_uri("data/processed/tokyo.parquet")
