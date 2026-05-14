# 云端部署检查清单

这份检查清单覆盖当前推荐的部署形态：

- Streamlit Cloud 运行 UI。
- Supabase Postgres 存储任务状态、日志和数据集索引元数据。
- Supabase Storage 存储生成的 parquet/csv 文件。
- 独立 worker 进程执行历史数据采集任务。

## 1. Supabase 配置

1. 创建一个 Supabase 项目。
2. 在 SQL Editor 中执行：

```sql
-- 粘贴并执行 docs/supabase_agent_tasks.sql
```

这会创建：

- `agent_tasks`
- `agent_task_logs`
- `dataset_index`

3. 在 Storage 中创建一个 bucket，例如：

```text
aq-datasets
```

应用在服务端环境中使用 service role key，因此 bucket 不需要公开。

## 2. Streamlit Cloud UI

把应用入口文件设置为：

```text
app.py
```

在 Streamlit Cloud 中配置以下 secrets：

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

UI 应只把 Historical Data Agent 任务提交为 `PENDING`；不要在 Streamlit 进程内执行长时间采集任务。

## 3. Worker 部署

worker 可以部署在 Render、Railway、Fly.io 或 VPS。必需环境变量如下：

```text
DATABASE_URL
DEEPSEEK_API_KEY
DATASET_STORAGE_MODE=supabase
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_STORAGE_BUCKET=aq-datasets
```

可选环境变量：

```text
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
AGENT_LANGUAGE=en
WORKER_POLL_SECONDS=5
DATASET_STORAGE_CACHE_DIR=.cache/datasets
```

启动命令：

```bash
python -m src.worker
```

也可以使用辅助脚本：

```bash
bash scripts/run_worker.sh
```

```powershell
.\scripts\run_worker.ps1
```

### Render Blueprint

仓库根目录提供了一个 `render.yaml`，用于定义原生 Python 后台 worker，包含以下默认设置：

- `buildCommand: pip install -r requirements.txt`
- `startCommand: python -m src.worker`
- `DATASET_STORAGE_MODE=supabase`
- 需要在部署时填写的 secrets：`DATABASE_URL`、`SUPABASE_URL`、`SUPABASE_SERVICE_ROLE_KEY`、`DEEPSEEK_API_KEY`

如果你希望 worker 服务定义跟随仓库版本一起维护，建议直接把当前仓库作为 Render Blueprint 导入。

## 4. 真实 Supabase Smoke Test

在正式对用户开放前，先执行：

```bash
python scripts/supabase_smoke_test.py
```

这个 smoke test 会验证：

- Postgres 任务表结构可以创建。
- `dataset_index` 表结构可以创建。
- 一个很小的 CSV 能上传到 Supabase Storage。
- 上传后的文件可以通过存储适配器重新下载。
- 一条 `dataset_index` 记录可以写入并成功读回。

成功输出的结尾应为：

```text
Smoke test OK. storage_uri=supabase://...
```

## 5. 端到端应用检查

1. 打开 Streamlit 应用。
2. 进入 Historical Data Agent。
3. 提交一个小城市、小日期范围的 `Agent: Plan and Collect` 任务。
4. 确认该任务在 `agent_tasks` 中先显示为 `PENDING`。
5. 启动 worker，并确认它 claim 了该任务。
6. 等待任务状态变为 `SAVED`。
7. 继续确认：
   - `agent_tasks.output_path` 是 `supabase://...`
   - `dataset_index.storage_uri` 是 `supabase://...`
   - Supabase Storage 中存在生成后的文件
   - Overview / Playback / Correlation 页面可以加载这个新的远程数据集

## 6. 安全说明

- 不要提交 `.streamlit/secrets.toml` 或任何真实 key。
- `SUPABASE_SERVICE_ROLE_KEY` 只应保存在服务端 secrets 中。
- 进程重启后不要自动重跑旧的 `RUNNING` 任务；应由 watchdog 将长期无进展任务标记为 `TIMEOUT`。
- 对 Streamlit Cloud，优先使用 Supabase transaction pooler URL。
