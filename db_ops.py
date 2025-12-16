import sqlite3
import json
import os
from datetime import datetime

DB = os.path.join(os.path.dirname(__file__), "realestate.db")


def _connect():
    return sqlite3.connect(DB)


def get_latest_property_fact_id(conn):
    cur = conn.cursor()
    row = cur.execute("SELECT id FROM property_facts ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else None


def get_latest_deal(conn):
    cur = conn.cursor()
    row = cur.execute("""
        SELECT
          di.id,
          di.property_fact_id,
          di.purchase_price,
          di.estimated_rent,
          COALESCE(di.monthly_taxes, 0),
          COALESCE(di.monthly_insurance, 0),
          COALESCE(di.monthly_hoa, 0),
          COALESCE(di.monthly_maintenance, 0),
          COALESCE(di.label, ''),
          COALESCE(di.notes, '')
        FROM deal_inputs di
        ORDER BY di.id DESC
        LIMIT 1
    """).fetchone()
    return row


def upsert_property_fact(conn, json_raw: str, address: str = None, sqft: float = None) -> int:
    """
    Inserts a new property_facts row (keeps history).
    Returns the inserted property_facts.id.
    """
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO property_facts (json_raw, address, sqft)
        VALUES (?, ?, ?)
    """, (json_raw, address, sqft))
    conn.commit()
    return cur.lastrowid


def insert_deal_input(
    conn,
    property_fact_id: int,
    purchase_price: float,
    estimated_rent: float,
    monthly_taxes: float = 0.0,
    monthly_insurance: float = 0.0,
    monthly_hoa: float = 0.0,
    monthly_maintenance: float = 0.0,
    label: str = "",
    notes: str = ""
) -> int:
    """
    Inserts a deal_inputs row linked to a property_facts row.
    Returns deal_inputs.id
    """
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO deal_inputs
        (property_fact_id, purchase_price, estimated_rent,
         monthly_taxes, monthly_insurance, monthly_hoa, monthly_maintenance,
         label, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        property_fact_id, purchase_price, estimated_rent,
        monthly_taxes, monthly_insurance, monthly_hoa, monthly_maintenance,
        label, notes
    ))
    conn.commit()
    return cur.lastrowid


def list_saved_deals(limit: int = 25):
    """
    Returns list of dict rows: newest first.
    """
    conn = _connect()
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT
          di.id AS deal_id,
          COALESCE(di.label, '') AS label,
          COALESCE(pf.address, '') AS address,
          COALESCE(pf.sqft, NULL) AS sqft,
          di.purchase_price,
          di.estimated_rent,
          COALESCE(di.monthly_taxes, 0) AS monthly_taxes,
          COALESCE(di.monthly_insurance, 0) AS monthly_insurance,
          COALESCE(di.monthly_hoa, 0) AS monthly_hoa,
          COALESCE(di.monthly_maintenance, 0) AS monthly_maintenance,
          COALESCE(di.notes, '') AS notes
        FROM deal_inputs di
        JOIN property_facts pf ON pf.id = di.property_fact_id
        ORDER BY di.id DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    cols = [
        "deal_id", "label", "address", "sqft", "purchase_price", "estimated_rent",
        "monthly_taxes", "monthly_insurance", "monthly_hoa", "monthly_maintenance", "notes"
    ]
    return [dict(zip(cols, r)) for r in rows]


def get_deal_by_id(deal_id: int):
    conn = _connect()
    cur = conn.cursor()
    row = cur.execute("""
        SELECT
          di.id AS deal_id,
          di.property_fact_id,
          COALESCE(di.label, '') AS label,
          COALESCE(pf.address, '') AS address,
          COALESCE(pf.sqft, NULL) AS sqft,
          di.purchase_price,
          di.estimated_rent,
          COALESCE(di.monthly_taxes, 0) AS monthly_taxes,
          COALESCE(di.monthly_insurance, 0) AS monthly_insurance,
          COALESCE(di.monthly_hoa, 0) AS monthly_hoa,
          COALESCE(di.monthly_maintenance, 0) AS monthly_maintenance,
          COALESCE(di.notes, '') AS notes
        FROM deal_inputs di
        JOIN property_facts pf ON pf.id = di.property_fact_id
        WHERE di.id = ?
    """, (deal_id,)).fetchone()
    conn.close()

    if not row:
        return None

    cols = [
        "deal_id", "property_fact_id", "label", "address", "sqft",
        "purchase_price", "estimated_rent",
        "monthly_taxes", "monthly_insurance", "monthly_hoa", "monthly_maintenance",
        "notes"
    ]
    return dict(zip(cols, row))


# --- quick “smoke test” runner (optional) ---
if __name__ == "__main__":
    conn = _connect()
    latest_pf = get_latest_property_fact_id(conn)
    latest_deal = get_latest_deal(conn)
    conn.close()

    print("Latest property_fact_id:", latest_pf)
    print("Latest deal row:", latest_deal)
