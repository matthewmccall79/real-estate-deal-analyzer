import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ATTOM_API_KEY")
if not API_KEY: 
    raise RuntimeError("ATTOM_API_KEY not found. Check your .env file.")

BASE = "https://api.gateway.attomdata.com/propertyapi/v1.0.0"

def basic_profile(one_line_address: str) -> dict:
    url = f"{BASE}/property/basicprofile"
    
    headers = {"accept": "application/json", "apikey": API_KEY}

    params = {"address": one_line_address}

    r = requests.get(url, headers=headers, params=params, timeout=30)
    
    print("Status:", r.status_code)
    
    if r.status_code != 200:
        print("Response text (first 500 chars):", r.text[:500])
    
    r.raise_for_status()
    return r.json()

if __name__ == "__main__":
   address = "4529 Winona Court, Denver, CO"
   data = basic_profile(address)

   print("Top-level keys:", list(data.keys()))
   prop = data.get("property")
   if isinstance(prop, list) and prop:
       print("First property keys:", list(prop[0].keys())[:25])
   else:
       print("property field type:", type(prop).__name__) 