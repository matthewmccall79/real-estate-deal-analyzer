import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), "realestate.db")


def column_exists(cur, table, column):
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def ensure_columns():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # --- property_facts additions (store basics we can display quickly) ---
    # Only add if missing.
    pf_additions = {
        "sqft": "REAL",
        "address": "TEXT"
    }

    for col, coltype in pf_additions.items():
        if not column_exists(cur, "property_facts", col):
            cur.execute(f"ALTER TABLE property_facts ADD COLUMN {col} {coltype}")

    # --- deal_inputs additions (monthly fixed costs + metadata) ---
    di_additions = {
        "monthly_taxes": "REAL",
        "monthly_insurance": "REAL",
        "monthly_hoa": "REAL",
        "monthly_maintenance": "REAL",
        "label": "TEXT",
        "notes": "TEXT"
    }

    for col, coltype in di_additions.items():
        if not column_exists(cur, "deal_inputs", col):
            cur.execute(f"ALTER TABLE deal_inputs ADD COLUMN {col} {coltype}")

    conn.commit()
    conn.close()
    print("DB schema ensured (columns added if missing).")


if __name__ == "__main__":
    ensure_columns()
