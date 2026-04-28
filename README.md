# City Air Quality Dashboard

A Streamlit dashboard for historical urban air-quality analysis and DeepSeek-assisted archive collection.

## Features
- Multi-filter linked analysis across pages
- Spatiotemporal playback map for station-level pollution
- Pollutant-weather correlation analysis
- DeepSeek-assisted historical air-quality collection agent for user-selected cities
- Sidebar dataset switcher so newly collected dataset files can be explored immediately
- ETL pipeline from raw CSV to cleaned dashboard-ready datasets

## Project Structure
- `app.py`: Landing page
- `pages/`: Streamlit multipage views for overview, playback, correlation, and the historical data agent
- `src/`: Shared data, metrics, chart, i18n, UI, and collection-agent modules
- `scripts/build_dataset.py`: ETL from raw dataset to processed dataset file
- `scripts/generate_demo_data.py`: Synthetic data generator for quick demo
- `tests/`: Unit tests for data, metric, and collection logic
- `Dockerfile`: Container deployment config
- `.streamlit/config.toml`: Streamlit runtime config

## Data Sources
- Bundled historical example: UCI Beijing Multi-Site Air-Quality Data
- Historical city agent: Open-Meteo Geocoding API + Open-Meteo Air Quality Archive + Open-Meteo Weather Archive
- Optional planner/summarizer: DeepSeek Chat Completions API

## Quick Start
1. Create and activate a Python 3.14 virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Build demo data:
   - `python scripts/generate_demo_data.py --out data/processed/beijing_aq.parquet`
4. Or build from raw CSV files:
   - Put `PRSA_Data_*.csv` into `data/raw/`
   - Run `python scripts/build_dataset.py --raw data/raw --out data/processed/beijing_aq.parquet`
5. Optional: configure DeepSeek in `.streamlit/secrets.toml` using `.streamlit/secrets.toml.example`
6. Launch app:
   - `python -m streamlit run app.py`

Notes:
- If parquet is unavailable in the runtime, the app automatically falls back to CSV dataset files.
- If `data/processed/beijing_aq.parquet` is missing, the app bootstraps demo data automatically.

## Historical Data Agent
Open `Historical Data Agent` in the Streamlit sidebar and use the natural-language workflow:
1. Configure `deepseek_api_key` in Streamlit secrets.
2. Describe the target city, year range, pollutants, and whether weather columns should be included.
3. Use `Agent: Draft Plan` to inspect the plan or `Agent: Plan and Collect` to execute collection.
4. Switch to the newly saved dataset file from the sidebar dataset selector on any analysis page.

The agent saves outputs under `data/processed/agent_runs/` and falls back to CSV automatically when parquet support is blocked.

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

## Streamlit Community Cloud Deployment
1. Push this repo to GitHub.
2. In Streamlit Community Cloud, create app and set:
   - Main file path: `app.py`
   - Python version: `3.14` (if available; otherwise choose the latest available version and test)
3. In App Settings -> Secrets (optional):
   - `data_path = "data/processed/beijing_aq.parquet"`
   - `deepseek_api_key = "sk-..."`
   - `deepseek_model = "deepseek-v4-flash"`
4. Deploy.

## Accepted Data Contract
Processed datasets should include:
- `timestamp`, `station_id`, `lat`, `lon`
- `pm25`, `pm10`, `no2`, `so2`, `co`, `o3`
- `temp`, `humidity`, `wind_speed`

Optional visualization-clipped columns:
- `pm25_viz`, `pm10_viz`, `no2_viz`, `so2_viz`, `co_viz`, `o3_viz`

## Tests
- `pytest -q`
