# Cloud Deployment Checklist

This checklist covers the recommended deployment shape:

- Streamlit Cloud runs the UI.
- Supabase Postgres stores agent task state, logs, and dataset index metadata.
- Supabase Storage stores generated parquet/csv files.
- A separate worker process runs historical collection tasks.

## 1. Supabase Setup

1. Create a Supabase project.
2. In SQL Editor, run:

```sql
-- paste and execute docs/supabase_agent_tasks.sql
```

This creates:

- `agent_tasks`
- `agent_task_logs`
- `dataset_index`

3. In Storage, create a bucket such as:

```text
aq-datasets
```

The app uses the service role key from server-side environments, so the bucket does not need to be public.

## 2. Streamlit Cloud UI

Set the app entrypoint to:

```text
app.py
```

Add these secrets in Streamlit Cloud:

```toml
database_url = "postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres"
agent_task_executor_mode = "worker"
dataset_storage_mode = "supabase"
supabase_url = "https://<project-ref>.supabase.co"
supabase_service_role_key = "<service-role-key>"
supabase_storage_bucket = "aq-datasets"
deepseek_api_key = "sk-..."
deepseek_model = "deepseek-v4-flash"
```

The UI should submit Historical Data Agent tasks as `PENDING`; it should not run long collection work inside the Streamlit process.

## 3. Worker Deployment

Deploy the worker on Render, Railway, Fly.io, or a VPS. Required environment variables:

```text
DATABASE_URL
DEEPSEEK_API_KEY
DATASET_STORAGE_MODE=supabase
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_STORAGE_BUCKET=aq-datasets
```

Optional:

```text
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
AGENT_LANGUAGE=en
WORKER_POLL_SECONDS=5
DATASET_STORAGE_CACHE_DIR=.cache/datasets
```

Start command:

```bash
python -m src.worker
```

Or use the helper scripts:

```bash
bash scripts/run_worker.sh
```

```powershell
.\scripts\run_worker.ps1
```

## 4. Real Supabase Smoke Test

Run this before opening the app to users:

```bash
python scripts/supabase_smoke_test.py
```

The smoke test verifies:

- Postgres task schema can be created.
- `dataset_index` schema can be created.
- A tiny CSV can upload to Supabase Storage.
- The uploaded file can download through the storage adapter.
- A `dataset_index` row can be written and read back.

Successful output ends with:

```text
Smoke test OK. storage_uri=supabase://...
```

## 5. End-To-End App Check

1. Open the Streamlit app.
2. Go to Historical Data Agent.
3. Submit `Agent: Plan and Collect` for a small city/date range.
4. Confirm the task appears as `PENDING` in `agent_tasks`.
5. Start the worker and confirm it claims the task.
6. Wait for `SAVED`.
7. Confirm:
   - `agent_tasks.output_path` is `supabase://...`
   - `dataset_index.storage_uri` is `supabase://...`
   - Supabase Storage contains the generated file
   - Overview / Playback / Correlation can load the generated remote dataset

## 6. Safety Notes

- Do not commit `.streamlit/secrets.toml` or real keys.
- Keep `SUPABASE_SERVICE_ROLE_KEY` only in server-side secrets.
- Do not auto-rerun old `RUNNING` tasks after restart; the watchdog should mark stale tasks as `TIMEOUT`.
- Prefer Supabase transaction pooler URLs for Streamlit Cloud.
