import os
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent_task_store import PostgresAgentTaskStore
from src.dataset_registry import DatasetIndexEntry, PostgresDatasetRegistry
from src.dataset_storage import SupabaseDatasetStorage

SMOKE_WORK_DIR = Path("pytest-cache-files-smoke")
REQUIRED_ENV = (
    "DATABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_STORAGE_BUCKET",
)


@dataclass(frozen=True, slots=True)
class SmokeConfig:
    database_url: str
    supabase_url: str
    service_role_key: str
    bucket: str


def validate_env() -> SmokeConfig:
    missing = [key for key in REQUIRED_ENV if not os.environ.get(key, "").strip()]
    if missing:
        print("Missing required environment variables:", file=sys.stderr)
        for key in missing:
            print(f"  - {key}", file=sys.stderr)
        raise SystemExit(2)
    return SmokeConfig(
        database_url=os.environ["DATABASE_URL"].strip(),
        supabase_url=os.environ["SUPABASE_URL"].strip(),
        service_role_key=os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip(),
        bucket=os.environ["SUPABASE_STORAGE_BUCKET"].strip(),
    )


def run_smoke_test(config: SmokeConfig) -> None:
    print("[1/5] Ensuring Postgres task schema...")
    task_store = PostgresAgentTaskStore(config.database_url)
    task_store.ensure_schema()

    print("[2/5] Ensuring dataset_index schema...")
    registry = PostgresDatasetRegistry(config.database_url)
    registry.ensure_schema()

    print("[3/5] Uploading tiny dataset to Supabase Storage...")
    storage = SupabaseDatasetStorage(
        supabase_url=config.supabase_url,
        service_role_key=config.service_role_key,
        bucket=config.bucket,
    )
    SMOKE_WORK_DIR.mkdir(exist_ok=True)
    local_path = SMOKE_WORK_DIR / "supabase_smoke_dataset.csv"
    local_path.write_text("timestamp,station_id,pm25\n2024-01-01T00:00:00+08:00,SMOKE,1.0\n", encoding="utf-8")
    storage_uri = storage.put_file(local_path)

    print("[4/5] Downloading uploaded dataset back through storage adapter...")
    fetched_path = storage.get_file(storage_uri)
    if not fetched_path.exists() or fetched_path.stat().st_size == 0:
        raise RuntimeError(f"Downloaded smoke dataset is missing or empty: {fetched_path}")

    print("[5/5] Writing and reading dataset_index entry...")
    registry.add_entry(
        DatasetIndexEntry(
            city="Supabase Smoke Test",
            country_code="ZZ",
            start_date="2024-01-01",
            end_date="2024-01-01",
            pollutants=["pm25"],
            row_count=1,
            format="csv",
            storage_uri=storage_uri,
            source_task_id="smoke-test",
        )
    )
    indexed = registry.find_by_uri(storage_uri)
    if indexed is None:
        raise RuntimeError(f"dataset_index did not return smoke entry for {storage_uri}")
    print(f"Smoke test OK. storage_uri={storage_uri}")


def main() -> None:
    run_smoke_test(validate_env())


if __name__ == "__main__":
    main()
