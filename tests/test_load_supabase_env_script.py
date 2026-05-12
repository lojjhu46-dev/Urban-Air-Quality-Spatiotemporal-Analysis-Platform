from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path


SCRIPT_PATH = Path("scripts/load_supabase_env.ps1").resolve()


def _workspace_temp_dir() -> Path:
    root = Path.cwd() / "pytest-cache-files-load-supabase-env"
    root.mkdir(exist_ok=True)
    path = root / f"case-{uuid.uuid4().hex}"
    path.mkdir()
    return path


def test_load_supabase_env_sets_process_environment_from_toml() -> None:
    tmp_path = _workspace_temp_dir()
    try:
        secrets_path = tmp_path / "secrets.toml"
        secrets_path.write_text(
            '\n'.join(
                [
                    'database_url = "postgresql://example"',
                    'agent_task_executor_mode = "worker"',
                    'dataset_storage_mode = "supabase"',
                    'supabase_url = "https://project.supabase.co"',
                    'supabase_service_role_key = "service-role-key"',
                    'supabase_storage_bucket = "aq-datasets"',
                ]
            ),
            encoding="utf-8",
        )

        command = (
            f". '{SCRIPT_PATH}' -SecretsPath '{secrets_path}' -Profile smoke -Quiet; "
            "[Console]::Out.WriteLine(($env:DATABASE_URL, "
            "$env:AGENT_TASK_EXECUTOR_MODE, "
            "$env:DATASET_STORAGE_MODE, "
            "$env:SUPABASE_URL, "
            "$env:SUPABASE_SERVICE_ROLE_KEY, "
            "$env:SUPABASE_STORAGE_BUCKET) -join \"`n\")"
        )

        result = subprocess.run(  # noqa: S603
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().splitlines() == [
            "postgresql://example",
            "worker",
            "supabase",
            "https://project.supabase.co",
            "service-role-key",
            "aq-datasets",
        ]
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
