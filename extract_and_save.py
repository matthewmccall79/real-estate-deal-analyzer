import os
import json
import sqlite3
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

API_KEY = os.getenv("ATTOM_API_KEY")
if not API_KEY:
    raise RuntimeError("ATTOM_API_KEY not found.")

BASE = "https://api.gateway.attomdata.com/propertyapi/v1.0.0"

def fetch_property(address: str) -> dict:
    # Expect: "123 Main St, City, ST" (zip ok too)
    parts = [p.strip() for p in address.split(",", 1)]
    if len(parts) != 2:
        raise ValueError('Use a full address like "123 Main St, City, ST"')

    address1, address2 = parts[0], parts[1]

    url = f"{BASE}/property/detail"
    headers = {"accept": "application/json", "apikey": API_KEY}
    params = {"address1": address1, "address2": address2}

    r = requests.get(url, headers=headers, params=params, timeout=30)
    print("Status:", r.status_code)
    r.raise_for_status()
    return r.json()

def safe_get(d: dict, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

def extract_fields(payload: dict) -> dict:
    props = payload.get("property")
    if isinstance(props, list) and props:
        p = props[0]
    elif isinstance(props, dict):
        p = props
    else:
        p = {}

    # helper
    def sg(*keys, default=None):
        return safe_get(p, *keys, default=default)

    # Beds / baths are commonly in building.rooms
    beds = sg("building", "rooms", "beds")
    baths = sg("building", "rooms", "bathstotal") or sg("building", "rooms", "bathstotalcalc")

    # Sqft: in your keys, you have BOTH 'building' and 'area'
    # Try building.size first, then area (ATTOM often uses area->sqft)
    sqft = (
        sg("building", "size", "livingsize")
        or sg("building", "size", "bldgsize")
        or sg("area", "sqft")
        or sg("area", "sumsqft")
        or sg("area", "bldgsize")
        or sg("area", "livingsize")
    )

    year_built = sg("summary", "yearbuilt") or sg("vintage", "yearbuilt")

    attom_id = safe_get(p, "identifier", "attomId")

    return {
        "attom_id": attom_id,
        "beds": beds,
        "baths": baths,
        "sqft": sqft,
        "year_built": year_built,
        # These remain None until we pull an endpoint that includes sale/assessment
        "last_sale_price": None,
        "last_sale_date": None,
    }


def insert_property_fact(address: str, fetched_at: str, fields: dict, payload: dict):
    conn = sqlite3.connect("realestate.db")
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO property_facts (
          address, fetched_at, attom_id, beds, baths, sqft, year_built,
          last_sale_price, last_sale_date, json_raw
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            address,
            fetched_at,
            fields["attom_id"],
            fields["beds"],
            fields["baths"],
            fields["sqft"],
            fields["year_built"],
            fields["last_sale_price"],
            fields["last_sale_date"],
            json.dumps(payload),
        )
    )
    conn.commit()
    conn.close()

if __name__ == "__main__":
    addresses = [
        "1 Garden State Plaza Pkwy, Paramus, NJ",
        "1600 Pennsylvania Ave NW, Washington, DC",
        "350 5th Ave, New York, NY",
    ]

    for address in addresses:
        payload = fetch_property(address)
        fields = extract_fields(payload)
        print("Extracted fields:", fields)
        insert_property_fact(address, datetime.utcnow().isoformat(), fields, payload)
        print("Saved:", address)
