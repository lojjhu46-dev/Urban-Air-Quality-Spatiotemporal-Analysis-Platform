# 本地项目完整测试清单

## Summary

当前测试套件位于 `tests/`，按 `pytest.ini` 配置运行。完整回归命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

当前仓库应覆盖 124 个测试用例。可用以下命令核对收集数量：

```powershell
.\.venv\Scripts\python.exe -m pytest --collect-only -q
```

## 自动化测试分组

- Agent 页面与交互：`tests/test_agent_interaction.py`
  - 城市目录、城市候选、中文显示、页面表单、任务提交、确认流程、失败状态展示、采集完成状态同步。

- Agent 本地任务执行：`tests/test_agent_task_executor.py`
  - 本地线程执行器选择、能力描述、后台线程启动、重复提交复用已有线程。

- Agent 任务状态存储：`tests/test_agent_task_store.py`
  - 内存任务创建、状态更新、日志记录、终态任务不被后续更新覆盖。

- Agent 任务运行器：`tests/test_agent_task_runner.py`
  - 自定义城市采集状态链、确认后的任务恢复、稳定目录别名回退、后台线程非阻塞、watchdog 超时不被覆盖。

- Agent UI 状态同步：`tests/test_agent_task_ui.py`
  - 采集完成结果同步到 session、确认面板显示条件。

- Agent watchdog：`tests/test_agent_task_watchdog.py`
  - 最大运行时超时、长时间无进展超时、等待确认任务不被误判超时。

- 历史采集核心逻辑：`tests/test_collection_agent.py`
  - 数据源窗口裁剪、欧洲 CAMS 计划、分块日期、天气窗口裁剪、API 请求、DST 时间处理、数据集最终格式、DeepSeek 工具流、城市校验、代理城市回退、网络重试。

- 采集数据管线：`tests/test_collection_data_pipeline.py`
  - 日期分块、天气归档窗口、DST 处理、最终数据集与覆盖率契约。

- 采集工具调用层：`tests/test_collection_agent_tools.py`
  - 工具 schema、参数校验、默认请求 payload、工具提示词、fallback 回复、候选解析、工具分发、未知工具错误。

- 采集摘要：`tests/test_collection_agent_summary.py`
  - 默认计划说明、运行摘要、DeepSeek 计划指导 prompt、摘要 payload、摘要 fallback。

- 中国城市代理回退：`tests/test_collection_proxy_fallback.py`
  - 同省候选过滤、候选匹配、代理计划解析、代理查询顺序、代理采集可用性、DeepSeek 代理选择。

- 自定义城市校验：`tests/test_custom_city_validation.py`
  - 有效位置、拼写纠正确认、默认字段、已存 payload 规范化、文本 normalizer。

- 数据读写：`tests/test_data_io.py`
  - parquet 不可用时回退 CSV、CSV 写出、CSV 加载与 timestamp 时区规范化。

- 数据筛选与地图帧：`tests/test_data.py`
  - 日期/站点筛选、地图帧最近时间 fallback。

- 本地数据集存储：`tests/test_dataset_storage.py`
  - 本地路径保持、环境存储默认为本地。

- 指标计算：`tests/test_metrics.py`
  - KPI 基础计算、相关矩阵计算。

- DeepSeek 客户端：`tests/test_deepseek_client.py`
  - 模型兼容候选、JSON 提取、工具参数解析、HTTP 错误信息、兼容模型重试、JSON completion 解析。

- 国际化：`tests/test_i18n.py`
  - 语言 fallback、语言标签、API 语言映射、Agent 文案双语、天气字段翻译。

- 导航：`tests/test_navigation.py`
  - 自定义侧边栏导航项本地化。

## 手动验收清单

- 启动应用：

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

- 首页能显示当前数据集路径。
- 侧边栏能发现并切换：
  - `data/processed/beijing_aq.parquet`
  - `data/processed/agent_runs/` 下的 parquet/csv 文件。
- `Overview` 页面能加载 KPI、站点排名和事件标注。
- `Spatiotemporal Playback` 页面能按日期/小时显示地图散点，并支持时间推进。
- `Correlation Analysis` 页面能显示散点、拟合、相关矩阵和日均折线。
- `Historical Data Agent` 页面：
  - DeepSeek key 为空时，应提示需要配置 key。
  - 配置 key 后，可提交 `Agent: Draft Plan`。
  - 可提交小范围 `Agent: Plan and Collect`，结果保存到 `data/processed/agent_runs/`。
  - 采集完成后，新数据集能在侧边栏被发现并切换分析。

## Assumptions

- 项目按纯本地 Streamlit 应用验收，不测试云端任务队列、外部执行进程或远程数据集存储。
- 自动化测试以 `pytest -q` 为准；涉及真实外部 API/key 的行为主要通过 mock 和手动小范围验证覆盖。
