from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.i18n import t, weather_label


def _display_name(column: str, language: str | None = None) -> str:
    if column in {"temp", "humidity", "wind_speed"}:
        return weather_label(column, language)
    return column.upper()


def trend_figure(df: pd.DataFrame, pollutant: str, language: str | None = None) -> go.Figure:
    if df.empty or pollutant not in df.columns:
        return go.Figure()

    series = (
        df.set_index("timestamp")
        .groupby("station_id", observed=True)[pollutant]
        .resample("D")
        .mean()
        .reset_index()
    )

    fig = px.line(
        series,
        x="timestamp",
        y=pollutant,
        color="station_id",
        render_mode="svg",
        title=t("chart.daily_trend", language, pollutant=pollutant.upper()),
    )
    fig.update_layout(legend_title_text=t("chart.station", language), margin=dict(l=10, r=10, t=45, b=10))
    return fig


def ranking_figure(df: pd.DataFrame, pollutant: str, language: str | None = None) -> go.Figure:
    if df.empty or pollutant not in df.columns:
        return go.Figure()

    fig = px.bar(
        df,
        x=pollutant,
        y="station_id",
        orientation="h",
        title=t("chart.station_ranking", language, pollutant=pollutant.upper()),
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, margin=dict(l=10, r=10, t=45, b=10))
    return fig


def map_figure(df: pd.DataFrame, pollutant: str, language: str | None = None) -> go.Figure:
    if df.empty or pollutant not in df.columns:
        return go.Figure()

    working = df.copy()
    working["marker_size"] = np.clip(np.nan_to_num(working[pollutant].to_numpy(), nan=0.0), 5, None)

    fig = px.scatter(
        working,
        x="lon",
        y="lat",
        size="marker_size",
        color=pollutant,
        hover_name="station_id",
        color_continuous_scale="Turbo",
        render_mode="svg",
        title=t("chart.station_distribution", language, pollutant=pollutant.upper()),
        labels={"lon": t("chart.longitude", language), "lat": t("chart.latitude", language)},
    )
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    fig.update_layout(margin=dict(l=10, r=10, t=45, b=10))
    return fig


def correlation_heatmap(corr: pd.DataFrame, language: str | None = None) -> go.Figure:
    if corr.empty:
        return go.Figure()

    renamed = corr.rename(index=lambda value: _display_name(str(value), language), columns=lambda value: _display_name(str(value), language))
    fig = px.imshow(
        renamed,
        text_auto=True,
        aspect="auto",
        color_continuous_scale="RdBu_r",
        zmin=-1,
        zmax=1,
        title=t("chart.correlation_matrix", language),
    )
    fig.update_layout(margin=dict(l=10, r=10, t=45, b=10))
    return fig


def scatter_with_regression(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    max_points: int = 8000,
    language: str | None = None,
) -> go.Figure:
    fig = go.Figure()
    if df.empty or x_col not in df.columns or y_col not in df.columns:
        return fig

    working = df[[x_col, y_col]].dropna()
    if working.empty:
        return fig

    if len(working) > max_points:
        working = working.sample(n=max_points, random_state=42)

    x_title = _display_name(x_col, language)
    y_title = _display_name(y_col, language)

    fig.add_trace(
        go.Scatter(
            x=working[x_col],
            y=working[y_col],
            mode="markers",
            name=t("chart.samples", language),
            marker={"size": 5, "opacity": 0.45},
        )
    )

    if len(working) >= 2:
        coef = np.polyfit(working[x_col], working[y_col], deg=1)
        x_line = np.linspace(float(working[x_col].min()), float(working[x_col].max()), 100)
        y_line = coef[0] * x_line + coef[1]
        fig.add_trace(
            go.Scatter(x=x_line, y=y_line, mode="lines", name=t("chart.linear_fit", language), line={"width": 2})
        )

    fig.update_layout(
        title=t("chart.vs", language, y=y_title, x=x_title),
        xaxis_title=x_title,
        yaxis_title=y_title,
        margin=dict(l=10, r=10, t=45, b=10),
    )
    return fig
