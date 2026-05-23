# Strava Running Dashboard

A Streamlit dashboard that visualizes your running metrics from the Strava API, including weekly mileage, pace trends, distance distribution, and training load science (TRIMP, CTL, ATL, TSB).

---

## Prerequisites

- Python 3.10+
- A Strava account with at least one logged run
- pip

---

## Installation

```bash
pip install -r requirements.txt
```

---

## One-Time Strava Setup

### 1. Register a Strava API App

1. Go to https://www.strava.com/settings/api
2. Create an app (name and website can be anything)
3. Set **Authorization Callback Domain** to `localhost`
4. Copy your **Client ID** and **Client Secret**

### 2. Get Your Refresh Token

Run this in a Python shell or script (substitute your values):

**Step A** — Open this URL in your browser:
```
https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=http://localhost&approval_prompt=force&scope=activity:read_all
```

**Step B** — Approve access. You'll be redirected to a URL like:
```
http://localhost/?state=&code=XXXXXXXXXXXXXXXX&scope=...
```
Copy the value after `code=`.

**Step C** — Exchange the code for tokens:
```python
import requests
tokens = requests.post("https://www.strava.com/api/v3/oauth/token", data={
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "code": "CODE_FROM_URL",
    "grant_type": "authorization_code",
}).json()
print(tokens["refresh_token"])
```

Copy the printed refresh token.

---

## Configure Credentials

```bash
cp .env.example .env
```

Edit `.env`:
```
STRAVA_CLIENT_ID=123456
STRAVA_CLIENT_SECRET=abc123def456
STRAVA_REFRESH_TOKEN=your_long_refresh_token_here
```

Optionally set your heart rate values for more accurate TRIMP:
```
ATHLETE_REST_HR=50
ATHLETE_MAX_HR=190
```

---

## Run the App

```bash
streamlit run app.py
```

The app opens at http://localhost:8501.

---

## Dashboard Features

| Section | Description |
|---|---|
| KPI row | Total runs, miles, avg pace, longest run, elevation |
| Weekly Mileage | Bar chart colored by volume |
| Pace Over Time | Scatter + 4-run rolling average, MM:SS y-axis |
| Distance Distribution | Histogram in 0.5-mile bins |
| Run Log | Sortable table with all metrics |
| Training Load | CTL / ATL / TSB chart + current values |

### Sidebar Controls
- **Date range** — filter all charts and the run log
- **Min distance** — exclude short runs (warm-ups, cooldowns)
- **Activity name search** — filter by partial name
- **Fetch Latest Run** — pulls any runs logged since your last sync without re-fetching the full 90-day history
- **Full Refresh** — clears the session cache and re-fetches everything from Strava

---

## Training Load Science

**TRIMP** (Training Impulse) — effort score per run:
- With heart rate: `duration × hr_ratio × e^(1.92 × hr_ratio)` (Banister model)
- Without HR: pace-based proxy using effort relative to an easy 10:00/mi baseline

**CTL** (Chronic Training Load) — 42-day EWM of daily TRIMP → represents fitness

**ATL** (Acute Training Load) — 7-day EWM of daily TRIMP → represents fatigue

**TSB** (Training Stress Balance) = CTL − ATL → represents form/freshness:
- Positive (5–25): fresh, race-ready
- Near zero: balanced
- Deeply negative: overcooked, injury risk

> Note: The app fetches 90 days of history. For fully accurate CTL, ideally 6+ months of data is needed. The 90-day window gives a good approximation after the first few weeks.
