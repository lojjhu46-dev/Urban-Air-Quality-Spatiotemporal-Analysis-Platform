from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import requests

from src.data import write_dataset
from src.config import BEIJING_CENTER, POLLUTANT_COLUMNS, STATION_COORDS, TIMEZONE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build processed Beijing AQ dataset from raw CSV files.")
    parser.add_argument("--raw", type=Path, required=True, help="Directory containing PRSA_Data_*.csv")
    parser.add_argument("--out", type=Path, required=True, help="Output dataset path (.parquet or .csv)")
    parser.add_argument("--skip-weather-api", action="store_true", help="Skip Open-Meteo weather supplement")
    return parser.parse_args()


def read_raw_files(raw_dir: Path) -> pd.DataFrame:
    files = sorted(raw_dir.glob("PRSA_Data_*.csv"))
    if not files:
        files = sorted(raw_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found in {raw_dir}")

    frames: list[pd.DataFrame] = []
    for file in files:
        frame = pd.read_csv(file)
        frames.append(frame)

    merged = pd.concat(frames, ignore_index=True)
    return merged


def relative_humidity_from_temp_dewp(temp: pd.Series, dewp: pd.Series) -> pd.Series:
    temp = temp.astype(float)
    dewp = dewp.astype(float)
    num = np.exp((17.625 * dewp) / (243.04 + dewp))
    den = np.exp((17.625 * temp) / (243.04 + temp))
    rh = 100.0 * (num / den)
    return rh.clip(0, 100)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "station": "station_id",
        "PM2.5": "pm25",
        "PM10": "pm10",
        "SO2": "so2",
        "NO2": "no2",
        "CO": "co",
        "O3": "o3",
        "TEMP": "temp_local",
        "DEWP": "dewp_local",
        "WSPM": "wind_speed_local",
    }

    out = df.rename(columns=rename_map).copy()
    required = ["year", "month", "day", "hour", "station_id"]
    missing = [col for col in required if col not in out.columns]
    if missing:
        raise ValueError(f"Raw data missing required columns: {missing}")

    out["timestamp"] = pd.to_datetime(
        out[["year", "month", "day", "hour"]],
        errors="coerce",
    )
    out = out.dropna(subset=["timestamp", "station_id"])
    out["timestamp"] = out["timestamp"].dt.tz_localize(TIMEZONE)

    for col in POLLUTANT_COLUMNS + ["temp_local", "dewp_local", "wind_speed_local"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    for col in POLLUTANT_COLUMNS:
        if col in out.columns:
            out.loc[out[col] < 0, col] = np.nan

    if "wind_speed_local" in out.columns:
        out.loc[out["wind_speed_local"] < 0, "wind_speed_local"] = np.nan

    needed = ["timestamp", "station_id"] + [c for c in POLLUTANT_COLUMNS if c in out.columns]
    optional = [col for col in ["temp_local", "dewp_local", "wind_speed_local"] if col in out.columns]
    out = out[needed + optional]

    return out


def reindex_hourly(df: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    value_cols = [c for c in POLLUTANT_COLUMNS if c in df.columns]
    local_weather_cols = [c for c in ["temp_local", "dewp_local", "wind_speed_local"] if c in df.columns]

    for station_id, station_df in df.groupby("station_id"):
        station_df = station_df.sort_values("timestamp").set_index("timestamp")
        full_idx = pd.date_range(station_df.index.min(), station_df.index.max(), freq="h", tz=TIMEZONE)
        station_df = station_df.reindex(full_idx)
        station_df.index.name = "timestamp"
        station_df["station_id"] = station_id

        for col in value_cols + local_weather_cols:
            station_df[col] = station_df[col].interpolate(method="time", limit=3, limit_area="inside")

        frames.append(station_df.reset_index())

    return pd.concat(frames, ignore_index=True)


def fetch_open_meteo(start_date: str, end_date: str) -> pd.DataFrame:
    lat, lon = BEIJING_CENTER
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "timezone": TIMEZONE,
    }
    response = requests.get(url, params=params, timeout=45)
    response.raise_for_status()
    payload = response.json()

    hourly = payload.get("hourly", {})
    if not hourly:
        return pd.DataFrame()

    ts = pd.to_datetime(hourly.get("time", []), errors="coerce")
    ts = ts.tz_localize(TIMEZONE)

    frame = pd.DataFrame(
        {
            "timestamp": ts,
            "temp_api": pd.to_numeric(hourly.get("temperature_2m", []), errors="coerce"),
            "humidity_api": pd.to_numeric(hourly.get("relative_humidity_2m", []), errors="coerce"),
            "wind_speed_api": pd.to_numeric(hourly.get("wind_speed_10m", []), errors="coerce"),
        }
    )
    return frame.dropna(subset=["timestamp"]).sort_values("timestamp")


def attach_station_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["lat"] = out["station_id"].map(lambda s: STATION_COORDS.get(s, BEIJING_CENTER)[0])
    out["lon"] = out["station_id"].map(lambda s: STATION_COORDS.get(s, BEIJING_CENTER)[1])
    return out


def finalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if {"temp_local", "dewp_local"}.issubset(set(out.columns)):
        out["humidity_local"] = relative_humidity_from_temp_dewp(out["temp_local"], out["dewp_local"])
    else:
        out["humidity_local"] = np.nan

    out["temp"] = out.get("temp_api", pd.Series(np.nan, index=out.index)).combine_first(out.get("temp_local"))
    out["humidity"] = out.get("humidity_api", pd.Series(np.nan, index=out.index)).combine_first(out.get("humidity_local"))
    out["wind_speed"] = out.get("wind_speed_api", pd.Series(np.nan, index=out.index)).combine_first(out.get("wind_speed_local"))

    for col in POLLUTANT_COLUMNS:
        if col in out.columns:
            q = out[col].dropna()
            if q.empty:
                out[f"{col}_viz"] = out[col]
            else:
                lower = q.quantile(0.01)
                upper = q.quantile(0.99)
                out[f"{col}_viz"] = out[col].clip(lower, upper)

    keep = [
        "timestamp",
        "station_id",
        "lat",
        "lon",
        *[c for c in POLLUTANT_COLUMNS if c in out.columns],
        "temp",
        "humidity",
        "wind_speed",
        *[f"{c}_viz" for c in POLLUTANT_COLUMNS if f"{c}_viz" in out.columns],
    ]

    out = out[keep].sort_values(["timestamp", "station_id"]).reset_index(drop=True)
    return out


def main() -> None:
    args = parse_args()
    raw_df = read_raw_files(args.raw)
    normalized = normalize_columns(raw_df)
    hourly = reindex_hourly(normalized)
    hourly = attach_station_coordinates(hourly)

    if args.skip_weather_api:
        weather = pd.DataFrame()
    else:
        start_date = hourly["timestamp"].min().date().isoformat()
        end_date = hourly["timestamp"].max().date().isoformat()
        try:
            weather = fetch_open_meteo(start_date, end_date)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Open-Meteo unavailable, fallback to local weather columns only: {exc}")
            weather = pd.DataFrame()

    merged = hourly
    if not weather.empty:
        merged = merged.merge(weather, on="timestamp", how="left")

    final = finalize_columns(merged)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    actual_out = write_dataset(final, args.out)

    print(f"[OK] Wrote {len(final):,} rows to {actual_out}")
    print(f"[OK] Time range: {final['timestamp'].min()} -> {final['timestamp'].max()}")
    print(f"[OK] Stations: {final['station_id'].nunique()}")


if __name__ == "__main__":
    main()
