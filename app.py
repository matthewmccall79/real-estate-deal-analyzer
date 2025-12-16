import os
import sqlite3
from datetime import datetime

import streamlit as st
import requests


# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Real Estate Deal Analyzer", layout="centered")
DB = os.path.join(os.path.dirname(__file__), "realestate.db")


# =========================
# FINANCE HELPERS
# =========================
def monthly_payment(principal: float, annual_rate: float, years: int) -> float:
    if principal <= 0:
        return 0.0
    r = annual_rate / 12
    n = years * 12
    if r == 0:
        return principal / n
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


def compute_metrics(
    purchase_price: float,
    rent_monthly: float,
    sqft: float | None,
    down_pct: float,
    interest_rate: float,
    term_years: int,
    opex_ratio: float,
    monthly_taxes: float,
    monthly_insurance: float,
    monthly_hoa: float,
    monthly_maintenance: float,
):
    loan_amount = purchase_price * (1 - down_pct)
    mortgage_pmt = monthly_payment(loan_amount, interest_rate, term_years)

    gross_rent_annual = rent_monthly * 12
    noi_annual = gross_rent_annual * (1 - opex_ratio)

    fixed_costs_annual = 12 * (
        monthly_taxes + monthly_insurance + monthly_hoa + monthly_maintenance
    )

    cash_flow_annual = noi_annual - (mortgage_pmt * 12) - fixed_costs_annual
    cash_flow_monthly = cash_flow_annual / 12
    cash_invested = purchase_price * down_pct

    cap_rate = (noi_annual / purchase_price) * 100 if purchase_price else 0.0
    coc_return = (cash_flow_annual / cash_invested) * 100 if cash_invested else 0.0
    price_per_sqft = (purchase_price / sqft) if sqft and sqft > 0 else None

    return {
        "mortgage_pmt": mortgage_pmt,
        "gross_rent_annual": gross_rent_annual,
        "noi_annual": noi_annual,
        "fixed_costs_annual": fixed_costs_annual,
        "cash_flow_monthly": cash_flow_monthly,
        "cash_flow_annual": cash_flow_annual,
        "cap_rate": cap_rate,
        "coc_return": coc_return,
        "cash_invested": cash_invested,
        "price_per_sqft": price_per_sqft,
    }


# =========================
# API HELPERS
# =========================
def get_attom_key():
    try:
        return st.secrets.get("ATTOM_API_KEY", None)
    except Exception:
        return os.getenv("ATTOM_API_KEY")


def nominatim_suggest(query: str, limit: int = 6):
    """
    Autocomplete suggestions via OpenStreetMap Nominatim.
    Returns display_name strings.
    """
    q = (query or "").strip()
    if len(q) < 4:
        return []

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": q,
        "format": "json",
        "addressdetails": 0,
        "limit": str(limit),
    }
    headers = {"User-Agent": "real-estate-deal-analyzer/1.0"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=8)
        r.raise_for_status()
        data = r.json()
        out = []
        for item in data:
            dn = item.get("display_name")
            if dn:
                out.append(dn)
        return out
    except Exception:
        return []


def attom_lookup_by_address(address_one_line: str):
    """
    ATTOM basic profile lookup by a single address string.
    Returns {'address_one_line':..., 'sqft':...} or {'error':...}.
    """
    api_key = get_attom_key()
    if not api_key:
        return {"error": "Missing ATTOM_API_KEY in Streamlit Secrets."}

    url = "https://api.gateway.attomdata.com/propertyapi/v1.0.0/property/basicprofile"
    headers = {"apikey": api_key, "Accept": "application/json"}
    params = {"address": address_one_line}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=12)
        if r.status_code != 200:
            return {"error": f"ATTOM returned {r.status_code}: {r.text[:200]}"}

        data = r.json()

        props = data.get("property")
        p = props[0] if isinstance(props, list) and props else (props if isinstance(props, dict) else None)
        if not p:
            return {"error": "No property found for that address."}

        addr = p.get("address", {}) or {}
        building = p.get("building", {}) or {}
        size = (building.get("size") or {}) if isinstance(building, dict) else {}

        sqft = size.get("livingsize") or size.get("bldgsize") or size.get("grosssize")
        one_line = addr.get("oneLine") or address_one_line

        return {
            "address_one_line": one_line,
            "sqft": float(sqft) if sqft is not None else None,
        }
    except Exception as e:
        return {"error": f"ATTOM lookup failed: {e}"}


