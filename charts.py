"""
charts.py
Plotly figure builders for the Strava running dashboard.
Each function is pure: accepts a DataFrame, returns a Figure. No Streamlit calls.
"""

import math
import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def weekly_mileage_chart(df: pd.DataFrame) -> go.Figure:
    """Bar chart of weekly mileage, colored by volume.

    Groups runs by ISO week, sorts chronologically, colors bars on a RdYlGn
    continuous scale so high-volume weeks stand out.

    Args:
        df: Filtered runs DataFrame with week_start, week_label, distance_mi

    Returns:
        Plotly Figure
    """
    weekly = (
        df.groupby(["week_start", "week_label"])["distance_mi"]
        .sum()
        .reset_index()
        .sort_values("week_start")
    )
    fig = px.bar(
        weekly,
        x="week_label",
        y="distance_mi",
        color="distance_mi",
        color_continuous_scale="RdYlGn",
        labels={"distance_mi": "Miles", "week_label": "Week"},
        title="Weekly Mileage",
    )
    fig.update_layout(coloraxis_showscale=False, xaxis_tickangle=-45)
    fig.update_traces(
        hovertemplate="<b>%{x}</b><br>%{y:.2f} mi<extra></extra>"
    )
    return fig


def pace_over_time_chart(df: pd.DataFrame) -> go.Figure:
    """Line chart of pace over time with a 4-run rolling average trendline.

    Y-axis displays pace in MM:SS format via custom tick labels.
    Y-axis is inverted so faster paces appear at the top.

    Args:
        df: Filtered runs DataFrame

    Returns:
        Plotly Figure with two traces: individual runs + rolling average
    """
    sorted_df = df.sort_values("start_date_local").copy()
    sorted_df["rolling_pace"] = (
        sorted_df["pace_min_float"].rolling(window=4, min_periods=1).mean()
    )

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=sorted_df["start_date_local"],
        y=sorted_df["pace_min_float"],
        mode="markers",
        name="Individual runs",
        opacity=0.5,
        marker=dict(color="#1f77b4"),
        customdata=sorted_df[["distance_mi", "pace_display"]].values,
        hovertemplate=(
            "<b>%{x|%Y-%m-%d}</b><br>"
            "Distance: %{customdata[0]:.2f} mi<br>"
            "Pace: %{customdata[1]}<extra></extra>"
        ),
    ))

    fig.add_trace(go.Scatter(
        x=sorted_df["start_date_local"],
        y=sorted_df["rolling_pace"],
        mode="lines",
        name="4-run rolling avg",
        line=dict(color="#d62728", width=2),
        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>Avg: %{y:.2f} min/mi<extra></extra>",
    ))

    y_min = sorted_df["pace_min_float"].min()
    y_max = sorted_df["pace_min_float"].max()
    tickvals = _generate_pace_ticks(y_min, y_max, step=0.5)
    ticktext = [_decimal_min_to_mmss(v) for v in tickvals]

    fig.update_layout(
        title="Pace Over Time",
        xaxis_title="Date",
        yaxis_title="Pace (min/mi)",
        yaxis=dict(
            tickvals=tickvals,
            ticktext=ticktext,
            autorange="reversed",
        ),
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


def distance_histogram(df: pd.DataFrame) -> go.Figure:
    """Histogram of run distances in 0.5-mile bins.

    Args:
        df: Filtered runs DataFrame

    Returns:
        Plotly Figure
    """
    fig = px.histogram(
        df,
        x="distance_mi",
        labels={"distance_mi": "Distance (mi)"},
        title="Run Distance Distribution",
    )
    fig.update_traces(
        xbins=dict(start=0, size=0.5),
        hovertemplate="Distance: %{x:.1f} mi<br>Count: %{y}<extra></extra>",
    )
    fig.update_layout(bargap=0.05, yaxis_title="Runs")
    return fig


def training_load_chart(load_df: pd.DataFrame) -> go.Figure:
    """Multi-line chart of CTL, ATL, and TSB over time.

    CTL (fitness) = blue, ATL (fatigue) = red, TSB (form) = dashed green.
    A dotted zero-baseline helps read TSB sign at a glance.

    Args:
        load_df: DataFrame from data.compute_training_load() with
                 columns: date, daily_trimp, ctl, atl, tsb

    Returns:
        Plotly Figure
    """
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=load_df["date"], y=load_df["ctl"],
        name="CTL — Fitness",
        mode="lines",
        line=dict(color="#1f77b4", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=load_df["date"], y=load_df["atl"],
        name="ATL — Fatigue",
        mode="lines",
        line=dict(color="#d62728", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=load_df["date"], y=load_df["tsb"],
        name="TSB — Form",
        mode="lines",
        line=dict(color="#2ca02c", width=2, dash="dash"),
    ))

    fig.add_hline(y=0, line_dash="dot", line_color="gray", line_width=1)

    fig.update_layout(
        title="Training Load: CTL / ATL / TSB",
        xaxis_title="Date",
        yaxis_title="Load (TRIMP units)",
        legend=dict(orientation="h", y=-0.2),
        hovermode="x unified",
    )
    return fig


def race_readiness_chart(
    projected_df: pd.DataFrame,
    race_date: datetime.date,
    target_tsb: float,
) -> go.Figure:
    """Project CTL/ATL/TSB to race day, with race-date marker and target TSB line.

    Args:
        projected_df: Output of coaching.simulate_race_readiness()
        race_date:    Target race date
        target_tsb:   User's desired TSB at race start

    Returns:
        Plotly Figure
    """
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=projected_df["date"], y=projected_df["ctl"],
        name="CTL — Fitness", mode="lines",
        line=dict(color="#1f77b4", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=projected_df["date"], y=projected_df["atl"],
        name="ATL — Fatigue", mode="lines",
        line=dict(color="#d62728", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=projected_df["date"], y=projected_df["tsb"],
        name="TSB — Form", mode="lines",
        line=dict(color="#2ca02c", width=2, dash="dash"),
    ))

    race_ts = pd.Timestamp(race_date)
    fig.add_vline(
        x=race_ts.timestamp() * 1000,
        line_dash="dot", line_color="purple", line_width=2,
        annotation_text="Race Day", annotation_position="top left",
    )
    fig.add_hline(
        y=target_tsb, line_dash="dot", line_color="#2ca02c", line_width=1,
        annotation_text=f"Target TSB {target_tsb}", annotation_position="bottom right",
    )
    fig.add_hline(y=0, line_dash="dot", line_color="gray", line_width=1)

    fig.update_layout(
        title="Race Readiness Projection (Zero-Training Taper)",
        xaxis_title="Date",
        yaxis_title="Load (TRIMP units)",
        legend=dict(orientation="h", y=-0.2),
        hovermode="x unified",
    )
    return fig


def efficiency_chart(df: pd.DataFrame) -> go.Figure:
    """Pace-vs-HR efficiency score over time with a 10-run rolling average.

    Args:
        df: Output of coaching.efficiency_score() with efficiency and rolling_10 columns

    Returns:
        Plotly Figure
    """
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["start_date_local"], y=df["efficiency"],
        mode="markers", name="Individual runs",
        opacity=0.45, marker=dict(color="#1f77b4", size=7),
        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>Efficiency: %{y:.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df["start_date_local"], y=df["rolling_10"],
        mode="lines", name="10-run rolling avg",
        line=dict(color="#d62728", width=2),
        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>Rolling avg: %{y:.2f}<extra></extra>",
    ))

    fig.update_layout(
        title="Pace vs HR Efficiency Score",
        xaxis_title="Date",
        yaxis_title="Efficiency (pace min/km ÷ relative HR)",
        legend=dict(orientation="h", y=-0.2),
        annotations=[dict(
            text="Rising score = getting fitter (same HR, faster pace)",
            xref="paper", yref="paper", x=0.01, y=0.97,
            showarrow=False, font=dict(size=11, color="gray"),
        )],
    )
    return fig


