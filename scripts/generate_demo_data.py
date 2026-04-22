from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from src.config import POLLUTANT_COLUMNS, STATION_COORDS, TIMEZONE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic Beijing AQ dataset for demo usage.")
    parser.add_argument("--out", type=Path, required=True, help="Output parquet path")
    parser.add_argument("--days", type=int, default=60, help="Number of historical days")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = np.random.default_rng(args.seed)

    end_ts = pd.Timestamp.now(tz=TIMEZONE).floor("h")
    start_ts = end_ts - pd.Timedelta(days=args.days)
    hours = pd.date_range(start=start_ts, end=end_ts, freq="h", tz=TIMEZONE)

    rows: list[dict[str, float | str | pd.Timestamp]] = []
    station_names = sorted(STATION_COORDS.keys())

    for station in station_names:
        lat, lon = STATION_COORDS[station]
        station_bias = rng.normal(0, 7)

        for ts in hours:
            hour_of_day = ts.hour
            day_of_year = ts.dayofyear
            seasonal = 18 * np.sin(2 * np.pi * day_of_year / 365)
            diurnal = 14 * np.sin(2 * np.pi * hour_of_day / 24)
            noise = rng.normal(0, 9)
            pm25 = max(5, 70 + station_bias + seasonal + diurnal + noise)

            row = {
                "timestamp": ts,
                "station_id": station,
                "lat": lat,
                "lon": lon,
                "pm25": pm25,
                "pm10": max(8, pm25 * 1.4 + rng.normal(0, 12)),
                "no2": max(4, 45 + 0.35 * diurnal + rng.normal(0, 7)),
                "so2": max(1, 12 + rng.normal(0, 3)),
                "co": max(0.2, 1.3 + rng.normal(0, 0.25)),
                "o3": max(3, 85 - 0.4 * diurnal + rng.normal(0, 10)),
                "temp": 12 + 10 * np.sin(2 * np.pi * (hour_of_day - 6) / 24) + rng.normal(0, 1.8),
                "humidity": np.clip(65 - 20 * np.sin(2 * np.pi * (hour_of_day - 6) / 24) + rng.normal(0, 8), 15, 98),
                "wind_speed": np.clip(2.4 + rng.normal(0, 0.9), 0.1, 9.0),
            }
            rows.append(row)

    df = pd.DataFrame(rows).sort_values(["timestamp", "station_id"]).reset_index(drop=True)

    for col in POLLUTANT_COLUMNS:
        lower = df[col].quantile(0.01)
        upper = df[col].quantile(0.99)
        df[f"{col}_viz"] = df[col].clip(lower, upper)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)

    print(f"[OK] Wrote demo data to {args.out}")
    print(f"[OK] Rows: {len(df):,}, Stations: {df['station_id'].nunique()}")


if __name__ == "__main__":
    main()
