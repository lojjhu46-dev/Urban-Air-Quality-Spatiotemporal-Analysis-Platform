# City Air Quality Dashboard

A medium-complexity data visualization project using Python 3.14, Streamlit, and Plotly.

## Features
- Multi-filter linked dashboard across pages
- Spatiotemporal playback map for station-level pollution
- Pollutant-weather correlation analysis
- Optional OpenAQ realtime panel with fallback mode
- ETL pipeline from raw CSV to cleaned Parquet
- DeepSeek-assisted historical air-quality collection agent for user-selected cities
- Sidebar dataset switcher so newly collected parquet files can be explored immediately

## Project Structure
- `app.py`: Landing page
- `pages/`: Streamlit multipage views, including the historical data agent
- `src/`: Shared data, metrics, chart, realtime, and collection-agent modules
- `scripts/build_dataset.py`: ETL from raw dataset to Parquet
- `scripts/generate_demo_data.py`: Synthetic data generator for quick demo
- `tests/`: Unit tests for data, metric, and collection logic
- `Dockerfile`: Container deployment config
- `.streamlit/config.toml`: Streamlit runtime config
- `.github/workflows/streamlit-cloud-check.yml`: GitHub Actions CI (lint/test)

## Data Sources
- Bundled historical example: UCI Beijing Multi-Site Air-Quality Data
- Historical city agent: Open-Meteo Geocoding API + Open-Meteo Air Quality Archive + Open-Meteo Weather Archive
- Optional realtime expansion: OpenAQ API
- Optional planner/summarizer: DeepSeek Chat Completions API

## Quick Start
1. Create and activate a Python 3.14 virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Build demo data (no external download required):
   - `python scripts/generate_demo_data.py --out data/processed/beijing_aq.parquet`
4. Or build from real raw CSV files:
   - Put `PRSA_Data_*.csv` into `data/raw/`
   - Run `python scripts/build_dataset.py --raw data/raw --out data/processed/beijing_aq.parquet`
5. Optional: configure DeepSeek in `.streamlit/secrets.toml` using `.streamlit/secrets.toml.example`
6. Launch app:
   - `streamlit run app.py`

## Historical Data Agent
Open `Historical Data Agent` in the Streamlit sidebar and follow this flow:
1. Enter a city query and optional ISO country code.
2. Pick a resolved city candidate returned by Open-Meteo geocoding.
3. Generate the collection plan.
4. Run the collection agent.
5. Switch to the newly saved parquet file from the sidebar dataset selector on any analysis page.

The agent saves parquet outputs under `data/processed/agent_runs/` so they can be loaded by the existing dashboard pages.

## Coverage Notes
- The agent uses Open-Meteo historical air-quality data.
- For European cities, CAMS Europe coverage starts on `2013-01-01` and is hourly.
- For non-European cities, Open-Meteo global coverage starts on `2022-08-01` and is typically 3-hourly.
- If a requested year range exceeds source availability, the agent clips the range and reports the exact adjusted dates in the plan.

## Docker Deployment
1. Build image:
   - `docker build -t beijing-aq-dashboard .`
2. Run container:
   - `docker run --rm -p 8501:8501 beijing-aq-dashboard`
3. Open browser:
   - `http://localhost:8501`

Notes:
- If `data/processed/beijing_aq.parquet` is missing, the app bootstraps demo data automatically.
- Agent-generated parquet files appear automatically in the app sidebar dataset selector.

## Streamlit Community Cloud Deployment
1. Push this repo to GitHub.
2. In Streamlit Community Cloud, create app and set:
   - Main file path: `app.py`
   - Python version: `3.14` (if available in Cloud UI; otherwise choose latest available and test)
3. In App Settings -> Secrets (optional):
   - `data_path = "data/processed/beijing_aq.parquet"`
   - `deepseek_api_key = "sk-..."`
   - `deepseek_model = "deepseek-v4-flash"`
4. Deploy.

Included config:
- `.streamlit/config.toml`: server/theme defaults.
- `.streamlit/secrets.toml.example`: secrets template.

## GitHub Actions CI (for Cloud pre-check)
- Workflow file: `.github/workflows/streamlit-cloud-check.yml`
- Trigger: `push` (main/master), `pull_request`
- Checks:
  - `Lint (Syntax)`: `py_compile`
  - `Test (Pytest)`: `pytest -q`

## Accepted Data Contract
Processed Parquet should include:
- `timestamp`, `station_id`, `lat`, `lon`
- `pm25`, `pm10`, `no2`, `so2`, `co`, `o3`
- `temp`, `humidity`, `wind_speed`

Optional visualization-clipped columns:
- `pm25_viz`, `pm10_viz`, `no2_viz`, `so2_viz`, `co_viz`, `o3_viz`

## Tests
- `pytest -q`

## Notes
- Realtime panel automatically degrades to historical mode when recent coverage is insufficient.
- If external API contracts change, the historical collection agent and realtime module fail safely with surfaced warnings.
