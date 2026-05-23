"""
app.py
Main Streamlit application for the Strava Running Dashboard.
Orchestrates auth, data fetching, filtering, and visualization.
"""

import datetime
import streamlit as st
import pandas as pd

import auth
import coaching
import data
import charts

st.set_page_config(
    page_title="Strava Running Dashboard",
    page_icon="🏃",
    layout="wide",
)

# ── Session state init (fires once per browser session) ────────────────────────

if "access_token" not in st.session_state:
    try:
        st.session_state["access_token"] = auth.get_access_token()
    except EnvironmentError as e:
        st.error(str(e))
        st.stop()
    except Exception as e:
        st.error(f"Strava authentication failed: {e}")
        st.stop()

if "raw_runs" not in st.session_state:
    headers = auth.get_auth_headers(st.session_state["access_token"])
    with st.spinner("Fetching your runs from Strava..."):
        try:
            st.session_state["raw_runs"] = data.fetch_runs(headers)
        except Exception as e:
            st.error(f"Failed to fetch activities: {e}")
            st.stop()

raw_df: pd.DataFrame = st.session_state["raw_runs"]

if raw_df.empty:
    st.warning("No runs found in the last 90 days.")
    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────────────────

st.sidebar.header("Filters")

date_min = raw_df["start_date_local"].dt.date.min()
date_max = raw_df["start_date_local"].dt.date.max()

date_range = st.sidebar.date_input(
    "Date range",
    value=(date_min, date_max),
    min_value=date_min,
    max_value=datetime.date.today(),
)
# date_input returns a tuple when a range is selected, or a single date mid-selection
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date = end_date = date_range[0] if date_range else date_min

min_dist = st.sidebar.slider(
    "Min distance (miles)",
    min_value=0.0,
    max_value=float(int(raw_df["distance_mi"].max()) + 1),
    value=0.0,
    step=0.5,
)

name_search = st.sidebar.text_input("Search activity name", value="")

st.sidebar.markdown("---")

# ── HR Settings ────────────────────────────────────────────────────────────────

st.sidebar.subheader("HR Settings")
rest_hr = st.sidebar.number_input(
    "Resting HR (bpm)", min_value=30, max_value=80, value=49, step=1
)
max_hr = st.sidebar.number_input(
    "Max HR (bpm)", min_value=150, max_value=220, value=191, step=1
)

st.sidebar.markdown("---")

# ── Fetch Latest Run button ────────────────────────────────────────────────────

st.sidebar.subheader("Sync")

if st.sidebar.button("Fetch Latest Run", use_container_width=True, type="primary"):
    latest_ts = int(st.session_state["raw_runs"]["start_date_local"].max().timestamp())
    try:
        headers = auth.get_auth_headers(st.session_state["access_token"])
        with st.spinner("Checking Strava for new runs..."):
            new_runs = data.fetch_latest_run(headers, after=latest_ts)
        if new_runs is not None and not new_runs.empty:
            existing_ids = set(st.session_state["raw_runs"]["id"])
            new_runs = new_runs[~new_runs["id"].isin(existing_ids)]
        if new_runs is not None and not new_runs.empty:
            st.session_state["raw_runs"] = pd.concat(
                [st.session_state["raw_runs"], new_runs], ignore_index=True
            ).sort_values("start_date_local").reset_index(drop=True)
            st.sidebar.success(f"Added {len(new_runs)} new run(s)!")
            raw_df = st.session_state["raw_runs"]
            st.rerun()
        else:
            st.sidebar.info("No new runs found since last sync.")
    except Exception as e:
        st.sidebar.error(f"Sync failed: {e}")

# Full refresh — clears the session cache and re-fetches everything
if st.sidebar.button("Full Refresh (90 days)", use_container_width=True):
    for key in ("raw_runs", "access_token"):
        st.session_state.pop(key, None)
    st.rerun()

# ── Apply filters ──────────────────────────────────────────────────────────────

filtered_df = data.apply_filters(raw_df, start_date, end_date, min_dist, name_search)

if filtered_df.empty:
    st.warning("No runs match the current filters.")
    st.stop()

# ── KPI Row ────────────────────────────────────────────────────────────────────

