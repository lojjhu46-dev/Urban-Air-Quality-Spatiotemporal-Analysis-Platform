from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import quote

import requests


DEFAULT_DATASET_CACHE_DIR = Path(".cache/datasets")


@dataclass(frozen=True, slots=True)
class DatasetStorageConfig:
    mode: str | None = None
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str | None = None
    cache_dir: Path = DEFAULT_DATASET_CACHE_DIR


class DatasetStorage(Protocol):
    def put_file(self, local_path: str | Path) -> str: ...

    def get_file(self, storage_uri: str) -> Path: ...

    def exists(self, storage_uri: str) -> bool: ...


class LocalDatasetStorage:
    def put_file(self, local_path: str | Path) -> str:
        return str(local_path)

    def get_file(self, storage_uri: str) -> Path:
        return Path(storage_uri)

    def exists(self, storage_uri: str) -> bool:
        return Path(storage_uri).exists()


class SupabaseDatasetStorage:
    def __init__(
        self,
        *,
        supabase_url: str,
        service_role_key: str,
        bucket: str,
        cache_dir: str | Path = DEFAULT_DATASET_CACHE_DIR,
    ) -> None:
        if not supabase_url:
            raise ValueError("supabase_url is required for Supabase dataset storage.")
        if not service_role_key:
            raise ValueError("supabase_service_role_key is required for Supabase dataset storage.")
        if not bucket:
            raise ValueError("supabase_storage_bucket is required for Supabase dataset storage.")
        self.supabase_url = supabase_url.rstrip("/")
        self.service_role_key = service_role_key
        self.bucket = bucket
        self.cache_dir = Path(cache_dir)

    def put_file(self, local_path: str | Path) -> str:
        path = Path(local_path)
        object_key = _object_key_for_path(path)
        headers = self._headers()
        headers["content-type"] = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        headers["x-upsert"] = "true"
        response = requests.request(
            "POST",
            self._object_url(self.bucket, object_key),
            headers=headers,
            data=path.read_bytes(),
            timeout=120,
        )
        response.raise_for_status()
        return _supabase_uri(self.bucket, object_key)

    def get_file(self, storage_uri: str) -> Path:
        bucket, object_key = parse_supabase_storage_uri(storage_uri)
        local_path = self.cache_dir / bucket / Path(*PurePosixPath(object_key).parts)
        if local_path.exists():
            return local_path

        local_path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(
            self._authenticated_object_url(bucket, object_key),
            headers=self._headers(),
            timeout=120,
        )
        response.raise_for_status()
        local_path.write_bytes(response.content)
        return local_path

    def exists(self, storage_uri: str) -> bool:
        if not is_remote_storage_uri(storage_uri):
            return Path(storage_uri).exists()
        bucket, object_key = parse_supabase_storage_uri(storage_uri)
        response = requests.get(
            self._authenticated_object_url(bucket, object_key),
            headers=self._headers(),
            timeout=30,
        )
        return response.status_code == 200

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.service_role_key,
            "authorization": f"Bearer {self.service_role_key}",
        }

    def _object_url(self, bucket: str, object_key: str) -> str:
        return f"{self.supabase_url}/storage/v1/object/{quote(bucket)}/{_quote_object_key(object_key)}"

    def _authenticated_object_url(self, bucket: str, object_key: str) -> str:
        return f"{self.supabase_url}/storage/v1/object/authenticated/{quote(bucket)}/{_quote_object_key(object_key)}"


def dataset_storage_from_config(config: DatasetStorageConfig | None = None) -> DatasetStorage:
    config = config or DatasetStorageConfig()
    mode = (config.mode or "local").strip().casefold()
    if mode in {"supabase", "supabase_storage", "supabase-storage"}:
        return SupabaseDatasetStorage(
            supabase_url=(config.supabase_url or "").strip(),
            service_role_key=(config.supabase_service_role_key or "").strip(),
            bucket=(config.supabase_storage_bucket or "").strip(),
            cache_dir=config.cache_dir,
        )
    return LocalDatasetStorage()


def dataset_storage_from_env() -> DatasetStorage:
    return dataset_storage_from_config(
        DatasetStorageConfig(
            mode=_env("DATASET_STORAGE_MODE") or _env("dataset_storage_mode"),
            supabase_url=_env("SUPABASE_URL") or _env("supabase_url"),
            supabase_service_role_key=(
                _env("SUPABASE_SERVICE_ROLE_KEY")
                or _env("supabase_service_role_key")
                or _env("SUPABASE_SERVICE_KEY")
                or _env("supabase_service_key")
            ),
            supabase_storage_bucket=_env("SUPABASE_STORAGE_BUCKET") or _env("supabase_storage_bucket"),
            cache_dir=Path(_env("DATASET_STORAGE_CACHE_DIR") or _env("dataset_storage_cache_dir") or DEFAULT_DATASET_CACHE_DIR),
        )
    )


def is_remote_storage_uri(value: str | Path) -> bool:
    return str(value).startswith("supabase://")


def parse_supabase_storage_uri(storage_uri: str) -> tuple[str, str]:
    raw = storage_uri.removeprefix("supabase://")
    bucket, separator, object_key = raw.partition("/")
    if not bucket or not separator or not object_key:
        raise ValueError(f"Invalid Supabase storage URI: {storage_uri}")
    return bucket, object_key


def _supabase_uri(bucket: str, object_key: str) -> str:
    return f"supabase://{bucket}/{object_key}"


def _object_key_for_path(path: Path) -> str:
    return PurePosixPath(path.name).as_posix()


def _quote_object_key(object_key: str) -> str:
    return "/".join(quote(part) for part in PurePosixPath(object_key).parts)


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()
