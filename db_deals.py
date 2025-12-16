import sqlite3

conn = sqlite3.connect("realestate.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS deal_inputs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  property_fact_id INTEGER NOT NULL,
  purchase_price INTEGER NOT NULL,
  estimated_rent INTEGER,
  notes TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(property_fact_id) REFERENCES property_facts(id)
);
""")

conn.commit()
conn.close()
print("deal_inputs table ready.")
