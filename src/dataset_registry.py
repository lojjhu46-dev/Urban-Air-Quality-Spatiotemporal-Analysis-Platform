from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class DatasetIndexEntry:
    city: str
    country_code: str
    start_date: str
    end_date: str
    pollutants: list[str] = field(default_factory=list)
    row_count: int = 0
    format: str = "parquet"
    storage_uri: str = ""
    source_task_id: str | None = None
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "city": self.city,
            "country_code": self.country_code,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "pollutants": list(self.pollutants),
            "row_count": self.row_count,
            "format": self.format,
            "storage_uri": self.storage_uri,
            "source_task_id": self.source_task_id,
            "created_at": self.created_at,
        }


class DatasetRegistry(Protocol):
    def add_entry(self, entry: DatasetIndexEntry) -> None: ...

    def list_entries(self) -> list[DatasetIndexEntry]: ...

    def find_by_uri(self, storage_uri: str) -> DatasetIndexEntry | None: ...


class LocalDatasetRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, DatasetIndexEntry] = {}

    def add_entry(self, entry: DatasetIndexEntry) -> None:
        self._entries[entry.storage_uri] = entry

    def list_entries(self) -> list[DatasetIndexEntry]:
        return list(self._entries.values())

    def find_by_uri(self, storage_uri: str) -> DatasetIndexEntry | None:
        return self._entries.get(storage_uri)


class PostgresDatasetRegistry:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        try:
            import psycopg  # type: ignore[import-not-found]
            from psycopg.rows import dict_row  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Install `psycopg[binary]` to use Supabase Postgres dataset registry.") from exc
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _jsonb(self, payload: list[str]):
        try:
            from psycopg.types.json import Jsonb  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Install `psycopg[binary]` to use Supabase Postgres dataset registry.") from exc
        return Jsonb(payload)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(DATASET_INDEX_SCHEMA_SQL)

    def add_entry(self, entry: DatasetIndexEntry) -> None:
        self.ensure_schema()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into dataset_index (
                        city, country_code, start_date, end_date, pollutants,
                        row_count, format, storage_uri, source_task_id, created_at
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    on conflict (storage_uri) do update set
                        city = excluded.city,
                        country_code = excluded.country_code,
                        start_date = excluded.start_date,
                        end_date = excluded.end_date,
                        pollutants = excluded.pollutants,
                        row_count = excluded.row_count,
                        format = excluded.format,
                        source_task_id = excluded.source_task_id
                    """,
                    (
                        entry.city,
                        entry.country_code,
                        entry.start_date,
                        entry.end_date,
                        self._jsonb(list(entry.pollutants)),
                        int(entry.row_count),
                        entry.format,
                        entry.storage_uri,
                        entry.source_task_id,
                    ),
                )

    def list_entries(self) -> list[DatasetIndexEntry]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select * from dataset_index order by created_at desc")
                rows = cursor.fetchall()
        return [_entry_from_row(dict(row)) for row in rows]

    def find_by_uri(self, storage_uri: str) -> DatasetIndexEntry | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select * from dataset_index where storage_uri = %s", (storage_uri,))
                row = cursor.fetchone()
        return _entry_from_row(dict(row)) if row is not None else None


def dataset_registry_from_config(database_url: str | None = None) -> DatasetRegistry:
    if database_url and database_url.strip():
        return PostgresDatasetRegistry(database_url.strip())
    return LocalDatasetRegistry()


def _entry_from_row(row: dict[str, Any]) -> DatasetIndexEntry:
    pollutants = row.get("pollutants") or []
    if isinstance(pollutants, str):
        try:
            pollutants = json.loads(pollutants)
        except json.JSONDecodeError:
            pollutants = []

    return DatasetIndexEntry(
        city=str(row.get("city") or ""),
        country_code=str(row.get("country_code") or ""),
        start_date=str(row.get("start_date") or ""),
        end_date=str(row.get("end_date") or ""),
        pollutants=[str(item) for item in list(pollutants)],
        row_count=int(row.get("row_count") or 0),
        format=str(row.get("format") or "parquet"),
        storage_uri=str(row.get("storage_uri") or ""),
        source_task_id=row.get("source_task_id"),
        created_at=str(row.get("created_at") or ""),
    )


DATASET_INDEX_SCHEMA_SQL = """
create table if not exists dataset_index (
    id bigserial primary key,
    city text not null default '',
    country_code text not null default '',
    start_date text not null default '',
    end_date text not null default '',
    pollutants jsonb not null default '[]'::jsonb,
    row_count integer not null default 0,
    format text not null default 'parquet',
    storage_uri text not null,
    source_task_id text,
    created_at timestamptz not null default now(),
    constraint dataset_index_storage_uri_unique unique (storage_uri)
);

create index if not exists idx_dataset_index_city
    on dataset_index(city, country_code);

create index if not exists idx_dataset_index_created
    on dataset_index(created_at desc);
"""
