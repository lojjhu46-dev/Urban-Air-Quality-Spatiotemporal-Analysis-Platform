# Beijing Air Quality Spatiotemporal Analysis

A medium-complexity data visualization project using Python 3.14, Streamlit, and Plotly.

## Features
- Multi-filter linked dashboard across pages
- Spatiotemporal playback map for station-level pollution
- Pollutant-weather correlation analysis
- Optional OpenAQ realtime panel with fallback mode
- ETL pipeline from raw CSV to cleaned Parquet

## Project Structure
- `app.py`: Landing page
- `pages/`: Streamlit multipage views
- `src/`: Shared data, metrics, chart, and realtime modules
- `scripts/build_dataset.py`: ETL from raw dataset to Parquet
- `scripts/generate_demo_data.py`: Synthetic data generator for quick demo
- `tests/`: Unit tests for data and metric logic
- `Dockerfile`: Container deployment config
- `.streamlit/config.toml`: Streamlit runtime config
- `.github/workflows/streamlit-cloud-check.yml`: GitHub Actions CI (lint/test)

## Data Sources
- Primary historical data: UCI Beijing Multi-Site Air-Quality Data
- Weather supplement: Open-Meteo historical API
- Optional realtime expansion: OpenAQ API

## Quick Start
1. Create and activate a Python 3.14 virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Build demo data (no external download required):
   - `python scripts/generate_demo_data.py --out data/processed/beijing_aq.parquet`
4. Or build from real raw CSV files:
   - Put `PRSA_Data_*.csv` into `data/raw/`
   - Run `python scripts/build_dataset.py --raw data/raw --out data/processed/beijing_aq.parquet`
5. Launch app:
   - `streamlit run app.py`

## Docker Deployment
1. Build image:
   - `docker build -t beijing-aq-dashboard .`
2. Run container:
   - `docker run --rm -p 8501:8501 beijing-aq-dashboard`
3. Open browser:
   - `http://localhost:8501`

Notes:
- If `data/processed/beijing_aq.parquet` is missing, app bootstraps demo data automatically.
- For real datasets, mount a volume and point `data_path` via Streamlit secrets if needed.

## Streamlit Community Cloud Deployment
1. Push this repo to GitHub.
2. In Streamlit Community Cloud, create app and set:
   - Main file path: `app.py`
   - Python version: `3.14` (if available in Cloud UI; otherwise choose latest available and test)
3. In App Settings -> Secrets (optional):
   - `data_path = "data/processed/beijing_aq.parquet"`
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

This gives a lightweight gate before Streamlit Cloud rebuild/deploy.

## Accepted Data Contract
Processed Parquet must include:
- `timestamp`, `station_id`, `lat`, `lon`
- `pm25`, `pm10`, `no2`, `so2`, `co`, `o3`
- `temp`, `humidity`, `wind_speed`

Optional visualization-clipped columns:
- `pm25_viz`, `pm10_viz`, `no2_viz`, `so2_viz`, `co_viz`, `o3_viz`

## Tests
- `pytest -q`

## Notes
- Realtime panel automatically degrades to historical mode when recent coverage is insufficient.
- If OpenAQ endpoint changes, the realtime module fails safely without breaking historical pages.
