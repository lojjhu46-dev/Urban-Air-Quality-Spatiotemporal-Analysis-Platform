from __future__ import annotations

import os
import signal
import sys
import time

from src.agent_task_runner import AgentTaskRunConfig, run_custom_city_task
from src.agent_task_store import PostgresAgentTaskStore
from src.config import AQ_AGENT_DEFAULT_MODEL, DEEPSEEK_BASE_URL


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _database_url_from_env() -> str:
    return _env("DATABASE_URL") or _env("database_url")


def _run_config_from_env() -> AgentTaskRunConfig:
    return AgentTaskRunConfig(
        api_key=_env("DEEPSEEK_API_KEY") or _env("deepseek_api_key") or None,
        model=_env("DEEPSEEK_MODEL", AQ_AGENT_DEFAULT_MODEL) or AQ_AGENT_DEFAULT_MODEL,
        base_url=_env("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL) or DEEPSEEK_BASE_URL,
        language=_env("AGENT_LANGUAGE", "en") or "en",
    )


def main() -> None:
    database_url = _database_url_from_env()
    if not database_url:
        print("FATAL: DATABASE_URL is required for the worker.", file=sys.stderr)
        raise SystemExit(1)

    store = PostgresAgentTaskStore(database_url)
    store.ensure_schema()
    config = _run_config_from_env()
    poll_seconds = max(1, int(_env("WORKER_POLL_SECONDS", "5") or "5"))
    running = True

    def stop(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    print(f"Worker started. Polling every {poll_seconds}s.")

    while running:
        task = store.claim_next_pending_task()
        if task is None:
            time.sleep(poll_seconds)
            continue

        print(f"[{task.task_id}] Claimed custom city task.")
        try:
            run_custom_city_task(store, task.task_id, config)
        except Exception as exc:  # noqa: BLE001
            print(f"[{task.task_id}] Unhandled worker error: {exc}", file=sys.stderr)
        time.sleep(1)

    print("Worker stopped.")


if __name__ == "__main__":
    main()
