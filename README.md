# 城市空气质量时空分析与历史采集系统

本项目是一个基于 Streamlit 的多页面空气质量分析系统，既能对已有历史数据集进行时空分析，也能通过内置的历史数据 Agent 为指定城市生成新的可视化数据集。系统将数据加载、筛选分析、时空回放、相关性计算、历史采集、数据集切换和中英双语界面整合在同一个工作台中，适合用于城市空气质量教学演示、原型验证和轻量级研究分析。

## 系统定位

这个系统解决的是“从历史空气质量数据到可视化分析，再到新城市数据补采”的完整闭环问题：

- 如果你已经有处理好的数据集，可以直接进入总览、时空回放和相关性分析页面进行探索。
- 如果你只有原始北京站点 CSV，可以通过脚本构建为系统可识别的数据集。
- 如果你希望分析新的城市，可以在 Historical Data Agent 页面中通过结构化城市目录选择目标区域、年份、污染物和天气字段，由系统规划并采集新的历史数据集，然后立即切换到分析页面继续使用。

## 核心能力

- 多页面历史空气质量分析
  - 总览页提供 KPI、站点排名和事件标注。
  - 时空回放页提供按小时播放的站点级污染分布。
  - 相关性分析页提供污染物与气象变量的散点图、线性拟合和相关矩阵。
- 数据集切换与自动发现
  - 侧边栏会自动发现 `data/processed/` 和 `data/processed/agent_runs/` 下的 parquet / CSV 数据集。
  - 新采集的数据可立即在全部分析页面中切换使用。
- 历史数据 Agent
  - 内置跨大洲、国家/地区、省州和城市的结构化目录。
  - 可根据目标城市、年份范围、污染物和天气字段生成采集计划。
  - 支持实际可用时间窗裁剪、分块采集、天气补充和结果汇总。
  - 可选 DeepSeek 增强，用于计划说明、运行摘要以及中国城市覆盖较弱时的同省代理恢复。
- 原始数据 ETL
  - 提供从北京多站点原始 CSV 到系统可视化数据集的构建脚本。
  - 提供演示数据生成脚本，便于快速启动系统。
- 双语界面
  - 首页、分析页、Agent 页面、侧边栏导航和内置地区目录均支持 `zh-CN` / `en` 切换。

## 典型使用流程

### 场景一：使用已有数据集做分析

1. 准备好 `parquet` 或 `csv` 数据集。
2. 启动应用后，在侧边栏数据集选择器中选择目标文件。
3. 在 Overview、Spatiotemporal Playback、Correlation Analysis 页面中使用统一筛选条件进行分析。

### 场景二：从北京原始 CSV 构建可视化数据集

1. 将 `PRSA_Data_*.csv` 放入 `data/raw/`。
2. 运行 `scripts/build_dataset.py`。
3. 生成的数据会被保存到 `data/processed/`，并可被系统直接加载。

### 场景三：采集新城市历史数据

1. 打开 `Historical Data Agent` 页面。
2. 通过大洲、国家/地区、省州和城市选择目标位置。
3. 选择年份范围、污染物字段和天气字段。
4. 使用 `Agent: Draft Plan` 查看计划，或直接使用 `Agent: Plan and Collect` 执行采集。
5. 采集结果保存到 `data/processed/agent_runs/` 后，可回到分析页面继续使用。

## 页面说明

### Home

首页用于说明系统用途、显示当前激活的数据集，并提供统一的导航入口。

### Overview

总览页面向“全局判断”和“快速诊断”：

- 最新时刻均值
- 近 24 小时滚动均值
- 超阈值时长
- 站点差异
- 按站点的污染物排名
- 基于日均值的粗粒度事件标注

### Spatiotemporal Playback

时空回放页面向“空间分布”和“时间推进”：

- 选择日期和小时查看目标时刻的站点分布
- 通过动画回放连续小时的污染变化
- 在站点层面观察热点扩散与收缩

