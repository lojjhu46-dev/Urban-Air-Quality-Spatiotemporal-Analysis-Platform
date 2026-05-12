# Streamlit Cloud + Supabase 任务托管 + 轻量 Worker 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Streamlit Cloud UI + Supabase Postgres 任务托管 + 独立 worker 采集的最小上云闭环，加数据集索引层。

**Architecture:** PostgresAgentTaskStore 增加原子 claim 能力；新增 NoOpAgentTaskExecutor 让 UI 只提交不执行；独立 worker 进程轮询 Postgres 抢任务；DatasetRegistry 提供本地 + Postgres 双后端元数据索引。

**Tech Stack:** Python 3.14, Streamlit, psycopg 3, Supabase Postgres, parquet

---

### Task 1: 新增 `claim_next_pending_task()` 到 PostgresAgentTaskStore

**Files:**
- Modify: `src/agent_task_store.py`

- [ ] **Step 1: 添加 `claim_next_pending_task()` 方法**

在 `PostgresAgentTaskStore` 类的 `list_logs` 方法之后（第324行后），`task_store_from_config` 函数之前，插入：

```python
    def claim_next_pending_task(self) -> AgentTask | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT task_id FROM agent_tasks
                    WHERE status = 'PENDING' AND kind = 'custom_city_collection'
                    ORDER BY created_at
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                task_id = row["task_id"]
                cursor.execute(
                    """
                    UPDATE agent_tasks
                    SET status = 'RUNNING',
                        started_at = now(),
                        updated_at = now()
                    WHERE task_id = %s
                    RETURNING *
                    """,
                    (task_id,),
                )
                updated = cursor.fetchone()
        if updated is None:
            return None
        return _task_from_row(dict(updated))
```

- [ ] **Step 2: 运行存量测试确认不破坏现有行为**

```bash
.venv/Scripts/python.exe -m pytest tests/test_agent_task_store.py -v
```

- [ ] **Step 3: Commit**

```bash
git add src/agent_task_store.py
git commit -m "feat: add claim_next_pending_task to PostgresAgentTaskStore"
```

---

### Task 2: 新增 `update_heartbeat()` 到 PostgresAgentTaskStore

**Files:**
- Modify: `src/agent_task_store.py`

- [ ] **Step 1: 添加 `update_heartbeat()` 方法**

在 `claim_next_pending_task` 之后插入：

```python
    def update_heartbeat(self, task_id: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE agent_tasks SET updated_at = now() WHERE task_id = %s AND status = 'RUNNING'",
                    (task_id,),
                )
```

- [ ] **Step 2: 在 `InMemoryAgentTaskStore` 添加兼容接口**

在 `InMemoryAgentTaskStore.list_logs` 之后插入：

```python
    def claim_next_pending_task(self) -> AgentTask | None:
        with self._lock:
            for task in self._tasks.values():
                if task.status == AgentTaskStatus.PENDING and task.kind == "custom_city_collection":
                    task.status = AgentTaskStatus.RUNNING
                    task.started_at = _utc_now()
                    task.updated_at = _utc_now()
                    return task
        return None

    def update_heartbeat(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None and task.status == AgentTaskStatus.RUNNING:
                task.updated_at = _utc_now()
```

- [ ] **Step 3: 运行全部测试**

```bash
.venv/Scripts/python.exe -m pytest tests/ -q
```

- [ ] **Step 4: Commit**

```bash
git add src/agent_task_store.py
git commit -m "feat: add update_heartbeat to both task store backends"
```

---

### Task 3: 新增 NoOpAgentTaskExecutor（worker mode）

**Files:**
- Modify: `src/agent_task_executor.py`

- [ ] **Step 1: 替换文件内容**

用以下内容替换 `src/agent_task_executor.py`：

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.agent_task_runner import AgentTaskRunConfig, AgentTaskStore, start_background_custom_city_task


@dataclass(frozen=True, slots=True)
class AgentTaskSubmission:
    task_id: str
    mode: str
    started: bool
    message: str


@dataclass(frozen=True, slots=True)
class AgentTaskExecutorCapabilities:
    mode: str
    supports_external_worker: bool
    supports_cross_process_recovery: bool
    auto_reruns_running_tasks: bool
    notes: str


