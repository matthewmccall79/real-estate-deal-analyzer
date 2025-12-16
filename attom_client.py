import os
import requests


ATTOM_BASE_URL = "https://api.gateway.attomdata.com/propertyapi/v1.0.0"


def get_attom_headers():
    """
    Reads ATTOM API key from environment variables.
    """
    api_key = os.getenv("ATTOM_API_KEY")
    if not api_key:
        raise RuntimeError("ATTOM_API_KEY not found in environment variables")
    return {
        "Accept": "application/json",
        "apikey": api_key,
    }


def lookup_property_by_address(address):
    """
    Look up property facts using a full address string.
    Returns parsed JSON or None if not found.
    """
    url = f"{ATTOM_BASE_URL}/property/basicprofile"
    params = {
        "address": address
    }

    response = requests.get(
        url,
        headers=get_attom_headers(),
        params=params,
        timeout=10,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"ATTOM API error {response.status_code}: {response.text}"
        )

    data = response.json()

    if not data or "property" not in data or not data["property"]:
        return None

    return data["property"][0]
