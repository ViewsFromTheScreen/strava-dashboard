"""
coaching.py
Coaching intelligence calculations for the Strava running dashboard.
Pure functions — no Streamlit calls, no I/O.
"""

import datetime
import numpy as np
import pandas as pd

_METERS_PER_MILE = 1609.34


def ramp_rate(load_df: pd.DataFrame) -> dict:
    """Week-over-week CTL change percentage with status and coaching message."""
    today = load_df["date"].max()
    this_week = load_df[load_df["date"] > today - pd.Timedelta(days=7)]["ctl"].mean()
    last_week = load_df[
        (load_df["date"] > today - pd.Timedelta(days=14))
        & (load_df["date"] <= today - pd.Timedelta(days=7))
    ]["ctl"].mean()

    if pd.isna(last_week) or last_week == 0:
        return {
            "pct_change": 0.0,
            "status": "green",
            "message": "Not enough history to calculate ramp rate.",
        }

    pct_change = (this_week - last_week) / last_week * 100

    if pct_change < 5:
        status = "green"
        message = f"Load up {pct_change:.1f}% week-over-week — sustainable progression."
    elif pct_change < 10:
        status = "yellow"
        message = f"Load up {pct_change:.1f}% — approaching the 10% guideline. Monitor fatigue closely."
    else:
        status = "red"
        message = (
            f"Load up {pct_change:.1f}% — exceeds the safe ramp rate. "
            "Consider an easy week to reduce injury risk."
        )

    return {"pct_change": pct_change, "status": status, "message": message}


def daily_recommendation(tsb: float) -> dict:
    """Coaching message for today based on current TSB value."""
    if tsb < -20:
        return {
            "band": "Rest Only",
            "message": (
                f"TSB {tsb:.1f} — Significant accumulated fatigue. "
                "Take a full rest day or very light cross-training. Hard efforts now raise injury risk."
            ),
            "color": "error",
        }
    elif tsb < 0:
        return {
            "band": "Easy Recovery Run",
            "message": (
                f"TSB {tsb:.1f} — Keep it short and comfortable. "
                "Aerobic recovery only — no intensity today."
            ),
            "color": "warning",
        }
    elif tsb < 10:
        return {
            "band": "Moderate Aerobic",
            "message": (
                f"TSB {tsb:.1f} — Good for a steady aerobic run. "
                "Hold off on hard efforts until TSB climbs above 10."
            ),
            "color": "info",
        }
    elif tsb <= 25:
        return {
            "band": "Green Light",
            "message": (
                f"TSB {tsb:.1f} — You're fresh and fit. "
                "Green light for a hard workout, tempo run, or long run."
            ),
            "color": "success",
        }
    else:
        return {
            "band": "Race Ready",
            "message": (
                f"TSB {tsb:.1f} — Peak freshness. "
                "Race ready — a hard effort today will yield a top performance."
            ),
            "color": "info",
        }


def simulate_race_readiness(
    current_ctl: float,
    current_atl: float,
    race_date: datetime.date,
    target_tsb: float,
) -> pd.DataFrame:
    """Project CTL/ATL/TSB forward to race_date assuming zero training (pure taper).

    Daily EWM decay: ctl *= (1 - 2/43), atl *= (1 - 2/8)
    Returns DataFrame with columns: date, ctl, atl, tsb
    """
    today = datetime.date.today()
    n_days = (race_date - today).days
    if n_days <= 0:
        return pd.DataFrame(columns=["date", "ctl", "atl", "tsb"])

    decay_ctl = 1 - 2 / 43  # span=42
    decay_atl = 1 - 2 / 8   # span=7

    rows = []
    ctl, atl = current_ctl, current_atl
    for i in range(1, n_days + 1):
        ctl *= decay_ctl
        atl *= decay_atl
        rows.append({
            "date": pd.Timestamp(today + datetime.timedelta(days=i)),
            "ctl": ctl,
            "atl": atl,
            "tsb": ctl - atl,
        })
    return pd.DataFrame(rows)


