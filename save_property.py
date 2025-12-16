import os
import json
import sqlite3
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ATTOM_API_KEY")
if not API_KEY:
    raise RuntimeError("ATTOM_API_KEY not found. Check your .env file.")

BASE = "https://api.gateway.attomdata.com/propertyapi/v1.0.0"

def fetch_property(address: str) -> dict:
    url = f"{BASE}/property/basicprofile"
    headers = {"accept": "application/json", "apikey": API_KEY}
    params = {"address": address}

    r = requests.get(url, headers=headers, params=params, timeout=30)
    print("Status:", r.status_code)
    r.raise_for_status()
    return r.json()

def save_property_to_db(address: str, payload: dict) -> None:
    conn = sqlite3.connect("realestate.db")
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO properties (address, fetched_at, json_raw) VALUES (?, ?, ?)",
        (address, datetime.utcnow().isoformat(), json.dumps(payload))
    )

    conn.commit()
    conn.close()

if __name__ == "__main__":
    address = "Paramus, NJ"
    data = fetch_property(address)
    save_property_to_db(address, data)
    print("Saved property to database.")