class AgentTaskExecutor(Protocol):
    def submit_custom_city_task(
        self,
        store: AgentTaskStore,
        task_id: str,
        config: AgentTaskRunConfig,
    ) -> AgentTaskSubmission: ...


class InProcessAgentTaskExecutor:
    mode = "thread"

    def submit_custom_city_task(
        self,
        store: AgentTaskStore,
        task_id: str,
        config: AgentTaskRunConfig,
    ) -> AgentTaskSubmission:
        thread = start_background_custom_city_task(store, task_id, config)
        return AgentTaskSubmission(
            task_id=task_id,
            mode=self.mode,
            started=thread.is_alive(),
            message="Submitted to in-process background thread.",
        )


class NoOpAgentTaskExecutor:
    """Submit-only executor for worker mode. Does not start local threads.

    The UI creates a PENDING task and returns. An external worker process
    claims and executes it via PostgresAgentTaskStore.claim_next_pending_task().
    """

    mode = "worker"

    def submit_custom_city_task(
        self,
        store: AgentTaskStore,
        task_id: str,
        config: AgentTaskRunConfig,
    ) -> AgentTaskSubmission:
        del config
        task = store.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        return AgentTaskSubmission(
            task_id=task_id,
            mode=self.mode,
            started=False,
            message="Task queued. A worker process will claim and execute it.",
        )


def agent_task_executor_from_config(mode: str | None = None) -> AgentTaskExecutor:
    normalized = (mode or "thread").strip().casefold()
    if normalized in {"", "thread", "inprocess", "in-process", "local"}:
        return InProcessAgentTaskExecutor()
    if normalized == "worker":
        return NoOpAgentTaskExecutor()
    return InProcessAgentTaskExecutor()


def describe_executor_capabilities(mode: str | None = None) -> AgentTaskExecutorCapabilities:
    executor = agent_task_executor_from_config(mode)
    mode_value = getattr(executor, "mode", "thread")
    if mode_value == "thread":
        return AgentTaskExecutorCapabilities(
            mode="thread",
            supports_external_worker=False,
            supports_cross_process_recovery=False,
            auto_reruns_running_tasks=False,
            notes=(
                "The thread executor runs work inside the current Streamlit process. "
                "Persisted RUNNING tasks are not automatically rerun after process restart; "
                "the watchdog should mark stale tasks as TIMEOUT."
            ),
        )
    return AgentTaskExecutorCapabilities(
        mode="worker",
        supports_external_worker=True,
        supports_cross_process_recovery=True,
        auto_reruns_running_tasks=False,
        notes=(
            "Worker mode submits tasks to a shared task store. "
            "An independent worker process claims and executes tasks. "
            "RUNNING tasks are not automatically claimed by a new worker — "
            "the watchdog marks stale tasks as TIMEOUT."
        ),
    )
```

- [ ] **Step 2: 运行 executor 测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_agent_task_executor.py -v
```

- [ ] **Step 3: 添加 worker mode 测试到 test_agent_task_executor.py**

在文件末尾追加：

```python
def test_worker_executor_does_not_start_thread() -> None:
    from src.agent_task_executor import NoOpAgentTaskExecutor

    store = InMemoryAgentTaskStore()
    task = store.create_task(kind="custom_city_collection", request_payload={"action": "plan"})
    submission = NoOpAgentTaskExecutor().submit_custom_city_task(
        store, task.task_id, AgentTaskRunConfig(api_key="sk-test")
    )

    assert submission.task_id == task.task_id
    assert submission.mode == "worker"
    assert submission.started is False
    assert "queued" in submission.message.lower()


def test_agent_task_executor_factory_returns_noop_for_worker_mode() -> None:
    from src.agent_task_executor import NoOpAgentTaskExecutor, agent_task_executor_from_config

    assert isinstance(agent_task_executor_from_config("worker"), NoOpAgentTaskExecutor)


def test_describe_executor_capabilities_declares_worker_support() -> None:
    from src.agent_task_executor import describe_executor_capabilities

    capabilities = describe_executor_capabilities("worker")

    assert capabilities.mode == "worker"
    assert capabilities.supports_external_worker is True
    assert capabilities.supports_cross_process_recovery is True
```

更新文件顶部的 import：

```python
from src.agent_task_runner import AgentTaskRunConfig, start_background_custom_city_task
from src.agent_task_store import AgentTaskStatus, InMemoryAgentTaskStore
```

- [ ] **Step 4: 运行全部测试**

