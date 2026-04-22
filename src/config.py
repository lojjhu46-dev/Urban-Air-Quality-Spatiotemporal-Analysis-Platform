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