st.title("Strava Running Dashboard")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Runs", len(filtered_df))
col2.metric("Total Miles", f"{filtered_df['distance_mi'].sum():.1f}")
col3.metric("Avg Pace", data._format_pace(filtered_df["pace_sec_per_mi"].mean()))
col4.metric("Longest Run", f"{filtered_df['distance_mi'].max():.2f} mi")
col5.metric("Elevation Gain", f"{filtered_df['elevation_gain_ft'].sum():,.0f} ft")

# ── Charts ─────────────────────────────────────────────────────────────────────

st.subheader("Weekly Mileage")
st.plotly_chart(charts.weekly_mileage_chart(filtered_df), use_container_width=True)

# ── Run Log Table ──────────────────────────────────────────────────────────────

st.subheader("Run Log")

log_df = filtered_df[[
    "start_date_local", "name", "distance_mi", "pace_display",
    "moving_time_display", "elevation_gain_ft", "average_heartrate",
]].copy()
log_df["start_date_local"] = log_df["start_date_local"].dt.strftime("%Y-%m-%d")
log_df["distance_mi"] = log_df["distance_mi"].round(2)
log_df["elevation_gain_ft"] = log_df["elevation_gain_ft"].round(0)
log_df.columns = [
    "Date", "Name", "Distance (mi)", "Pace", "Moving Time", "Elevation (ft)", "Avg HR"
]

st.dataframe(
    log_df.sort_values("Date", ascending=False),
    use_container_width=True,
    hide_index=True,
)

# ── Training Load ──────────────────────────────────────────────────────────────

st.subheader("Training Load — CTL / ATL / TSB")

with st.expander("What do these mean?"):
    st.markdown(
        "**CTL (Fitness)** — 42-day exponential fitness curve. Higher = more adapted.\n\n"
        "**ATL (Fatigue)** — 7-day fatigue curve. Spikes after hard weeks.\n\n"
        "**TSB (Form)** = CTL − ATL. Positive = fresh/race-ready. Negative = fatigued.\n\n"
        "**TRIMP** — effort score per run. Uses HR when available; pace-based proxy otherwise."
    )

# Training load uses raw_df (unfiltered) — EWM must reflect true training history
load_df = data.compute_training_load(raw_df, rest_hr=rest_hr, max_hr=max_hr)
st.plotly_chart(charts.training_load_chart(load_df), use_container_width=True)

latest = load_df.iloc[-1]
tl1, tl2, tl3 = st.columns(3)
tl1.metric("CTL (Fitness)", f"{latest['ctl']:.1f}")
tl2.metric("ATL (Fatigue)", f"{latest['atl']:.1f}")
tl3.metric("TSB (Form)", f"{latest['tsb']:.1f}")

# ── Coaching Insights ──────────────────────────────────────────────────────────

st.header("🧠 Coaching Insights")

current_tsb = float(load_df["tsb"].iloc[-1])
current_ctl = float(load_df["ctl"].iloc[-1])
current_atl = float(load_df["atl"].iloc[-1])

# ── 1 & 7: Ramp Rate + Monotony/Strain snapshot ───────────────────────────────

ramp = coaching.ramp_rate(load_df)
ms = coaching.monotony_strain(load_df)

ci1, ci2, ci3 = st.columns(3)
ci1.metric("Weekly Load Change (CTL)", f"{ramp['pct_change']:+.1f}%")
ci2.metric("Training Monotony", f"{ms['monotony']:.2f}")
ci3.metric("Weekly Strain Score", f"{ms['strain']:.0f}")

if ramp["status"] == "green":
    st.success(f"**Ramp Rate:** {ramp['message']}")
elif ramp["status"] == "yellow":
    st.warning(f"**Ramp Rate:** {ramp['message']}")
else:
    st.error(f"**Ramp Rate:** {ramp['message']}")

if ms["flag"]:
    st.warning(
        "**Monotony Warning:** Training variation is too low (monotony > 2.0). "
        "Mix up pace, duration, or terrain to reduce overuse injury risk."
    )

# ── 2: Daily Training Recommendation ──────────────────────────────────────────

st.subheader("Today's Training Recommendation")
rec = coaching.daily_recommendation(current_tsb)
getattr(st, rec["color"])(f"**{rec['band']}** — {rec['message']}")