```bash
.venv/Scripts/python.exe -m pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add src/agent_task_executor.py tests/test_agent_task_executor.py
git commit -m "feat: add NoOpAgentTaskExecutor for worker mode"
```

---

### Task 4: 创建 worker 入口脚本

**Files:**
- Create: `src/worker.py`

- [ ] **Step 1: 创建 `src/worker.py`**

```python
from __future__ import annotations

import os
import signal
import sys
import time

from src.agent_task_runner import AgentTaskRunConfig, run_custom_city_task
from src.agent_task_store import PostgresAgentTaskStore


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def main() -> None:
    database_url = _env("DATABASE_URL") or _env("database_url")
    if not database_url:
        print("FATAL: DATABASE_URL not set in environment.", file=sys.stderr)
        sys.exit(1)

    store = PostgresAgentTaskStore(database_url)
    store.ensure_schema()

    config = AgentTaskRunConfig(
        api_key=_env("DEEPSEEK_API_KEY") or None,
        model=_env("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        base_url=_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        language=_env("AGENT_LANGUAGE", "en"),
    )

    running = True

    def _shutdown(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False
        print("\nWorker shutting down...")

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    print(f"Worker started. Model: {config.model}, Language: {config.language}")
    poll_seconds = int(_env("WORKER_POLL_SECONDS", "5"))

    while running:
        task = store.claim_next_pending_task()
        if task is None:
            time.sleep(poll_seconds)
            continue

        print(f"[{task.task_id}] Claimed. City: {task.request_payload.get('input_city', '?')}")
        try:
            run_custom_city_task(store, task.task_id, config)
        except Exception as exc:
            print(f"[{task.task_id}] Failed: {exc}", file=sys.stderr)
        time.sleep(1)

    print("Worker stopped.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 验证 worker 脚本可导入**

```bash
.venv/Scripts/python.exe -c "from src.worker import main; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add src/worker.py
git commit -m "feat: add standalone worker entry point"
```

---

### Task 5: 创建 DatasetRegistry

**Files:**
- Create: `src/dataset_registry.py`
- Create: `tests/test_dataset_registry.py`

- [ ] **Step 1: 创建 `src/dataset_registry.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import pandas as pd


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
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
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "city": self.city,
            "country_code": self.country_code,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "pollutants": self.pollutants,
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
        self._entries: list[DatasetIndexEntry] = []

    def add_entry(self, entry: DatasetIndexEntry) -> None:
        for existing in self._entries:
            if existing.storage_uri == entry.storage_uri:
                self._entries.remove(existing)
                break
        self._entries.append(entry)

    def list_entries(self) -> list[DatasetIndexEntry]:
        return list(self._entries)

    def find_by_uri(self, storage_uri: str) -> DatasetIndexEntry | None:
        for entry in self._entries:
            if entry.storage_uri == storage_uri:
                return entry
        return None

    @staticmethod
    def build_entry_from_path(path: Path) -> DatasetIndexEntry | None:
        try:
            df = pd.read_parquet(path) if path.suffix.lower() == ".parquet" else pd.read_csv(path)
        except Exception:
            return None

        if "station_id" not in df.columns or "timestamp" not in df.columns:
            return None

        city = str(df["station_id"].iloc[0])
        timestamps = pd.to_datetime(df["timestamp"])
        pollutants = [col for col in ["pm25", "pm10", "no2", "so2", "co", "o3"] if col in df.columns]

        return DatasetIndexEntry(
            city=city,
            country_code="",
            start_date=str(timestamps.min()),
            end_date=str(timestamps.max()),
            pollutants=pollutants,
            row_count=len(df),
            format=path.suffix.lstrip("."),
            storage_uri=str(path),
            created_at=_utc_now().isoformat(),
        )