# =========================
# DB HELPERS
# =========================
def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)


def create_saved_deals_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            label TEXT,
            notes TEXT,

            address TEXT NOT NULL,
            sqft REAL,

            purchase_price REAL NOT NULL,
            rent_monthly REAL NOT NULL,

            down_pct REAL NOT NULL,
            interest_rate REAL NOT NULL,
            term_years INTEGER NOT NULL,
            opex_ratio REAL NOT NULL,

            monthly_taxes REAL NOT NULL,
            monthly_insurance REAL NOT NULL,
            monthly_hoa REAL NOT NULL,
            monthly_maintenance REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def insert_saved_deal(payload: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO saved_deals (
            created_at, label, notes,
            address, sqft,
            purchase_price, rent_monthly,
            down_pct, interest_rate, term_years, opex_ratio,
            monthly_taxes, monthly_insurance, monthly_hoa, monthly_maintenance
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["created_at"],
            payload.get("label"),
            payload.get("notes"),
            payload["address"],
            payload.get("sqft"),
            payload["purchase_price"],
            payload["rent_monthly"],
            payload["down_pct"],
            payload["interest_rate"],
            payload["term_years"],
            payload["opex_ratio"],
            payload["monthly_taxes"],
            payload["monthly_insurance"],
            payload["monthly_hoa"],
            payload["monthly_maintenance"],
        ),
    )
    conn.commit()
    conn.close()