def vo2max_trend_chart(df: pd.DataFrame, reference_vo2: float = 61) -> go.Figure:
    """Estimated VO2max trend over time with trendline and reference line.

    Classifies the last-90-day trend as Improving / Flat / Declining based
    on the linear regression slope (threshold: ±0.05 ml/kg/min per day).

    Args:
        df:            Output of coaching.estimate_vo2max_trend()
        reference_vo2: Known/target VO2max to show as a reference line

    Returns:
        Plotly Figure
    """
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["start_date_local"], y=df["vo2max_est"],
        mode="markers", name="Estimated VO2max",
        opacity=0.4, marker=dict(color="#9467bd", size=7),
        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>Est. VO2max: %{y:.1f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df["start_date_local"], y=df["vo2max_smooth"],
        mode="lines", name="4-run smoothed",
        line=dict(color="#9467bd", width=2),
        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>Smoothed: %{y:.1f}<extra></extra>",
    ))

    # Trendline via linear regression on numeric x
    x_num = np.arange(len(df))
    if len(x_num) >= 2:
        coeffs = np.polyfit(x_num, df["vo2max_smooth"].values, 1)
        trend_y = np.polyval(coeffs, x_num)
        fig.add_trace(go.Scatter(
            x=df["start_date_local"], y=trend_y,
            mode="lines", name="Trend",
            line=dict(color="gray", width=1, dash="dot"),
        ))
        slope = coeffs[0]
        if slope > 0.05:
            trend_label = "Trend: Improving"
            trend_color = "green"
        elif slope < -0.05:
            trend_label = "Trend: Declining"
            trend_color = "red"
        else:
            trend_label = "Trend: Flat"
            trend_color = "gray"
    else:
        trend_label, trend_color = "Trend: Insufficient data", "gray"

    fig.add_hline(
        y=reference_vo2, line_dash="dot", line_color="#ff7f0e", line_width=1,
        annotation_text=f"Reference VO2max {reference_vo2}",
        annotation_position="bottom right",
    )

    fig.update_layout(
        title=f"VO2max Trend (Estimated)  —  <span style='color:{trend_color}'>{trend_label}</span>",
        xaxis_title="Date",
        yaxis_title="VO2max (ml/kg/min)",
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


def hr_zone_chart(zone_df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart of time spent in each HR zone.

    Args:
        zone_df: Output of coaching.hr_zone_distribution() with zone, minutes, pct columns

    Returns:
        Plotly Figure
    """
    zone_colors = {
        "Z1 Recovery (<60%)":      "#aec7e8",
        "Z2 Aerobic Base (60–70%)": "#2ca02c",
        "Z3 Aerobic (70–80%)":      "#ffbb78",
        "Z4 Threshold (80–90%)":    "#ff7f0e",
        "Z5 VO2max (>90%)":         "#d62728",
    }
    colors = [zone_colors.get(z, "#888") for z in zone_df["zone"]]
    labels = [f"{row['pct']:.0f}%  ({row['minutes']:.0f} min)" for _, row in zone_df.iterrows()]

    fig = go.Figure(go.Bar(
        y=zone_df["zone"],
        x=zone_df["minutes"],
        orientation="h",
        marker_color=colors,
        text=labels,
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>%{x:.0f} min<extra></extra>",
    ))

    fig.update_layout(
        title="Heart Rate Zone Distribution (by run time)",
        xaxis_title="Total Minutes",
        yaxis_title="",
        yaxis=dict(autorange="reversed"),
        showlegend=False,
        margin=dict(l=10, r=120),
    )
    return fig


# ── Helpers ────────────────────────────────────────────────────────────────────

def _generate_pace_ticks(y_min: float, y_max: float, step: float = 0.5) -> list:
    """Generate evenly-spaced tick values across a pace range."""
    start = math.floor(y_min / step) * step
    end = math.ceil(y_max / step) * step
    ticks = []
    v = start
    while v <= end + 1e-9:
        ticks.append(round(v, 4))
        v += step
    return ticks


def _decimal_min_to_mmss(decimal_min: float) -> str:
    """Convert decimal minutes to 'M:SS' string for y-axis labels."""
    total_sec = int(round(decimal_min * 60))
    m = total_sec // 60
    s = total_sec % 60
    return f"{m}:{s:02d}"