# ── 6: Long Run Fatigue Debt ───────────────────────────────────────────────────

debt = coaching.long_run_fatigue_debt(raw_df, load_df)
if debt:
    st.subheader("Long Run Recovery Estimate")
    st.info(
        f"Most recent long run: **{debt['distance_mi']:.1f} mi** on **{debt['run_date']}** "
        f"(TRIMP: {debt['run_trimp']:.0f}, avg daily load: {debt['avg_daily_load']:.0f}). "
        f"Estimated elevated ATL recovery: **{debt['debt_days']} day(s)**. "
        f"Earliest recommended hard effort: **{debt['earliest_hard']}**."
    )

# ── 3: Race Readiness Simulator ───────────────────────────────────────────────

st.subheader("🏁 Race Readiness Simulator")

sim_c1, sim_c2 = st.columns([1, 1])
with sim_c1:
    race_date = st.date_input(
        "Target race date",
        value=datetime.date.today() + datetime.timedelta(weeks=8),
        min_value=datetime.date.today() + datetime.timedelta(days=1),
    )
with sim_c2:
    target_tsb = st.slider("Target TSB at race start", min_value=5, max_value=30, value=15)

projected_df = coaching.simulate_race_readiness(current_ctl, current_atl, race_date, target_tsb)

if not projected_df.empty:
    final = projected_df.iloc[-1]
    will_hit = final["tsb"] >= target_tsb
    status_msg = (
        f"✅ On track — projected TSB at race: **{final['tsb']:.1f}** "
        f"(target: {target_tsb}). Projected CTL: **{final['ctl']:.1f}**."
        if will_hit else
        f"⚠️ Projected TSB: **{final['tsb']:.1f}** — below target of {target_tsb}. "
        f"Projected CTL: **{final['ctl']:.1f}**. You may need to extend your taper or reduce load sooner."
    )
    if will_hit:
        st.success(status_msg)
    else:
        st.warning(status_msg)
    st.plotly_chart(
        charts.race_readiness_chart(projected_df, race_date, target_tsb),
        use_container_width=True,
    )
else:
    st.info("Select a future race date to simulate projected CTL/ATL/TSB.")

# ── HR Zone Distribution ───────────────────────────────────────────────────────

st.subheader("❤️ Heart Rate Zone Distribution")
zone_df = coaching.hr_zone_distribution(filtered_df, max_hr)
if not zone_df.empty:
    st.plotly_chart(charts.hr_zone_chart(zone_df), use_container_width=True)
    st.caption("Based on average HR per run classified into % of max HR zones.")
else:
    st.info("No runs with HR data in the selected date range.")

# ── 4: VO2max Trend ────────────────────────────────────────────────────────────

st.subheader("📈 VO2max Trend (Estimated)")
vo2_df = coaching.estimate_vo2max_trend(raw_df, rest_hr, max_hr)
if not vo2_df.empty:
    st.plotly_chart(charts.vo2max_trend_chart(vo2_df, reference_vo2=61), use_container_width=True)
    st.caption(
        "Estimated from average pace + HR per run using the ACSM submaximal formula. "
        "Orange dashed line = your Strava VO2max reference (61). "
        "Strava's public API does not expose historical VO2max data directly."
    )
else:
    st.info("No runs with HR data available for VO2max estimation.")

# ── 5: Pace vs HR Efficiency ───────────────────────────────────────────────────

st.subheader("⚡ Pace vs HR Efficiency")
eff_df = coaching.efficiency_score(filtered_df, rest_hr, max_hr)
if not eff_df.empty:
    st.plotly_chart(charts.efficiency_chart(eff_df), use_container_width=True)
    st.caption(
        "Efficiency = pace (min/km) ÷ relative HR effort. "
        "A rising score means the same heart rate effort produces a faster pace — a sign of improving fitness."
    )
else:
    st.info("No runs with HR data in the selected date range.")

# ── Personal Records ───────────────────────────────────────────────────────────

st.subheader("🏆 Personal Records (Last 90 Days)")
prs = coaching.personal_records(raw_df)
pr_df = pd.DataFrame(prs)
st.dataframe(pr_df, use_container_width=True, hide_index=True)
st.caption("Best pace for runs at or above each target distance (±5% GPS tolerance). Based on the last 90 days of data.")
