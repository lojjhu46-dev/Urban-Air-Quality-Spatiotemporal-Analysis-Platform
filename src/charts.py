from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def trend_figure(df: pd.DataFrame, pollutant: str) -> go.Figure:
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
        title=f"Daily trend: {pollutant.upper()}",
    )
    fig.update_layout(legend_title_text="Station", margin=dict(l=10, r=10, t=45, b=10))
    return fig


def ranking_figure(df: pd.DataFrame, pollutant: str) -> go.Figure:
    if df.empty or pollutant not in df.columns:
        return go.Figure()

    fig = px.bar(
        df,
        x=pollutant,
        y="station_id",
        orientation="h",
        title=f"Station ranking ({pollutant.upper()})",
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, margin=dict(l=10, r=10, t=45, b=10))
    return fig


def map_figure(df: pd.DataFrame, pollutant: str) -> go.Figure:
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
        title=f"Station distribution: {pollutant.upper()}",
        labels={"lon": "Longitude", "lat": "Latitude"},
    )
    fig.update_yaxes(scaleanchor="x", scaleratio=1)

    fig.update_layout(margin=dict(l=10, r=10, t=45, b=10))
    return fig


def correlation_heatmap(corr: pd.DataFrame) -> go.Figure:
    if corr.empty:
        return go.Figure()

    fig = px.imshow(
        corr,
        text_auto=True,
        aspect="auto",
        color_continuous_scale="RdBu_r",
        zmin=-1,
        zmax=1,
        title="Correlation matrix",
    )
    fig.update_layout(margin=dict(l=10, r=10, t=45, b=10))
    return fig


def scatter_with_regression(df: pd.DataFrame, x_col: str, y_col: str, max_points: int = 8000) -> go.Figure:
    fig = go.Figure()
    if df.empty or x_col not in df.columns or y_col not in df.columns:
        return fig

    working = df[[x_col, y_col]].dropna()
    if working.empty:
        return fig

    if len(working) > max_points:
        working = working.sample(n=max_points, random_state=42)

    # Use SVG scatter for maximum browser compatibility (no WebGL dependency).
    fig.add_trace(
        go.Scatter(
            x=working[x_col],
            y=working[y_col],
            mode="markers",
            name="Samples",
            marker={"size": 5, "opacity": 0.45},
        )
    )

    if len(working) >= 2:
        coef = np.polyfit(working[x_col], working[y_col], deg=1)
        x_line = np.linspace(float(working[x_col].min()), float(working[x_col].max()), 100)
        y_line = coef[0] * x_line + coef[1]
        fig.add_trace(
            go.Scatter(x=x_line, y=y_line, mode="lines", name="Linear fit", line={"width": 2})
        )

    fig.update_layout(
        title=f"{y_col.upper()} vs {x_col}",
        xaxis_title=x_col,
        yaxis_title=y_col.upper(),
        margin=dict(l=10, r=10, t=45, b=10),
    )
    return fig
