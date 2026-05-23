# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
streamlit run app.py
```

Opens at http://localhost:8501. Requires a valid `.env` file (copy from `.env.example`).

## Module Architecture

Four-module separation of concerns:

- **`auth.py`** — Loads `.env` credentials via `python-dotenv` and exchanges the stored `refresh_token` for a fresh Strava `access_token` on each session start. Token refresh is intentionally not cached at the module level; caching happens in `st.session_state` in `app.py`.

- **`data.py`** — All Strava API calls, unit conversions, and pandas transformations. Public surface: `fetch_runs()`, `fetch_latest_run()`, `apply_filters()`, `compute_training_load()`. Private helpers (`_transform`, `_format_pace`, `_format_duration`) are used by `app.py` directly (e.g. `data._format_pace()`).

- **`charts.py`** — Pure Plotly figure builders. Accept DataFrames, return `go.Figure`. No `st.*` calls. The pace chart uses custom tick values/text to render `MM:SS` labels on a decimal-minute y-axis.

- **`app.py`** — Streamlit entry point. Initializes `st.session_state["access_token"]` and `st.session_state["raw_runs"]` once per browser session. Training load (`compute_training_load`) is always called on `raw_df` (the full unfiltered set) — never on `filtered_df` — because EWM is path-dependent.

## Key Data Contracts

All distances, paces, and elevations are converted to imperial in `_transform()` before any other module touches them:

| Field | Source | Stored as |
|---|---|---|
| `distance_mi` | `distance` (m) | miles |
| `pace_sec_per_mi` | `average_speed` (m/s) | seconds/mile (int-safe) |
| `pace_min_float` | derived | decimal minutes (for chart y-axis) |
| `pace_display` | derived | `"MM:SS /mi"` string |
| `elevation_gain_ft` | `total_elevation_gain` (m) | feet |
| `moving_time_display` | `moving_time` (s) | `"HH:MM:SS"` string |

`average_heartrate` is `NaN` when the activity has no HR data. All TRIMP/CTL/ATL/TSB logic handles this with a pace-based proxy.

## Strava API

- Base URL: `https://www.strava.com/api/v3`
- Token endpoint: `POST /oauth/token` with `grant_type=refresh_token`
- Activities: `GET /athlete/activities?per_page=200&page=N&after=<unix_ts>`
- `fetch_latest_run()` uses `after=<latest cached run timestamp>` with `per_page=10` — a lightweight check for new activities without a full re-fetch.

## Environment Variables

Loaded from `.env` by `auth.load_credentials()`. `ATHLETE_REST_HR` and `ATHLETE_MAX_HR` are read directly in `app.py` via `os.environ.get()` with fallback defaults (50 / 190).