### Correlation Analysis

相关性分析页面向“污染物与天气变量之间的关系”：

- 污染物与天气变量散点图
- 线性拟合趋势
- 污染物与天气字段的相关矩阵
- 站点级日均值对比折线图

### Historical Data Agent

历史数据 Agent 页面是本系统的数据扩展入口。它不是单纯的聊天界面，而是一个“结构化目录 + 采集规划 + 执行反馈”的采集工作台，主要能力包括：

- 结构化区域选择
- 污染物和天气字段配置
- 城市候选解析
- 数据源可用时间窗裁剪
- 分块采集与合并
- 结果摘要、覆盖率统计和告警提示

## 系统架构

系统按职责大致可以分为四层：

### 1. 表现层

- `app.py`
  - 首页入口
- `pages/`
  - 各分析页面和历史数据 Agent 页面
- `src/i18n.py`
  - 中英双语文案
- `src/navigation.py`
  - 自定义侧边栏导航
- `src/ui.py`
  - 数据集选择、缓存加载、筛选控件和表格渲染

### 2. 业务与目录层

- `src/agent_interaction.py`
  - 内置城市目录、路径标签、查询关键词和匹配逻辑
- `src/catalog_display.py`
  - 内置目录的中英文显示层
- `src/china_city_catalog.py`
  - 中国城市扩展目录与显示名映射

### 3. 分析与可视化层

- `src/metrics.py`
  - KPI、站点排名、相关性和事件检测
- `src/charts.py`
  - 趋势图、排名图、地图散点、相关矩阵和回归散点图

### 4. 数据与采集层

- `src/data.py`
  - 数据集读写、时区规范化、CSV / parquet 回退、默认演示数据自动生成
- `src/collection_agent.py`
  - 历史数据采集、城市候选解析、采集计划生成、时间窗裁剪、分块执行、DeepSeek 增强
- `scripts/build_dataset.py`
  - 北京原始 CSV 到系统数据集的 ETL 脚本
- `scripts/generate_demo_data.py`
  - 演示数据生成脚本

## 数据流

### 路径一：本地历史数据分析

`原始/处理后数据集 -> src.data.load_dataset -> 全局筛选 -> 分析页面 -> 图表与指标`

### 路径二：新城市历史数据采集

`结构化区域选择 -> 城市候选解析 -> 采集计划 -> 数据源查询 -> 分块合并 -> 输出数据集 -> 侧边栏切换 -> 分析页面`

## 数据源与覆盖说明

### 内置演示/基础数据

- 北京多站点空气质量历史数据
- 默认处理后文件路径：`data/processed/beijing_aq.parquet`

### 历史数据 Agent 使用的数据源

- Open-Meteo Geocoding API
- Open-Meteo Air Quality Archive
- Open-Meteo Weather Archive
- 可选 DeepSeek Chat Completions API

### 覆盖规则

- 欧洲城市：
  - 使用 CAMS Europe
  - 起始时间约为 `2013-01-01`
  - 采样频率为小时级
- 非欧洲城市：
  - 使用 Open-Meteo Global
  - 起始时间约为 `2022-08-01`
  - 常见采样频率为 3 小时级
- 如果用户请求的年份范围超出数据源支持窗口，系统会自动裁剪，并在采集计划中显示实际可用范围。

## 历史数据 Agent 的工作机制

Agent 的内部执行过程大致如下：

1. 根据内置目录确定目标城市及查询词。
2. 调用地理编码接口解析城市候选、坐标和时区。
3. 根据城市所在区域确定数据源、起始可用日期和采样步长。
4. 按固定分块大小切分采集任务，默认块大小为 90 天。
5. 抓取空气质量字段，并按需补充天气字段。
6. 合并分块结果，输出系统可直接加载的数据集。
7. 生成覆盖率摘要、运行提示和告警信息。

如果配置了 `deepseek_api_key`，系统还会使用 DeepSeek 做以下增强：

