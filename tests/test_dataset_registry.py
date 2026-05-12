from __future__ import annotations

from src.dataset_registry import DatasetIndexEntry, LocalDatasetRegistry, dataset_registry_from_config


def test_local_registry_adds_and_lists_entries() -> None:
    registry = LocalDatasetRegistry()
    entry = DatasetIndexEntry(
        city="Tokyo",
        country_code="JP",
        start_date="2024-01-01",
        end_date="2024-12-31",
        pollutants=["pm25", "o3"],
        row_count=1000,
        format="parquet",
        storage_uri="data/processed/agent_runs/tokyo.parquet",
        source_task_id="task-1",
    )

    registry.add_entry(entry)

    entries = registry.list_entries()
    assert entries == [entry]
    assert registry.find_by_uri("data/processed/agent_runs/tokyo.parquet") == entry


def test_local_registry_replaces_existing_entry_by_uri() -> None:
    registry = LocalDatasetRegistry()
    registry.add_entry(
        DatasetIndexEntry(
            city="Tokyo",
            country_code="JP",
            start_date="2024-01-01",
            end_date="2024-06-30",
            storage_uri="same.parquet",
        )
    )
    registry.add_entry(
        DatasetIndexEntry(
            city="Kyoto",
            country_code="JP",
            start_date="2024-01-01",
            end_date="2024-12-31",
            storage_uri="same.parquet",
        )
    )

    entries = registry.list_entries()
    assert len(entries) == 1
    assert entries[0].city == "Kyoto"


def test_dataset_registry_from_config_defaults_to_local() -> None:
    assert isinstance(dataset_registry_from_config(None), LocalDatasetRegistry)
    assert isinstance(dataset_registry_from_config(""), LocalDatasetRegistry)


def test_dataset_index_entry_serializes_to_dict() -> None:
    entry = DatasetIndexEntry(
        city="Berlin",
        country_code="DE",
        start_date="2023-01-01",
        end_date="2023-06-30",
        pollutants=["pm25", "pm10"],
        row_count=500,
        format="csv",
        storage_uri="berlin.csv",
        source_task_id="abc-123",
        created_at="2026-05-07T00:00:00+00:00",
    )

    assert entry.to_dict() == {
        "city": "Berlin",
        "country_code": "DE",
        "start_date": "2023-01-01",
        "end_date": "2023-06-30",
        "pollutants": ["pm25", "pm10"],
        "row_count": 500,
        "format": "csv",
        "storage_uri": "berlin.csv",
        "source_task_id": "abc-123",
        "created_at": "2026-05-07T00:00:00+00:00",
    }