def estimate_vo2max_trend(
    df: pd.DataFrame,
    rest_hr: int,
    max_hr: int,
) -> pd.DataFrame:
    """Estimate VO2max per run from average pace + HR using ACSM submaximal formula.

    vo2_at_pace = -4.60 + 0.182258 * speed_mpm + 0.000104 * speed_mpm^2
    vo2max_est  = vo2_at_pace * (max_hr / avg_hr)
    Returns DataFrame with columns: start_date_local, vo2max_est, vo2max_smooth
    """
    hr_runs = df[df["average_heartrate"].notna() & (df["average_heartrate"] > 0)].copy()
    if hr_runs.empty:
        return pd.DataFrame()

    hr_runs = hr_runs.sort_values("start_date_local")
    hr_runs["speed_mpm"] = (_METERS_PER_MILE / hr_runs["pace_sec_per_mi"]) * 60
    hr_runs["vo2_at_pace"] = (
        -4.60
        + 0.182258 * hr_runs["speed_mpm"]
        + 0.000104 * hr_runs["speed_mpm"] ** 2
    )
    hr_runs["vo2max_est"] = (
        hr_runs["vo2_at_pace"] * max_hr / hr_runs["average_heartrate"]
    ).clip(20, 90)
    hr_runs["vo2max_smooth"] = hr_runs["vo2max_est"].rolling(4, min_periods=1).mean()

    return hr_runs[["start_date_local", "vo2max_est", "vo2max_smooth"]].reset_index(drop=True)


def efficiency_score(
    df: pd.DataFrame,
    rest_hr: int,
    max_hr: int,
) -> pd.DataFrame:
    """Pace-per-HR efficiency score for runs with heart rate data.

    efficiency = pace_min_per_km / relative_hr
    relative_hr = clip((avg_hr - rest_hr) / (max_hr - rest_hr), 0.01, 1.0)
    A rising score means you run the same pace at lower relative HR — i.e., getting fitter.
    Returns DataFrame with efficiency and rolling_10 columns.
    """
    hr_runs = df[df["average_heartrate"].notna() & (df["average_heartrate"] > 0)].copy()
    if hr_runs.empty:
        return pd.DataFrame()

    hr_runs = hr_runs.sort_values("start_date_local")
    hr_runs["pace_min_per_km"] = hr_runs["pace_sec_per_mi"] / 60 * 1.60934
    hr_runs["relative_hr"] = (
        (hr_runs["average_heartrate"] - rest_hr) / (max_hr - rest_hr)
    ).clip(0.01, 1.0)
    hr_runs["efficiency"] = hr_runs["pace_min_per_km"] / hr_runs["relative_hr"]
    hr_runs["rolling_10"] = hr_runs["efficiency"].rolling(10, min_periods=1).mean()

    return hr_runs[
        ["start_date_local", "distance_mi", "efficiency", "rolling_10", "average_heartrate"]
    ].reset_index(drop=True)


def long_run_fatigue_debt(
    df: pd.DataFrame,
    load_df: pd.DataFrame,
) -> dict | None:
    """Estimate recovery days after the most recent long run (>90 min).

    debt_days = max(0, round((run_trimp - avg_daily_load) / 15))
    Returns None if no qualifying long run exists.
    """
    long_runs = df[df["moving_time"] > 5400].sort_values("start_date_local", ascending=False)
    if long_runs.empty:
        return None

    latest = long_runs.iloc[0]
    run_date = latest["start_date_local"].date()

    day_rows = load_df[load_df["date"].dt.date == run_date]["daily_trimp"]
    run_trimp = float(day_rows.iloc[0]) if not day_rows.empty else 0.0

    avg_daily = float(load_df.tail(28)["daily_trimp"].mean())
    debt_days = max(0, round((run_trimp - avg_daily) / 15))
    earliest_hard = run_date + datetime.timedelta(days=debt_days)

    return {
        "run_date": run_date,
        "distance_mi": latest["distance_mi"],
        "run_trimp": run_trimp,
        "debt_days": debt_days,
        "earliest_hard": earliest_hard,
        "avg_daily_load": avg_daily,
    }


