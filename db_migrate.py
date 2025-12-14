import sqlite3

conn = sqlite3.connect("realestate.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS property_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  address TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  attom_id TEXT,
  beds INTEGER,
  baths REAL,
  sqft INTEGER,
  year_built INTEGER,
  last_sale_price INTEGER,
  last_sale_date TEXT,
  json_raw TEXT NOT NULL
);
""")

conn.commit()
conn.close()
print("Migration complete: property_facts table is ready.")
