from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("scripts/supabase_smoke_test.py")


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("supabase_smoke_test", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["supabase_smoke_test"] = module
    spec.loader.exec_module(module)
    return module


def test_script_runs_without_src_import_error() -> None:
    env = os.environ.copy()
    for key in (
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_STORAGE_BUCKET",
    ):
        env.pop(key, None)

    result = subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT_PATH)],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 2
    assert "Missing required environment variables:" in result.stderr


def test_validate_env_reports_missing_required_values(monkeypatch) -> None:
    smoke = _load_smoke_module()
    for key in smoke.REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(SystemExit) as exc:
        smoke.validate_env()

    assert exc.value.code == 2


def test_validate_env_returns_config(monkeypatch) -> None:
    smoke = _load_smoke_module()
    values = {
        "DATABASE_URL": "postgresql://example",
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-key",
        "SUPABASE_STORAGE_BUCKET": "aq-datasets",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    config = smoke.validate_env()

    assert config.database_url == "postgresql://example"
    assert config.supabase_url == "https://project.supabase.co"
    assert config.bucket == "aq-datasets"


def test_smoke_test_runs_schema_storage_and_registry_checks(monkeypatch) -> None:
    smoke = _load_smoke_module()
    calls: list[str] = []

    class FakeStore:
        def __init__(self, database_url: str) -> None:
            assert database_url == "postgresql://example"

        def ensure_schema(self) -> None:
            calls.append("ensure_task_schema")

    class FakeRegistry:
        def __init__(self, database_url: str) -> None:
            assert database_url == "postgresql://example"
            self.entry = None

        def ensure_schema(self) -> None:
            calls.append("ensure_registry_schema")

        def add_entry(self, entry) -> None:  # noqa: ANN001
            calls.append("add_entry")
            self.entry = entry

        def find_by_uri(self, storage_uri: str):  # noqa: ANN001
            calls.append("find_by_uri")
            assert self.entry.storage_uri == storage_uri
            return self.entry

    class FakeStorage:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            assert kwargs["supabase_url"] == "https://project.supabase.co"
            assert kwargs["bucket"] == "aq-datasets"

        def put_file(self, local_path) -> str:  # noqa: ANN001
            calls.append("put_file")
            assert Path(local_path).exists()
            return "supabase://aq-datasets/smoke.csv"

        def get_file(self, storage_uri: str) -> Path:
            calls.append("get_file")
            assert storage_uri == "supabase://aq-datasets/smoke.csv"
            path = Path("pytest-cache-files-smoke/fetched.csv")
            path.parent.mkdir(exist_ok=True)
            path.write_text("timestamp,station_id,pm25\n2024-01-01,A,1\n", encoding="utf-8")
            return path

    monkeypatch.setattr(smoke, "PostgresAgentTaskStore", FakeStore)
    monkeypatch.setattr(smoke, "PostgresDatasetRegistry", FakeRegistry)
    monkeypatch.setattr(smoke, "SupabaseDatasetStorage", FakeStorage)

    config = smoke.SmokeConfig(
        database_url="postgresql://example",
        supabase_url="https://project.supabase.co",
        service_role_key="service-key",
        bucket="aq-datasets",
    )

    smoke.run_smoke_test(config)

    assert calls == [
        "ensure_task_schema",
        "ensure_registry_schema",
        "put_file",
        "get_file",
        "add_entry",
        "find_by_uri",
    ]