- 生成更自然的计划说明
- 生成运行摘要
- 在部分中国城市覆盖不足时，尝试给出同省代理候选

## 项目结构

```text
new_python/
├─ app.py                          # 首页入口
├─ pages/                          # Streamlit 多页面视图
├─ src/                            # 共享模块：数据、分析、图表、国际化、导航、采集
├─ scripts/                        # ETL 与演示数据生成脚本
├─ data/
│  ├─ raw/                         # 原始输入数据
│  └─ processed/                   # 处理后数据与 Agent 采集结果
├─ tests/                          # 单元测试与页面测试
├─ .streamlit/
│  ├─ config.toml                  # Streamlit 运行配置
│  └─ secrets.toml.example         # Secrets 配置示例
├─ Dockerfile
├─ docker-compose.yml
└─ requirements.txt
```

## 环境要求

- Python 3.14
- Streamlit
- pandas / numpy / plotly
- requests
- pytest
- 可选 `pyarrow`，用于 parquet 读写

依赖安装：

```bash
pip install -r requirements.txt
```

## 快速启动

### 1. 启动演示模式

如果默认数据集不存在，系统会尝试自动生成演示数据。你也可以手动生成：

```bash
python scripts/generate_demo_data.py --out data/processed/beijing_aq.parquet
```

### 2. 从原始 CSV 构建数据集

```bash
python scripts/build_dataset.py --raw data/raw --out data/processed/beijing_aq.parquet
```

### 3. 运行应用

```bash
python -m streamlit run app.py
```

### 4. 可选配置 DeepSeek

在 `.streamlit/secrets.toml` 中配置：

```toml
deepseek_api_key = "sk-..."
deepseek_model = "deepseek-v4-flash"
deepseek_base_url = "https://api.deepseek.com"
```

## 部署

### Docker

```bash
docker build -t beijing-aq-dashboard .
docker run --rm -p 8501:8501 beijing-aq-dashboard
```

### Streamlit Community Cloud

部署时至少需要指定：

- 主入口文件：`app.py`
- Python 版本：`3.14` 或平台支持的最新兼容版本

如果需要自定义默认数据集或启用 DeepSeek，可在平台 Secrets 中补充：

```toml
data_path = "data/processed/beijing_aq.parquet"
deepseek_api_key = "sk-..."
deepseek_model = "deepseek-v4-flash"
```

## 配置与运行特性

- 默认时区：`Asia/Shanghai`
- 默认数据集：`data/processed/beijing_aq.parquet`
- Agent 输出目录：`data/processed/agent_runs/`
- 若 parquet 不可用，系统会自动回退到 CSV
- 如果默认数据集缺失，系统会尝试自动生成演示数据
- 侧边栏默认导航已关闭，系统使用自定义的可翻译导航入口

## 数据集格式约定

系统可直接加载的数据集至少应包含以下字段：

- `timestamp`
- `station_id`
- `lat`
- `lon`
- `pm25`
- `pm10`
- `no2`
- `so2`
- `co`
- `o3`
- `temp`
- `humidity`
- `wind_speed`

可选字段：

- `pm25_viz`
- `pm10_viz`
- `no2_viz`
- `so2_viz`
- `co_viz`
- `o3_viz`

这些 `_viz` 字段通常用于对极值进行裁剪，以改善可视化效果。

## 当前限制

- 非欧洲地区的历史空气质量数据时间覆盖较短，通常从 2022 年 8 月开始。
- 不同数据源的时间密度不同，全球源通常不是逐小时采样。
- 历史数据 Agent 依赖外部 API 的可用性与响应质量。
- 本项目中的地区国际化仅覆盖内置目录，不对所有外部 API 返回地名做实时翻译。

## 测试

运行全部测试：

```bash
pytest -q
```

当前测试覆盖主要包括：

- 数据加载与写出
- 指标与相关性计算
- 历史采集逻辑
- 国际化与目录显示
- 页面级基础渲染