class PostgresDatasetRegistry:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("Install `psycopg[binary]` to use Postgres dataset registry.") from exc
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _jsonb(self, payload):
        try:
            from psycopg.types.json import Jsonb
        except ImportError as exc:
            raise RuntimeError("Install `psycopg[binary]` to use Postgres dataset registry.") from exc
        return Jsonb(payload)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(_DATASET_INDEX_SCHEMA_SQL)

    def add_entry(self, entry: DatasetIndexEntry) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO dataset_index
                        (city, country_code, start_date, end_date, pollutants,
                         row_count, format, storage_uri, source_task_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (storage_uri) DO UPDATE SET
                        city = EXCLUDED.city,
                        country_code = EXCLUDED.country_code,
                        start_date = EXCLUDED.start_date,
                        end_date = EXCLUDED.end_date,
                        pollutants = EXCLUDED.pollutants,
                        row_count = EXCLUDED.row_count,
                        format = EXCLUDED.format,
                        source_task_id = EXCLUDED.source_task_id
                    """,
                    (
                        entry.city,
                        entry.country_code,
                        entry.start_date,
                        entry.end_date,
                        self._jsonb(entry.pollutants),
                        entry.row_count,
                        entry.format,
                        entry.storage_uri,
                        entry.source_task_id,
                        _utc_now(),
                    ),
                )

    def list_entries(self) -> list[DatasetIndexEntry]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM dataset_index ORDER BY created_at DESC"
                )
                return [_entry_from_row(dict(row)) for row in cursor.fetchall()]

    def find_by_uri(self, storage_uri: str) -> DatasetIndexEntry | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM dataset_index WHERE storage_uri = %s",
                    (storage_uri,),
                )
                row = cursor.fetchone()
        return _entry_from_row(dict(row)) if row else None


def dataset_registry_from_config(database_url: str | None = None) -> DatasetRegistry:
    if database_url and database_url.strip():
        return PostgresDatasetRegistry(database_url.strip())
    return LocalDatasetRegistry()


def _entry_from_row(row: dict[str, Any]) -> DatasetIndexEntry:
    import json as _json

    pollutants = row.get("pollutants")
    if isinstance(pollutants, str):
        try:
            pollutants = _json.loads(pollutants)
        except Exception:
            pollutants = []

    return DatasetIndexEntry(
        city=str(row.get("city") or ""),
        country_code=str(row.get("country_code") or ""),
        start_date=str(row.get("start_date") or ""),
        end_date=str(row.get("end_date") or ""),
        pollutants=list(pollutants) if pollutants else [],
        row_count=int(row.get("row_count") or 0),
        format=str(row.get("format") or "parquet"),
        storage_uri=str(row.get("storage_uri") or ""),
        source_task_id=row.get("source_task_id"),
        created_at=str(row.get("created_at") or ""),
    )


_DATASET_INDEX_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dataset_index (
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
    CONSTRAINT dataset_index_storage_uri_unique UNIQUE (storage_uri)
);

CREATE INDEX IF NOT EXISTS idx_dataset_index_city
    ON dataset_index(city, country_code);

CREATE INDEX IF NOT EXISTS idx_dataset_index_created
    ON dataset_index(created_at DESC);
"""
```

- [ ] **Step 2: 创建 `tests/test_dataset_registry.py`**

```python
from __future__ import annotations

from pathlib import Path

from src.dataset_registry import (
    DatasetIndexEntry,
    LocalDatasetRegistry,
    dataset_registry_from_config,
)


def test_local_registry_add_and_list() -> None:
    registry = LocalDatasetRegistry()
    entry = DatasetIndexEntry(
        city="Tokyo",
        country_code="JP",
        start_date="2024-01-01",
        end_date="2024-12-31",
        pollutants=["pm25", "o3"],
        row_count=1000,
        format="parquet",
        storage_uri="/data/tokyo.parquet",
    )

    registry.add_entry(entry)
    entries = registry.list_entries()

    assert len(entries) == 1
    assert entries[0].city == "Tokyo"
    assert entries[0].storage_uri == "/data/tokyo.parquet"


def test_local_registry_deduplicates_by_uri() -> None:
    registry = LocalDatasetRegistry()
    first = DatasetIndexEntry(city="A", country_code="", start_date="", end_date="", storage_uri="/same.parquet")
    second = DatasetIndexEntry(city="B", country_code="", start_date="", end_date="", storage_uri="/same.parquet")

    registry.add_entry(first)
    registry.add_entry(second)
    entries = registry.list_entries()

    assert len(entries) == 1
    assert entries[0].city == "B"


def test_local_registry_find_by_uri() -> None:
    registry = LocalDatasetRegistry()
    entry = DatasetIndexEntry(city="Osaka", country_code="JP", start_date="", end_date="", storage_uri="/data/osaka.parquet")
    registry.add_entry(entry)

    found = registry.find_by_uri("/data/osaka.parquet")
    assert found is not None
    assert found.city == "Osaka"

    not_found = registry.find_by_uri("/data/nonexistent.parquet")
    assert not_found is None


def test_dataset_registry_from_config_returns_local_by_default() -> None:
    registry = dataset_registry_from_config(None)
    assert isinstance(registry, LocalDatasetRegistry)

    registry_empty = dataset_registry_from_config("")
    assert isinstance(registry_empty, LocalDatasetRegistry)


def test_dataset_index_entry_to_dict() -> None:
    entry = DatasetIndexEntry(
        city="Berlin",
        country_code="DE",
        start_date="2023-01-01",
        end_date="2023-06-30",
        pollutants=["pm25", "pm10"],
        row_count=500,
        format="parquet",
        storage_uri="/data/berlin.parquet",
        source_task_id="abc-123",
    )

    d = entry.to_dict()
    assert d["city"] == "Berlin"
    assert d["pollutants"] == ["pm25", "pm10"]
    assert d["source_task_id"] == "abc-123"
```

- [ ] **Step 3: 运行 registry 测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_dataset_registry.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/dataset_registry.py tests/test_dataset_registry.py
git commit -m "feat: add DatasetRegistry with local and postgres backends"
```

---

### Task 6: 采集完成时自动注册到 DatasetRegistry

**Files:**
- Modify: `src/agent_task_runner.py`

- [ ] **Step 1: 在 `run_custom_city_task` 的 SAVED 分支添加注册调用**

找到 `agent_task_runner.py` 中 `_record_step` SAVED 状态的调用（约第192行），在它之前插入 registry 注册逻辑。

在文件顶部 import 区添加：

```python
from src.dataset_registry import DatasetIndexEntry, dataset_registry_from_config
```

在 `run_custom_city_task` 函数中，`_record_step` (SAVED 分支) 之前插入：

```python
            # 将采集结果注册到 DatasetRegistry
            try:
                db_url = _env_database_url()
                registry = dataset_registry_from_config(db_url)
                registry.add_entry(DatasetIndexEntry(
                    city=result.plan.city_label,
                    country_code=result.plan.country_code,
                    start_date=result.plan.actual_start_date,
                    end_date=result.plan.actual_end_date,
                    pollutants=result.plan.pollutants,
                    row_count=result.row_count,
                    format="parquet",
                    storage_uri=result.output_path,
                    source_task_id=task_id,
                ))
            except Exception:
                pass  # registry write is best-effort, never block task completion
```

添加辅助函数：

```python
def _env_database_url() -> str | None:
    import os
    return os.environ.get("DATABASE_URL") or os.environ.get("database_url")
```

- [ ] **Step 2: 运行 runner 测试**

```bash
.venv/Scripts/python.exe -m pytest tests/test_agent_task_runner.py -v
```

- [ ] **Step 3: Commit**

```bash
git add src/agent_task_runner.py
git commit -m "feat: auto-register completed collections in DatasetRegistry"
```

---

### Task 7: 扩展数据集选择器利用 registry 元数据

**Files:**
- Modify: `src/ui.py`

- [ ] **Step 1: 修改 `format_dataset_label` 优先使用 registry 元数据**

在 `ui.py` 的 import 区添加：

```python
from src.dataset_registry import dataset_registry_from_config
```

修改 `format_dataset_label` 函数：

```python
# 模块级缓存，避免每次渲染都查 registry
_registry_cache: dict[str, str] = {}


def _registry_label(path: Path) -> str | None:
    raw = str(path)
    if raw in _registry_cache:
        return _registry_cache[raw] or None

    try:
        db_url = None
        try:
            db_url = st.secrets.get("database_url") or st.secrets.get("DATABASE_URL")
        except Exception:
            pass
        registry = dataset_registry_from_config(db_url)
        entry = registry.find_by_uri(raw)
        if entry is not None and entry.city:
            label = f"{entry.city} [{entry.format.upper()}] ({entry.start_date[:10]} ~ {entry.end_date[:10]})"
            _registry_cache[raw] = label
            return label
    except Exception:
        pass

    _registry_cache[raw] = ""
    return None


def format_dataset_label(path: Path) -> str:
    rich = _registry_label(path)
    if rich:
        return rich
    try:
        relative = path.relative_to(Path.cwd())
        suffix = relative.as_posix()
    except ValueError:
        suffix = str(path)
    return f"{path.stem} [{path.suffix.lstrip('.').upper()}] ({suffix})"
```

- [ ] **Step 2: 运行全部测试**

```bash
.venv/Scripts/python.exe -m pytest tests/ -q
```

- [ ] **Step 3: Commit**

```bash
git add src/ui.py
git commit -m "feat: enrich dataset selector labels with registry metadata"
```

---

### Task 8: 更新 secrets.example 和 README

**Files:**
- Modify: `.streamlit/secrets.toml.example`
- Modify: `README.md`

- [ ] **Step 1: 更新 `.streamlit/secrets.toml.example`**

用以下内容替换：

```toml
# Example only. In Streamlit Community Cloud, paste these key-values
# into the app Secrets panel (Advanced settings).

# Optional: override local parquet path
# data_path = "data/processed/beijing_aq.parquet"

# Optional: enable the historical collection agent with DeepSeek
# deepseek_api_key = "sk-"
# deepseek_model = "deepseek-v4-flash"
# deepseek_base_url = "https://api.deepseek.com"

# Task executor mode: "thread" (local, default) or "worker" (external worker)
# agent_task_executor_mode = "thread"
# agent_task_timeout_seconds = 1800
# agent_task_stalled_seconds = 300

# Supabase Postgres connection (transaction pooler URL recommended)
# When set, task state and dataset index are persisted in Postgres.
# Worker mode requires this to be configured.
# database_url = "postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres"
```

- [ ] **Step 2: 更新 README.md**

在第296行（`## 配置与运行特性` 部分之前）插入以下内容：

```markdown
## Streamlit Cloud + Supabase 部署

系统支持两种任务执行模式，通过 `agent_task_executor_mode` 控制：

- **`thread`（默认）**：采集任务在 Streamlit 进程内以后台线程执行。适合本地开发和单机部署。
- **`worker`**：UI 只创建 PENDING 任务，不启动本地线程。独立的 worker 进程通过轮询 Supabase Postgres 抢任务执行。适合 Streamlit Cloud（无长任务支持）的部署场景。

### Worker 部署步骤

1. 在 Supabase 项目中执行 `docs/supabase_agent_tasks.sql` 创建所需表。
2. 在 Streamlit Cloud secrets 中配置 `database_url` 和 `agent_task_executor_mode = "worker"`。
3. 在 Render / Railway / Fly.io / VPS 上部署 worker：

```bash
DATABASE_URL="postgresql://..." \\
DEEPSEEK_API_KEY="sk-..." \\
python -m src.worker
```

Worker 启动后持续轮询，每次原子 claim 一个 PENDING 任务，调用现有采集流程。多 worker 并发安全（`FOR UPDATE SKIP LOCKED`）。

### 数据集索引

采集完成后，系统自动将数据集元数据写入 `dataset_index` 表（Postgres）或本地内存（LocalRegistry）。数据集选择器优先使用索引中的城市名、时间范围等信息展示可读标签。
```

- [ ] **Step 3: 更新 `docs/supabase_agent_tasks.sql`**

在文件末尾追加 `dataset_index` 表定义：

```sql
CREATE TABLE IF NOT EXISTS dataset_index (
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
    CONSTRAINT dataset_index_storage_uri_unique UNIQUE (storage_uri)
);

CREATE INDEX IF NOT EXISTS idx_dataset_index_city
    ON dataset_index(city, country_code);

CREATE INDEX IF NOT EXISTS idx_dataset_index_created
    ON dataset_index(created_at DESC);
```

- [ ] **Step 4: Commit**

```bash
git add .streamlit/secrets.toml.example README.md docs/supabase_agent_tasks.sql
git commit -m "docs: add Streamlit Cloud + worker deployment guide"
```

---

### 最终验证

- [ ] **运行全量测试**

```bash
.venv/Scripts/python.exe -m pytest tests/ -q
```

- [ ] **验证 Streamlit 可启动（thread 模式）**

```bash
.venv/Scripts/python.exe -m streamlit run app.py --server.port 8505
```

确认首页、Overview、Historical Data Agent 页面返回 200。

- [ ] **验证新增模块均可正常导入**

```bash
.venv/Scripts/python.exe -c "from src.worker import main; from src.dataset_registry import LocalDatasetRegistry, PostgresDatasetRegistry, dataset_registry_from_config; print('All imports OK')"
```
