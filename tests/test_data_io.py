from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pandas as pd

import src.data as data


def _workspace_temp_dir() -> Path:
    root = Path.cwd() / "pytest-cache-files-data-io"
    root.mkdir(exist_ok=True)
    path = root / f"case-{uuid.uuid4().hex}"
    path.mkdir()
    return path


def test_output_dataset_path_falls_back_to_csv(monkeypatch) -> None:
    monkeypatch.setattr(data, "parquet_engine_available", lambda: False)
    tmp_path = _workspace_temp_dir()
    try:
        target = data.output_dataset_path(tmp_path / "sample.parquet")
        assert target.suffix == ".csv"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_write_dataset_uses_csv_when_parquet_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(data, "parquet_engine_available", lambda: False)
    tmp_path = _workspace_temp_dir()
    try:
        frame = pd.DataFrame({"timestamp": ["2024-01-01T00:00:00+08:00"], "station_id": ["A"], "pm25": [12.0]})
        written = data.write_dataset(frame, tmp_path / "collected.parquet")

        assert written.suffix == ".csv"
        assert written.exists()
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_load_dataset_reads_csv_and_normalizes_timestamp(monkeypatch) -> None:
    monkeypatch.setattr(data, "parquet_engine_available", lambda: False)
    tmp_path = _workspace_temp_dir()
    try:
        csv_path = tmp_path / "demo.csv"
        pd.DataFrame(
            {
                "timestamp": ["2024-01-01T00:00:00+08:00", "2024-01-01T01:00:00+08:00"],
                "station_id": ["A", "A"],
                "pm25": [12.0, 18.0],
            }
        ).to_csv(csv_path, index=False)

        loaded = data.load_dataset(csv_path)

        assert str(loaded["timestamp"].dt.tz) == data.TIMEZONE
        assert list(loaded["pm25"].astype(float)) == [12.0, 18.0]
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