def load_saved_deals():
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT id, created_at, COALESCE(label,''), address, sqft, purchase_price, rent_monthly
        FROM saved_deals
        ORDER BY id DESC
        """
    ).fetchall()
    conn.close()
    return rows


def get_saved_deal(deal_id: int):
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute(
        """
        SELECT
            id, created_at, label, notes,
            address, sqft,
            purchase_price, rent_monthly,
            down_pct, interest_rate, term_years, opex_ratio,
            monthly_taxes, monthly_insurance, monthly_hoa, monthly_maintenance
        FROM saved_deals
        WHERE id = ?
        """,
        (deal_id,),
    ).fetchone()
    conn.close()
    return row


def delete_saved_deal(deal_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM saved_deals WHERE id = ?", (deal_id,))
    conn.commit()
    conn.close()


def load_latest_deal_from_existing_tables():
    """
    Pulls your latest ingested deal from existing tables:
    deal_inputs JOIN property_facts.
    Used as sensible defaults.
    """
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute(
        """
        SELECT
          pf.address,
          pf.sqft,
          di.purchase_price,
          di.estimated_rent,
          COALESCE(di.monthly_taxes, 0),
          COALESCE(di.monthly_insurance, 0),
          COALESCE(di.monthly_hoa, 0),
          COALESCE(di.monthly_maintenance, 0)
        FROM deal_inputs di
        JOIN property_facts pf ON pf.id = di.property_fact_id
        ORDER BY di.id DESC
        LIMIT 1
        """
    ).fetchone()
    conn.close()
    return row


# =========================
# APP UI
# =========================
st.title("🏠 Real Estate Deal Analyzer")
st.caption("Paste an address → autocomplete → lookup sqft → underwrite → save → compare")

create_saved_deals_table()

tabs = st.tabs(["QuickCheck", "Saved Deals", "Compare Deals"])
tab1, tab2, tab3 = tabs

latest = load_latest_deal_from_existing_tables()
if not latest:
    st.error("No deal data found in your database yet. Run your extract/save pipeline first.")
    st.stop()

db_address, db_sqft, db_price, db_rent, db_tax, db_ins, db_hoa, db_maint = latest
db_sqft = float(db_sqft) if db_sqft is not None else None


# ==========================================================
# TAB 1 — QUICKCHECK + LOOKUP + SAVE
# ==========================================================
with tab1:
    st.subheader("1) Property (Address Search + Lookup)")

    if "lookup_result" not in st.session_state:
        st.session_state["lookup_result"] = {}

    search_q = st.text_input("Search address", value=db_address)
    suggestions = nominatim_suggest(search_q)
    picked = st.selectbox("Suggestions (optional)", ["(use typed address)"] + suggestions)

    lookup_address = search_q if picked == "(use typed address)" else picked

    colL, colR = st.columns([1, 2])
    with colL:
        do_lookup = st.button("🔎 Lookup (auto-fill sqft)")
    with colR:
        st.caption("Uses ATTOM to auto-fill sqft when possible. You can still override manually.")

    if do_lookup:
        res = attom_lookup_by_address(lookup_address)
        st.session_state["lookup_result"] = res
        if res.get("error"):
            st.error(res["error"])
        else:
            st.success("Lookup success — sqft will be pre-filled below.")

    lookup = st.session_state.get("lookup_result", {}) or {}
    display_address = lookup.get("address_one_line") or lookup_address

    sqft_default = lookup.get("sqft")
    if sqft_default is None:
        sqft_default = db_sqft if db_sqft is not None else 0.0

    st.write(f"**Using address:** {display_address}")
    st.write(f"**Sqft default:** {sqft_default if sqft_default else 'Unknown'}")

    st.subheader("2) Underwrite (Adjust Inputs)")

    with st.form("quickcheck_form"):
        col1, col2 = st.columns(2)

        with col1:
            purchase_price = st.number_input("Purchase price ($)", min_value=0.0, value=float(db_price))
            rent_monthly = st.number_input("Estimated rent (monthly $)", min_value=0.0, value=float(db_rent))
            sqft_input = st.number_input("Sqft (optional override)", min_value=0.0, value=float(sqft_default or 0.0))

            down_pct = st.slider("Down payment (%)", 5, 40, 20) / 100
            interest_rate = st.slider("Interest rate (%)", 3.0, 10.0, 7.0) / 100
            term_years = st.selectbox("Loan term (years)", [15, 30], index=1)

        with col2:
            opex_ratio = st.slider("Operating expense ratio (%)", 20, 50, 35) / 100

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                monthly_taxes = st.number_input("Taxes ($/mo)", min_value=0.0, value=float(db_tax))
            with c2:
                monthly_insurance = st.number_input("Insurance ($/mo)", min_value=0.0, value=float(db_ins))
            with c3:
                monthly_hoa = st.number_input("HOA ($/mo)", min_value=0.0, value=float(db_hoa))
            with c4:
                monthly_maintenance = st.number_input("Maintenance ($/mo)", min_value=0.0, value=float(db_maint))

            label = st.text_input("Label (optional)", value="")
            notes = st.text_area("Notes (optional)", value="", height=90)

        run_clicked = st.form_submit_button("Run QuickCheck")
        save_clicked = st.form_submit_button("Run QuickCheck + Save")

    if run_clicked or save_clicked:
        metrics = compute_metrics(
            purchase_price=float(purchase_price),
            rent_monthly=float(rent_monthly),
            sqft=float(sqft_input) if sqft_input and sqft_input > 0 else None,
            down_pct=float(down_pct),
            interest_rate=float(interest_rate),
            term_years=int(term_years),
            opex_ratio=float(opex_ratio),
            monthly_taxes=float(monthly_taxes),
            monthly_insurance=float(monthly_insurance),
            monthly_hoa=float(monthly_hoa),
            monthly_maintenance=float(monthly_maintenance),
        )

        st.subheader("3) Results")
        a, b, c = st.columns(3)
        a.metric("Monthly Cash Flow", f"${metrics['cash_flow_monthly']:,.2f}")
        b.metric("Cash-on-Cash Return", f"{metrics['coc_return']:.2f}%")
        c.metric("Cap Rate", f"{metrics['cap_rate']:.2f}%")

        a2, b2, c2 = st.columns(3)
        a2.metric("Mortgage P&I (Monthly)", f"${metrics['mortgage_pmt']:,.2f}")
        b2.metric("NOI (Annual)", f"${metrics['noi_annual']:,.2f}")
        c2.metric("Price / Sqft", f"${metrics['price_per_sqft']:,.2f}" if metrics["price_per_sqft"] else "—")

        if save_clicked:
            insert_saved_deal(
                {
                    "created_at": datetime.utcnow().isoformat(),
                    "label": (label.strip() or None),
                    "notes": (notes.strip() or None),
                    "address": display_address,
                    "sqft": float(sqft_input) if sqft_input and sqft_input > 0 else None,
                    "purchase_price": float(purchase_price),
                    "rent_monthly": float(rent_monthly),
                    "down_pct": float(down_pct),
                    "interest_rate": float(interest_rate),
                    "term_years": int(term_years),
                    "opex_ratio": float(opex_ratio),
                    "monthly_taxes": float(monthly_taxes),
                    "monthly_insurance": float(monthly_insurance),
                    "monthly_hoa": float(monthly_hoa),
                    "monthly_maintenance": float(monthly_maintenance),
                }
            )
            st.success("✅ Deal saved! Check the Saved Deals tab.")


# ==========================================================
# TAB 2 — SAVED DEALS
# ==========================================================
with tab2:
    st.subheader("Saved Deals")

    rows = load_saved_deals()
    if not rows:
        st.info("No saved deals yet. Use QuickCheck + Save to add one.")
    else:
        options = {}
        for (deal_id, created_at, label, addr, sqft_r, pp, rentm) in rows:
            tag = f"{deal_id} • {label or 'Untitled'} • {addr} • ${pp:,.0f} • ${rentm:,.0f}/mo"
            options[tag] = deal_id

        selected_tag = st.selectbox("Select a saved deal", list(options.keys()))
        selected_id = options[selected_tag]

        deal = get_saved_deal(selected_id)
        (
            _id, created_at, label, notes,
            addr, sqft_r,
            pp, rentm,
            down_pct, ir, term_y, opex_r,
            mtax, mins, mhoa, mmaint
        ) = deal

        st.write(f"**Address:** {addr}")
        st.write(f"**Label:** {label or '—'}")
        st.write(f"**Created:** {created_at}")
        st.write(f"**Notes:** {notes or '—'}")

        metrics = compute_metrics(
            purchase_price=float(pp),
            rent_monthly=float(rentm),
            sqft=float(sqft_r) if sqft_r else None,
            down_pct=float(down_pct),
            interest_rate=float(ir),
            term_years=int(term_y),
            opex_ratio=float(opex_r),
            monthly_taxes=float(mtax),
            monthly_insurance=float(mins),
            monthly_hoa=float(mhoa),
            monthly_maintenance=float(mmaint),
        )

        st.subheader("Deal Metrics")
        a, b, c = st.columns(3)
        a.metric("Monthly Cash Flow", f"${metrics['cash_flow_monthly']:,.2f}")
        b.metric("Cash-on-Cash Return", f"{metrics['coc_return']:.2f}%")
        c.metric("Cap Rate", f"{metrics['cap_rate']:.2f}%")

        if st.button("🗑️ Delete this saved deal"):
            delete_saved_deal(selected_id)
            st.success("Deleted. Refreshing…")
            st.rerun()


# ==========================================================
# TAB 3 — COMPARE DEALS
# ==========================================================
with tab3:
    st.subheader("Compare Deals")

    rows = load_saved_deals()
    if len(rows) < 2:
        st.info("Save at least 2 deals to compare them.")
    else:
        items = []
        id_by_label = {}
        for (deal_id, created_at, label, addr, sqft_r, pp, rentm) in rows:
            text = f"{deal_id} • {label or 'Untitled'} • {addr} • ${pp:,.0f}"
            items.append(text)
            id_by_label[text] = deal_id

        selected = st.multiselect("Pick 2+ deals to compare", items, default=items[:2])

        if len(selected) >= 2:
            compare_rows = []
            for tag in selected:
                deal_id = id_by_label[tag]
                deal = get_saved_deal(deal_id)
                (
                    _id, created_at, label, notes,
                    addr, sqft_r,
                    pp, rentm,
                    down_pct, ir, term_y, opex_r,
                    mtax, mins, mhoa, mmaint
                ) = deal

                metrics = compute_metrics(
                    purchase_price=float(pp),
                    rent_monthly=float(rentm),
                    sqft=float(sqft_r) if sqft_r else None,
                    down_pct=float(down_pct),
                    interest_rate=float(ir),
                    term_years=int(term_y),
                    opex_ratio=float(opex_r),
                    monthly_taxes=float(mtax),
                    monthly_insurance=float(mins),
                    monthly_hoa=float(mhoa),
                    monthly_maintenance=float(mmaint),
                )

                compare_rows.append(
                    {
                        "Deal": f"{deal_id} • {label or 'Untitled'}",
                        "Address": addr,
                        "Purchase Price": float(pp),
                        "Rent (Monthly)": float(rentm),
                        "Monthly Cash Flow": float(metrics["cash_flow_monthly"]),
                        "Cap Rate %": float(metrics["cap_rate"]),
                        "CoC %": float(metrics["coc_return"]),
                    }
                )

            st.dataframe(compare_rows, use_container_width=True)

            st.subheader("Monthly cash flow comparison")
            st.bar_chart({row["Deal"]: row["Monthly Cash Flow"] for row in compare_rows})