def monotony_strain(load_df: pd.DataFrame) -> dict:
    """Banister's training monotony and strain for the last 7 days.

    monotony = mean(daily_load) / std(daily_load)
    strain   = weekly_load * monotony
    Flags monotony > 2.0 as a warning.
    """
    last_7 = load_df.tail(7)["daily_trimp"]
    mean_load = float(last_7.mean())
    std_load = float(last_7.std())

    monotony = 0.0 if (std_load == 0 or np.isnan(std_load)) else mean_load / std_load
    weekly_load = float(last_7.sum())

    return {
        "monotony": monotony,
        "strain": weekly_load * monotony,
        "weekly_load": weekly_load,
        "flag": monotony > 2.0,
    }


def hr_zone_distribution(df: pd.DataFrame, max_hr: int) -> pd.DataFrame:
    """Classify runs by average HR zone and compute total minutes + % per zone.

    Zones are based on % of max HR (Garmin/Polar standard):
      Z1 <60%, Z2 60-70%, Z3 70-80%, Z4 80-90%, Z5 >90%
    Returns DataFrame with columns: zone, minutes, pct (sorted Z1→Z5).
    """
    hr_runs = df[df["average_heartrate"].notna() & (df["average_heartrate"] > 0)].copy()
    if hr_runs.empty:
        return pd.DataFrame()

    zone_order = [
        "Z1 Recovery (<60%)",
        "Z2 Aerobic Base (60–70%)",
        "Z3 Aerobic (70–80%)",
        "Z4 Threshold (80–90%)",
        "Z5 VO2max (>90%)",
    ]

    def _zone(hr):
        pct = hr / max_hr * 100
        if pct < 60:
            return zone_order[0]
        elif pct < 70:
            return zone_order[1]
        elif pct < 80:
            return zone_order[2]
        elif pct < 90:
            return zone_order[3]
        return zone_order[4]

    hr_runs["zone"] = hr_runs["average_heartrate"].apply(_zone)
    hr_runs["duration_min"] = hr_runs["moving_time"] / 60

    totals = hr_runs.groupby("zone")["duration_min"].sum().reset_index()
    totals.columns = ["zone", "minutes"]
    totals["pct"] = totals["minutes"] / totals["minutes"].sum() * 100
    totals["zone"] = pd.Categorical(totals["zone"], categories=zone_order, ordered=True)
    return totals.sort_values("zone").reset_index(drop=True)


def personal_records(df: pd.DataFrame) -> list[dict]:
    """Find best pace for 5K, 10K, half marathon, and marathon distances.

    Uses a 5% distance tolerance to handle GPS drift on short-course runs.
    Returns list of dicts with keys: Race, Best Pace, Date, Distance.
    """
    targets = [
        ("5K", 3.107),
        ("10K", 6.214),
        ("Half Marathon", 13.109),
        ("Marathon", 26.219),
    ]
    records = []
    for label, min_dist in targets:
        candidates = df[
            df["distance_mi"] >= min_dist * 0.95
        ].dropna(subset=["pace_sec_per_mi"])
        if candidates.empty:
            records.append({"Race": label, "Best Pace": "—", "Date": "—", "Distance": "—"})
            continue
        best = candidates.loc[candidates["pace_sec_per_mi"].idxmin()]
        records.append({
            "Race": label,
            "Best Pace": best["pace_display"],
            "Date": best["start_date_local"].strftime("%Y-%m-%d"),
            "Distance": f'{best["distance_mi"]:.2f} mi',
        })
    return records
