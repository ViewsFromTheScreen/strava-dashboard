"""
auth.py
Handles Strava OAuth 2.0 token refresh. Loads credentials from .env and
returns a fresh access token using the refresh_token grant type.
"""

import os
import requests
from dotenv import load_dotenv

STRAVA_TOKEN_URL = "https://www.strava.com/api/v3/oauth/token"


def load_credentials() -> dict:
    """Load Strava API credentials from .env file.

    Returns:
        dict with client_id, client_secret, refresh_token

    Raises:
        EnvironmentError: if any required variable is missing
    """
    load_dotenv()
    required = ["STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {missing}. "
            "Copy .env.example to .env and fill in your Strava credentials."
        )
    return {
        "client_id": os.environ["STRAVA_CLIENT_ID"],
        "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
        "refresh_token": os.environ["STRAVA_REFRESH_TOKEN"],
    }


def get_access_token() -> str:
    """Exchange the stored refresh token for a fresh Strava access token.

    Access tokens expire every 6 hours; this is called once per Streamlit session
    and the result stored in st.session_state.

    Returns:
        str: Valid Bearer access token

    Raises:
        requests.HTTPError: on non-2xx response from Strava
        EnvironmentError: if credentials are not configured
    """
    creds = load_credentials()
    response = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "refresh_token": creds["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def get_auth_headers(access_token: str) -> dict:
    """Build the Authorization header dict for Strava API requests."""
    return {"Authorization": f"Bearer {access_token}"}
