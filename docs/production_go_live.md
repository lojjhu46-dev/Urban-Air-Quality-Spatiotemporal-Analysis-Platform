# 生产上线执行手册

这份执行手册用于从“准备上云”推进到“生产可用”。当前仓库已经具备云端部署所需的 worker、Supabase 表结构、存储适配器和 Render Blueprint，但真实云环境尚未完成接入前，不应把项目标记为已上线。

目标生产部署形态：

- Streamlit Community Cloud 承载 UI。
- Supabase Postgres 存储任务状态和数据集索引元数据。
- Supabase Storage 存储生成的数据集文件。
- Render 运行常驻 worker，并负责 claim `PENDING` 任务。

请结合 [docs/cloud_deployment.md](D:/C/python/new_python/docs/cloud_deployment.md) 一起使用。本文假设你已经决定正式接入云资源。

## 0. 上线前置条件

开始执行本文前，先确认：

- 本地 `.streamlit/secrets.toml` 仍保持 `thread + local`，方便继续本地开发。
- 全量测试通过：`.\.venv\Scripts\python.exe -m pytest -q`。
- 你已经准备好 Supabase 项目、Render 账号和 Streamlit Community Cloud 应用入口权限。
- 真实密钥只写入云平台 secrets 或本机临时环境变量，不提交到仓库。

## 1. Supabase 前置准备

1. 在 Supabase SQL Editor 中执行 `docs/supabase_agent_tasks.sql`。
2. 在 Supabase Storage 中创建 `aq-datasets` bucket。
3. 确认你已经拿到以下生产环境配置值：
   - `DATABASE_URL`
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `SUPABASE_STORAGE_BUCKET=aq-datasets`

## 2. 部署 Render Worker

仓库根目录已经提供了 worker 的 Blueprint 文件 [render.yaml](D:/C/python/new_python/render.yaml)。

### 方案 A：通过 Blueprint 创建

1. 在 Render 中从当前仓库创建一个新的 Blueprint 服务。
2. 保持 `render.yaml` 中定义的 worker 服务类型不变。
3. 按提示填写以下 secrets：
   - `DATABASE_URL`
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `DEEPSEEK_API_KEY`
4. 检查以下非敏感默认值：
   - `DATASET_STORAGE_MODE=supabase`
   - `SUPABASE_STORAGE_BUCKET=aq-datasets`
   - `DEEPSEEK_MODEL=deepseek-v4-flash`
   - `DEEPSEEK_BASE_URL=https://api.deepseek.com`
   - `AGENT_LANGUAGE=en`
   - `WORKER_POLL_SECONDS=5`
5. 开始部署，并打开 worker 日志页面观察启动情况。

### 方案 B：手动创建

如果你不想导入 Blueprint，可以在 Render 中手动创建一个 Background Worker，配置如下：

- Runtime：`Python`
- Build Command：`pip install -r requirements.txt`
- Start Command：`python -m src.worker`
- Plan：`starter` 或更高

然后补齐与上面相同的环境变量。

### 预期的健康启动日志

worker 正常启动后应输出：

```text
Worker started. Polling every 5s.
```

## 3. 配置 Streamlit Community Cloud

在部署应用或编辑应用配置时，把入口文件设置为：

```text
app.py
```

然后把下面这组配置粘贴到应用的 Secrets 面板中，并用真实生产值替换占位符：

```toml
database_url = "postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres"
agent_task_executor_mode = "worker"
dataset_storage_mode = "supabase"
supabase_url = "https://<project-ref>.supabase.co"
supabase_service_role_key = "<service-role-key>"
supabase_storage_bucket = "aq-datasets"
deepseek_api_key = "sk-..."
deepseek_model = "deepseek-v4-flash"
deepseek_base_url = "https://api.deepseek.com"
```

生产环境下，应用应只提交 Historical Data Agent 任务为 `PENDING`，实际执行交给 Render worker。

## 4. 生产 Smoke Test

在正式对外开放前，请使用生产凭据跑一次真实 smoke test。

### PowerShell

```powershell
. .\scripts\load_supabase_env.ps1 -Profile smoke
C:\Users\cxk\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\supabase_smoke_test.py
```

### Bash

```bash
export DATABASE_URL="postgresql://..."
export SUPABASE_URL="https://<project-ref>.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="<service-role-key>"
export SUPABASE_STORAGE_BUCKET="aq-datasets"
python scripts/supabase_smoke_test.py
```

成功输出的结尾应包含：

```text
Smoke test OK. storage_uri=supabase://...
```

如果这里失败，停止上线流程。优先修复数据库连接、Storage bucket 名称、service role key 或网络访问问题。

## 5. 端到端 Claim 验证

1. 打开已部署的 Streamlit 应用。
2. 进入 `Historical Data Agent` 页面。
3. 提交一个小城市、短时间窗的 `Agent: Plan and Collect` 任务。
4. 在 `agent_tasks` 中确认新任务先以 `PENDING` 出现。
5. 观察 Render 日志，确认出现 claim 日志：

```text
[<task-id>] Claimed custom city task.
```

6. 等待任务状态进入 `SAVED`。
7. 继续核对以下结果：
   - `agent_tasks.output_path` 是 `supabase://...`
   - `dataset_index.storage_uri` 是 `supabase://...`
   - Supabase Storage 中能看到上传后的文件
   - Streamlit 的数据集选择器可以加载这个新的远程数据集

## 6. 完成判定

只有当下面几项都成立时，才算从“准备上云”进入“生产云端闭环完成”：

- Streamlit Cloud 能通过 `app.py` 正常启动。
- Render worker 已启动且保持健康。
- `scripts/supabase_smoke_test.py` 使用生产凭据执行通过。
- 一个生产任务完整经历 `PENDING -> RUNNING -> SAVED`。
- 保存后的数据集既能在 Supabase 元数据层看到，也能在 Streamlit UI 中加载使用。

## 7. 回退方案

如果生产联调遇到问题，可以先回退到本地闭环：

1. 保持本地 `.streamlit/secrets.toml`：

```toml
agent_task_executor_mode = "thread"
dataset_storage_mode = "local"
data_path = "data/processed/beijing_aq.parquet"
```

2. 暂停 Render worker。
3. 暂停或隐藏 Streamlit Cloud 应用入口。
4. 继续使用本地命令运行：

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```
