"""
data.py
Fetches, transforms, and filters Strava running activity data.
All unit conversions happen here; downstream modules receive clean DataFrames.
"""

import time
import datetime
import requests
import pandas as pd
import numpy as np
import os

BASE_URL = "https://www.strava.com/api/v3"
METERS_PER_MILE = 1609.34
FEET_PER_METER = 3.28084


def fetch_runs(headers: dict) -> pd.DataFrame:
    """Fetch all Run activities from the last 90 days, paginated.

    Calls GET /athlete/activities with after=now-90d, per_page=200, paginating
    until the API returns an empty batch. Filters to sport_type == "Run".

    Args:
        headers: Auth headers from auth.get_auth_headers()

    Returns:
        Transformed DataFrame. Empty DataFrame if no runs found.

    Raises:
        requests.HTTPError: on API error (401, 429, 5xx)
    """
    after_ts = int(
        (datetime.datetime.utcnow() - datetime.timedelta(days=90)).timestamp()
    )
    activities = []
    page = 1

    while True:
        resp = requests.get(
            f"{BASE_URL}/athlete/activities",
            headers=headers,
            params={"per_page": 200, "page": page, "after": after_ts},
            timeout=15,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        activities.extend(batch)
        page += 1
        if page > 1:
            time.sleep(0.3)  # conservative rate limiting

    if not activities:
        return pd.DataFrame()

    df = pd.DataFrame(activities)
    df = df[df["sport_type"] == "Run"].copy()
    if df.empty:
        return pd.DataFrame()

    return _transform(df)


def fetch_latest_run(headers: dict, after: int) -> pd.DataFrame | None:
    """Fetch any runs recorded after the given Unix timestamp.

    Used by the 'Fetch Latest Run' button to check for new activities
    without re-fetching the full 90-day history from the cache.

    Args:
        headers: Auth headers from auth.get_auth_headers()
        after:   Unix timestamp — only activities after this time are returned

    Returns:
        Transformed DataFrame of new runs, or None if none were found.

    Raises:
        requests.HTTPError: on API error
    """
    resp = requests.get(
        f"{BASE_URL}/athlete/activities",
        headers=headers,
        params={"per_page": 10, "page": 1, "after": after},
        timeout=15,
    )
    resp.raise_for_status()
    activities = resp.json()

    runs = [a for a in activities if a.get("sport_type") == "Run"]
    if not runs:
        return None

    return _transform(pd.DataFrame(runs))


def fetch_athlete_stats(headers: dict) -> dict:
    """Fetch aggregate athlete stats from Strava.

    Calls GET /athlete to get the athlete ID, then GET /athletes/{id}/stats.
    Note: Strava's public API does not expose historical VO2max data; this
    endpoint returns aggregate run/ride/swim totals only.

    Args:
        headers: Auth headers from auth.get_auth_headers()

    Returns:
        Raw stats JSON dict, or {} on any error.
    """
    try:
        athlete_resp = requests.get(f"{BASE_URL}/athlete", headers=headers, timeout=10)
        athlete_resp.raise_for_status()
        athlete_id = athlete_resp.json()["id"]

        stats_resp = requests.get(
            f"{BASE_URL}/athletes/{athlete_id}/stats", headers=headers, timeout=10
        )
        stats_resp.raise_for_status()
        return stats_resp.json()
    except Exception:
        return {}


def _transform(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all unit conversions and derived columns to raw Strava activity data.

    Args:
        df: Raw DataFrame from Strava API, already filtered to Runs

    Returns:
        Clean DataFrame with only the columns needed downstream
    """
    df = df.copy()
    df["start_date_local"] = pd.to_datetime(df["start_date_local"])

    # Distance: meters → miles
    df["distance_mi"] = df["distance"] / METERS_PER_MILE

    # Pace: average_speed (m/s) → seconds per mile → display string
    df["pace_sec_per_mi"] = df["average_speed"].apply(
        lambda s: (1.0 / (s * 0.000621371)) if (s and s > 0) else None
    )
    df["pace_min_float"] = df["pace_sec_per_mi"] / 60.0
    df["pace_display"] = df["pace_sec_per_mi"].apply(_format_pace)

    # Duration: seconds → HH:MM:SS
    df["moving_time_display"] = df["moving_time"].apply(_format_duration)

    # Elevation: meters → feet
    df["elevation_gain_ft"] = df["total_elevation_gain"] * FEET_PER_METER

    # Heart rate: optional — NaN if not present
    if "average_heartrate" not in df.columns:
        df["average_heartrate"] = float("nan")

    # Week grouping for bar chart
    df["week_label"] = df["start_date_local"].dt.to_period("W").astype(str)
    df["week_start"] = df["start_date_local"].dt.to_period("W").apply(
        lambda p: p.start_time
    )

    keep = [
        "id", "name", "start_date_local", "distance_mi", "pace_sec_per_mi",
        "pace_min_float", "pace_display", "moving_time", "moving_time_display",
        "elevation_gain_ft", "average_heartrate", "week_label", "week_start",
    ]
    return df[[c for c in keep if c in df.columns]].reset_index(drop=True)


def _format_pace(sec_per_mile) -> str:
    """Convert seconds-per-mile float to 'MM:SS /mi' display string."""
    if sec_per_mile is None or pd.isna(sec_per_mile):
        return "--"
    total = int(round(sec_per_mile))
    return f"{total // 60}:{total % 60:02d} /mi"


def _format_duration(seconds) -> str:
    """Convert total seconds to 'HH:MM:SS' display string."""
    if seconds is None or pd.isna(seconds):
        return "--"
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h}:{m:02d}:{s:02d}"


def apply_filters(
    df: pd.DataFrame,
    start_date: datetime.date,
    end_date: datetime.date,
    min_distance_mi: float,
    name_search: str,
) -> pd.DataFrame:
    """Apply sidebar filters to the full runs DataFrame.

    Args:
        df:               Full transformed DataFrame from fetch_runs()
        start_date:       Earliest date (inclusive)
        end_date:         Latest date (inclusive)
        min_distance_mi:  Minimum distance in miles
        name_search:      Partial activity name string (case-insensitive)

    Returns:
        Filtered DataFrame (may be empty)
    """
    mask = (
        (df["start_date_local"].dt.date >= start_date)
        & (df["start_date_local"].dt.date <= end_date)
        & (df["distance_mi"] >= min_distance_mi)
    )
    filtered = df[mask].copy()
    if name_search.strip():
        filtered = filtered[
            filtered["name"].str.contains(name_search.strip(), case=False, na=False)
        ]
    return filtered


def compute_training_load(
    df: pd.DataFrame,
    rest_hr: int = 50,
    max_hr: int = 190,
) -> pd.DataFrame:
    """Compute TRIMP, CTL (42-day EWM), ATL (7-day EWM), and TSB.

    TRIMP per run:
        With HR:    duration_min * hr_ratio * exp(1.92 * hr_ratio)
                    where hr_ratio = clip((avg_hr - rest_hr) / (max_hr - rest_hr), 0.1, 1.0)
        Without HR: duration_min * clip(600 / pace_sec_per_mi, 0.5, 2.0)
                    (effort factor relative to 10:00/mi easy pace baseline)

    Uses raw_df (unfiltered) — EWM is path-dependent; filtering corrupts CTL/ATL.

    Args:
        df:       Unfiltered transformed DataFrame
        rest_hr:  Resting heart rate (default 50, override via ATHLETE_REST_HR env var)
        max_hr:   Max heart rate (default 190, override via ATHLETE_MAX_HR env var)

    Returns:
        DataFrame with columns: date, daily_trimp, ctl, atl, tsb
    """
    EASY_PACE_THRESHOLD = 600.0  # 10:00/mi in sec/mi

    df = df.copy()
    df["duration_min"] = df["moving_time"] / 60.0
    df["date"] = df["start_date_local"].dt.date

    def _trimp_row(row):
        duration = row["duration_min"]
        if pd.notna(row["average_heartrate"]) and row["average_heartrate"] > 0:
            hr_ratio = (row["average_heartrate"] - rest_hr) / (max_hr - rest_hr)
            hr_ratio = float(np.clip(hr_ratio, 0.1, 1.0))
            return duration * hr_ratio * np.exp(1.92 * hr_ratio)
        else:
            if pd.notna(row["pace_sec_per_mi"]) and row["pace_sec_per_mi"] > 0:
                effort = float(np.clip(EASY_PACE_THRESHOLD / row["pace_sec_per_mi"], 0.5, 2.0))
            else:
                effort = 1.0
            return duration * effort

    df["trimp"] = df.apply(_trimp_row, axis=1)

    daily = df.groupby("date")["trimp"].sum().reset_index()
    daily.columns = ["date", "daily_trimp"]
    daily["date"] = pd.to_datetime(daily["date"])

    min_date = daily["date"].min()
    max_date = pd.Timestamp.today().normalize()
    full_range = pd.date_range(start=min_date, end=max_date, freq="D")
    daily = daily.set_index("date").reindex(full_range, fill_value=0.0)
    daily.index.name = "date"
    daily = daily.reset_index()

    # adjust=False uses recursive formula: y_t = alpha*x_t + (1-alpha)*y_{t-1}
    # This matches the standard CTL/ATL physiological model.
    daily["ctl"] = daily["daily_trimp"].ewm(span=42, adjust=False).mean()
    daily["atl"] = daily["daily_trimp"].ewm(span=7, adjust=False).mean()
    daily["tsb"] = daily["ctl"] - daily["atl"]

    return daily
