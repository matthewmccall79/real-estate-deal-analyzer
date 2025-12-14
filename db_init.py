import sqlite3

conn = sqlite3.connect("realestate.db")
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS properties (id INTEGER PRIMARY KEY AUTOINCREMENT, address TEXT NOT NULL, fetched_at TEXT NOT NULL, json_raw TEXT NOT NULL);""")

conn.commit()
conn.close()
print("DB ready: realestate.db")