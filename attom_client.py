import os
import requests
import streamlit as st

ATTOM_BASE_URL = "https://api.gateway.attomdata.com/propertyapi/v1.0.0"


def _get_attom_api_key() -> str:
    """
    Streamlit Cloud: use st.secrets
    Local dev: allow environment variable fallback
    """
    key = None

    # Streamlit secrets (works on Streamlit Cloud)
    try:
        key = st.secrets.get("ATTOM_API_KEY")
    except Exception:
        key = None

    # Fallback to env var (works locally)
    if not key:
        key = os.getenv("ATTOM_API_KEY")

    if not key:
        raise RuntimeError(
            "ATTOM_API_KEY not found. Add it in Streamlit Cloud: Manage app → Settings → Secrets "
            "as: ATTOM_API_KEY = \"your_key\" (or set it as an environment variable locally)."
        )

    return key


def get_attom_headers() -> dict:
    return {
        "Accept": "application/json",
        "apikey": _get_attom_api_key(),
    }


def lookup_property_by_address(address: str) -> dict:
    """
    Look up property facts using a full address string.
    Returns parsed JSON dict on success.
    Raises RuntimeError with a helpful message on failure.
    """
    address = (address or "").strip()
    if not address:
        raise RuntimeError("Address is blank.")

    url = f"{ATTOM_BASE_URL}/property/basicprofile"
    params = {"address": address}

    try:
        resp = requests.get(url, headers=get_attom_headers(), params=params, timeout=20)
    except requests.RequestException as e:
        raise RuntimeError(f"Network error calling ATTOM: {e}")

    # Helpful errors
    if resp.status_code in (401, 403):
        raise RuntimeError(
            f"ATTOM returned {resp.status_code} (auth/permission). "
            "Double-check your API key in Streamlit Secrets."
        )
    if resp.status_code == 429:
        raise RuntimeError("ATTOM rate limit hit (429). Try again in a minute.")
    if resp.status_code >= 400:
        raise RuntimeError(f"ATTOM returned {resp.status_code}: {resp.text[:200]}")

    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError("ATTOM response was not valid JSON.")

    return data
