from __future__ import annotations

from pathlib import Path

TIMEZONE = "Asia/Shanghai"

POLLUTANT_COLUMNS = ["pm25", "pm10", "no2", "so2", "co", "o3"]
WEATHER_COLUMNS = ["temp", "humidity", "wind_speed"]

POLLUTANT_THRESHOLDS = {
    "pm25": 75.0,
    "pm10": 150.0,
    "no2": 200.0,
    "so2": 500.0,
    "co": 10.0,
    "o3": 200.0,
}

REALTIME_MIN_COVERAGE = 0.60

DEFAULT_DATA_PATH = Path("data/processed/beijing_aq.parquet")
AQ_AGENT_OUTPUT_DIR = Path("data/processed/agent_runs")

AQ_AGENT_POLLUTANTS = {
    "pm25": {"label": "PM2.5", "api_field": "pm2_5"},
    "pm10": {"label": "PM10", "api_field": "pm10"},
    "no2": {"label": "NO2", "api_field": "nitrogen_dioxide"},
    "so2": {"label": "SO2", "api_field": "sulphur_dioxide"},
    "co": {"label": "CO", "api_field": "carbon_monoxide"},
    "o3": {"label": "O3", "api_field": "ozone"},
}

AQ_AGENT_DEFAULT_MODEL = "deepseek-v4-flash"
AQ_AGENT_CHUNK_DAYS = 90

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
OPEN_METEO_WEATHER_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

CAMS_EUROPE_START_DATE = "2013-01-01"
OPEN_METEO_GLOBAL_START_DATE = "2022-08-01"

EUROPE_COUNTRY_CODES = {
    "AL",
    "AD",
    "AT",
    "BY",
    "BE",
    "BA",
    "BG",
    "HR",
    "CY",
    "CZ",
    "DK",
    "EE",
    "FI",
    "FR",
    "DE",
    "GI",
    "GR",
    "HU",
    "IS",
    "IE",
    "IT",
    "XK",
    "LV",
    "LI",
    "LT",
    "LU",
    "MT",
    "MD",
    "MC",
    "ME",
    "NL",
    "MK",
    "NO",
    "PL",
    "PT",
    "RO",
    "RU",
    "SM",
    "RS",
    "SK",
    "SI",
    "ES",
    "SE",
    "CH",
    "TR",
    "UA",
    "GB",
    "VA",
}

STATION_COORDS = {
    "Aotizhongxin": (39.982, 116.397),
    "Changping": (40.217, 116.231),
    "Dingling": (40.292, 116.220),
    "Dongsi": (39.929, 116.417),
    "Guanyuan": (39.929, 116.339),
    "Gucheng": (39.914, 116.184),
    "Huairou": (40.358, 116.632),
    "Nongzhanguan": (39.933, 116.461),
    "Shunyi": (40.127, 116.655),
    "Tiantan": (39.886, 116.407),
    "Wanliu": (39.987, 116.287),
    "Wanshouxigong": (39.878, 116.352),
}

BEIJING_CENTER = (39.9042, 116.4074)
