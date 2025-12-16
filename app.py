import sqlite3
from datetime import datetime
import math

import pandas as pd
import streamlit as st


# ----------------------------
# Config
# ----------------------------
DB = "realestate.db"

st.set_page_config(page_title="Real Estate Deal Analyzer", page_icon="🏠", layout="wide")


# ----------------------------
# Math helpers
# ----------------------------
def monthly_payment(principal: float, annual_rate_pct: float, years: int) -> float:
    """Monthly P&I payment for a standard amortizing loan."""
    if principal <= 0 or years <= 0:
        return 0.0

    r = (annual_rate_pct / 100.0) / 12.0
    n = years * 12

    if r == 0:
        return principal / n

    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


# ----------------------------
# DB helpers
# ----------------------------
def get_conn():
    return sqlite3.connect(DB)


def ensure_tables():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
      CREATE TABLE IF NOT EXISTS quickchecks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        address TEXT,
        purchase_price REAL,
        estimated_rent_monthly REAL,
        sqft REAL,
        down_payment_pct REAL,
        interest_rate REAL,
        term_years INTEGER,
        opex_ratio REAL,
        monthly_taxes REAL,
        monthly_insurance REAL,
        monthly_hoa REAL,
        monthly_maintenance REAL,
        mortgage_pi_monthly REAL,
        noi_annual REAL,
        cap_rate_pct REAL,
        cash_flow_monthly REAL,
        cash_flow_annual REAL,
        cash_on_cash_pct REAL,
        status TEXT,
        label TEXT,
        notes TEXT
      );
    """)

    # additive migrations (safe if you already had the table)
    cols = [r[1] for r in cur.execute("PRAGMA table_info(quickchecks)").fetchall()]
    add_cols = [
        ("label", "TEXT"),
        ("notes", "TEXT"),
        ("monthly_taxes", "REAL"),
        ("monthly_insurance", "REAL"),
        ("monthly_hoa", "REAL"),
        ("monthly_maintenance", "REAL"),
        ("mortgage_pi_monthly", "REAL"),
        ("noi_annual", "REAL"),
        ("cap_rate_pct", "REAL"),
        ("cash_flow_monthly", "REAL"),
        ("cash_flow_annual", "REAL"),
        ("cash_on_cash_pct", "REAL"),
        ("status", "TEXT"),
    ]
    for col, coltype in add_cols:
        if col not in cols:
            cur.execute(f"ALTER TABLE quickchecks ADD COLUMN {col} {coltype}")

    conn.commit()
    conn.close()


def insert_quickcheck(row: dict):
    conn = get_conn()
    cur = conn.cursor()

    fields = [
        "created_at", "address", "purchase_price", "estimated_rent_monthly", "sqft",
        "down_payment_pct", "interest_rate", "term_years", "opex_ratio",
        "monthly_taxes", "monthly_insurance", "monthly_hoa", "monthly_maintenance",
        "mortgage_pi_monthly", "noi_annual", "cap_rate_pct",
        "cash_flow_monthly", "cash_flow_annual", "cash_on_cash_pct",
        "status", "label", "notes"
    ]
    values = [row.get(f) for f in fields]

    qmarks = ",".join(["?"] * len(fields))
    cur.execute(f"INSERT INTO quickchecks ({','.join(fields)}) VALUES ({qmarks})", values)

    conn.commit()
    conn.close()


def fetch_quickchecks_df() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT
          id, created_at, address, label,
          purchase_price, estimated_rent_monthly, sqft,
          down_payment_pct, interest_rate, term_years, opex_ratio,
          monthly_taxes, monthly_insurance, monthly_hoa, monthly_maintenance,
          mortgage_pi_monthly, noi_annual, cap_rate_pct,
          cash_flow_monthly, cash_flow_annual, cash_on_cash_pct,
          status, notes
        FROM quickchecks
        ORDER BY id DESC
    """, conn)
    conn.close()
    return df


def fetch_one(qid: int) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("""
        SELECT
          id, created_at, address, label,
          purchase_price, estimated_rent_monthly, sqft,
          down_payment_pct, interest_rate, term_years, opex_ratio,
          monthly_taxes, monthly_insurance, monthly_hoa, monthly_maintenance,
          mortgage_pi_monthly, noi_annual, cap_rate_pct,
          cash_flow_monthly, cash_flow_annual, cash_on_cash_pct,
          status, notes
        FROM quickchecks
        WHERE id = ?
    """, (qid,)).fetchone()
    conn.close()

    if not row:
        return None

    keys = [
        "id", "created_at", "address", "label",
        "purchase_price", "estimated_rent_monthly", "sqft",
        "down_payment_pct", "interest_rate", "term_years", "opex_ratio",
        "monthly_taxes", "monthly_insurance", "monthly_hoa", "monthly_maintenance",
        "mortgage_pi_monthly", "noi_annual", "cap_rate_pct",
        "cash_flow_monthly", "cash_flow_annual", "cash_on_cash_pct",
        "status", "notes"
    ]
    return dict(zip(keys, row))


def delete_quickcheck(qid: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM quickchecks WHERE id = ?", (qid,))
    conn.commit()
    conn.close()


# ----------------------------
# Analysis
# ----------------------------
def analyze_deal(
    purchase_price: float,
    rent_monthly: float,
    sqft: float,
    down_payment_pct: float,
    interest_rate: float,
    term_years: int,
    opex_ratio: float,
    monthly_taxes: float,
    monthly_insurance: float,
    monthly_hoa: float,
    monthly_maintenance: float,
):
    purchase_price = max(0.0, purchase_price)
    rent_monthly = max(0.0, rent_monthly)
    sqft = max(0.0, sqft)
    down_payment_pct = max(0.0, min(100.0, down_payment_pct))
    term_years = max(1, int(term_years))
    opex_ratio = max(0.0, min(0.95, opex_ratio))

    down_payment = purchase_price * (down_payment_pct / 100.0)
    loan_amount = max(0.0, purchase_price - down_payment)

    pi_monthly = monthly_payment(loan_amount, interest_rate, term_years)

    gross_rent_annual = rent_monthly * 12.0
    noi_annual = gross_rent_annual * (1.0 - opex_ratio)

    other_costs_annual = 12.0 * (monthly_taxes + monthly_insurance + monthly_hoa + monthly_maintenance)

    debt_service_annual = pi_monthly * 12.0

    cash_flow_annual = noi_annual - debt_service_annual - other_costs_annual
    cash_flow_monthly = cash_flow_annual / 12.0

    cap_rate_pct = (noi_annual / purchase_price * 100.0) if purchase_price > 0 else 0.0
    cash_on_cash_pct = (cash_flow_annual / down_payment * 100.0) if down_payment > 0 else 0.0

    price_per_sqft = (purchase_price / sqft) if sqft and sqft > 0 else None

    return {
        "down_payment": down_payment,
        "loan_amount": loan_amount,
        "pi_monthly": pi_monthly,
        "gross_rent_annual": gross_rent_annual,
        "noi_annual": noi_annual,
        "other_costs_annual": other_costs_annual,
        "debt_service_annual": debt_service_annual,
        "cash_flow_monthly": cash_flow_monthly,
        "cash_flow_annual": cash_flow_annual,
        "cap_rate_pct": cap_rate_pct,
        "cash_on_cash_pct": cash_on_cash_pct,
        "price_per_sqft": price_per_sqft,
    }


def status_for_cashflow(cash_flow_monthly: float, green_thresh: float, yellow_thresh: float) -> str:
    if cash_flow_monthly >= green_thresh:
        return "✅ Worth a deeper look"
    if cash_flow_monthly >= yellow_thresh:
        return "⚠️ Marginal (tight deal)"
    return "❌ Likely not worth pursuing (negative/weak cash flow)"


# ----------------------------
# UI
# ----------------------------
ensure_tables()

st.title("🏠 Real Estate Deal Analyzer")
st.caption("Backend-driven underwriting tool (Python, SQL, API data)")

with st.sidebar:
    st.header("Status thresholds")
    green_thresh = st.number_input("Green if monthly cash flow ≥", value=200.0, step=50.0)
    yellow_thresh = st.number_input("Yellow if monthly cash flow ≥", value=0.0, step=50.0)

    st.divider()
    st.header("Defaults")
    default_down = st.slider("Default down payment (%)", 0, 50, 20, 1)
    default_opex_pct = st.slider("Default OpEx ratio (%)", 0, 80, 35, 1)
    default_rate = st.slider("Default interest rate (%)", 0.0, 15.0, 7.0, 0.25)
    default_term = st.selectbox("Default term (years)", [15, 20, 25, 30], index=3)

tabs = st.tabs(["QuickCheck", "Saved Deals", "Compare Deals"])


# ----------------------------
# Tab 1: QuickCheck
# ----------------------------
with tabs[0]:
    st.subheader("1) Enter the deal")

    with st.form("quickcheck_form"):
        address = st.text_input("Property address", value="350 5th Ave, New York, NY")

        cA, cB, cC = st.columns(3)
        with cA:
            purchase_price = st.number_input("Purchase price ($)", min_value=0.0, value=900000.0, step=10000.0)
        with cB:
            rent_monthly = st.number_input("Estimated rent (monthly $)", min_value=0.0, value=6000.0, step=100.0)
        with cC:
            sqft = st.number_input("Sqft (optional)", min_value=0.0, value=3450.0, step=50.0)

        st.subheader("2) Financing & operating assumptions")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            down_payment_pct = st.slider("Down Payment (%)", 0, 60, int(default_down), 1)
        with c2:
            opex_ratio = st.slider("Operating Expense (%)", 0, 80, int(default_opex_pct), 1) / 100.0
        with c3:
            interest_rate = st.slider("Interest Rate (%)", 0.0, 15.0, float(default_rate), 0.25)
        with c4:
            term_years = st.selectbox("Loan Term (years)", [15, 20, 25, 30], index=[15, 20, 25, 30].index(default_term))

        st.subheader("3) Monthly fixed costs (optional, but recommended)")
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            monthly_taxes = st.number_input("Taxes ($/mo)", min_value=0.0, value=0.0, step=50.0)
        with k2:
            monthly_insurance = st.number_input("Insurance ($/mo)", min_value=0.0, value=0.0, step=25.0)
        with k3:
            monthly_hoa = st.number_input("HOA ($/mo)", min_value=0.0, value=0.0, step=25.0)
        with k4:
            monthly_maintenance = st.number_input("Maintenance ($/mo)", min_value=0.0, value=0.0, step=25.0)

        label = st.text_input("Label (optional)", value="")
        notes = st.text_area("Notes (optional)", value="", height=90)

        submitted = st.form_submit_button("Run QuickCheck + Save")

    if submitted:
        result = analyze_deal(
            purchase_price=purchase_price,
            rent_monthly=rent_monthly,
            sqft=sqft,
            down_payment_pct=down_payment_pct,
            interest_rate=interest_rate,
            term_years=term_years,
            opex_ratio=opex_ratio,
            monthly_taxes=monthly_taxes,
            monthly_insurance=monthly_insurance,
            monthly_hoa=monthly_hoa,
            monthly_maintenance=monthly_maintenance,
        )

        status = status_for_cashflow(result["cash_flow_monthly"], green_thresh, yellow_thresh)

        row = {
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "address": address,
            "purchase_price": purchase_price,
            "estimated_rent_monthly": rent_monthly,
            "sqft": sqft,
            "down_payment_pct": down_payment_pct,
            "interest_rate": interest_rate,
            "term_years": term_years,
            "opex_ratio": opex_ratio,
            "monthly_taxes": monthly_taxes,
            "monthly_insurance": monthly_insurance,
            "monthly_hoa": monthly_hoa,
            "monthly_maintenance": monthly_maintenance,
            "mortgage_pi_monthly": result["pi_monthly"],
            "noi_annual": result["noi_annual"],
            "cap_rate_pct": result["cap_rate_pct"],
            "cash_flow_monthly": result["cash_flow_monthly"],
            "cash_flow_annual": result["cash_flow_annual"],
            "cash_on_cash_pct": result["cash_on_cash_pct"],
            "status": status,
            "label": label.strip() if label else "",
            "notes": notes.strip() if notes else "",
        }

        insert_quickcheck(row)

        st.success(f"Saved ✅  Status: {status}")
        st.subheader("Results")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Cash flow (monthly)", f"${result['cash_flow_monthly']:,.2f}")
        m2.metric("Cash-on-cash", f"{result['cash_on_cash_pct']:.2f}%")
        m3.metric("Cap rate", f"{result['cap_rate_pct']:.2f}%")
        if result["price_per_sqft"] is None:
            m4.metric("Price / sqft", "—")
        else:
            m4.metric("Price / sqft", f"${result['price_per_sqft']:,.2f}")

        st.caption("NOI uses OpEx ratio; fixed costs (tax/ins/HOA/maint) are added separately from OpEx.")


# ----------------------------
# Tab 2: Saved Deals
# ----------------------------
with tabs[1]:
    st.subheader("Saved Deals")

    df = fetch_quickchecks_df()

    if df.empty:
        st.info("No saved deals yet. Use QuickCheck tab to save your first one.")
    else:
        # search + filter
        c1, c2 = st.columns([2, 1])
        with c1:
            search = st.text_input("Search (address or label)", value="")
        with c2:
            statuses = ["All"] + sorted([s for s in df["status"].dropna().unique().tolist()])
            status_filter = st.selectbox("Filter status", statuses)

        filtered = df.copy()
        if search.strip():
            s = search.strip().lower()
            filtered = filtered[
                filtered["address"].fillna("").str.lower().str.contains(s)
                | filtered["label"].fillna("").str.lower().str.contains(s)
            ]
        if status_filter != "All":
            filtered = filtered[filtered["status"] == status_filter]

        show_cols = [
            "id", "created_at", "address", "label",
            "purchase_price", "estimated_rent_monthly", "sqft",
            "cash_flow_monthly", "cap_rate_pct", "cash_on_cash_pct", "status"
        ]
        st.dataframe(filtered[show_cols], use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("View / Delete")

        left, right = st.columns([1, 1])

        with left:
            view_id = st.number_input("Deal ID to view", min_value=0, step=1, value=0)
            if st.button("View deal details"):
                one = fetch_one(int(view_id))
                if not one:
                    st.warning("No deal found with that ID.")
                else:
                    st.write(f"**{one['address']}**")
                    if one.get("label"):
                        st.write(f"Label: {one['label']}")
                    st.write(f"Created: {one['created_at']}")
                    st.write(f"Status: {one.get('status','')}")
                    st.write("---")
                    st.write("**Inputs**")
                    st.write({
                        "purchase_price": one["purchase_price"],
                        "estimated_rent_monthly": one["estimated_rent_monthly"],
                        "sqft": one["sqft"],
                        "down_payment_pct": one["down_payment_pct"],
                        "interest_rate": one["interest_rate"],
                        "term_years": one["term_years"],
                        "opex_ratio": one["opex_ratio"],
                        "monthly_taxes": one["monthly_taxes"],
                        "monthly_insurance": one["monthly_insurance"],
                        "monthly_hoa": one["monthly_hoa"],
                        "monthly_maintenance": one["monthly_maintenance"],
                    })
                    st.write("**Results**")
                    st.write({
                        "mortgage_pi_monthly": one["mortgage_pi_monthly"],
                        "noi_annual": one["noi_annual"],
                        "cap_rate_pct": one["cap_rate_pct"],
                        "cash_flow_monthly": one["cash_flow_monthly"],
                        "cash_flow_annual": one["cash_flow_annual"],
                        "cash_on_cash_pct": one["cash_on_cash_pct"],
                    })
                    if one.get("notes"):
                        st.write("**Notes**")
                        st.write(one["notes"])

        with right:
            del_id = st.number_input("Deal ID to delete", min_value=0, step=1, value=0, key="del_id")
            confirm = st.checkbox("I understand this is permanent.")
            if st.button("Delete deal"):
                if not confirm:
                    st.error("Please check the confirmation box first.")
                else:
                    delete_quickcheck(int(del_id))
                    st.success(f"Deleted deal {int(del_id)}.")
                    st.rerun()


# ----------------------------
# Tab 3: Compare Deals
# ----------------------------
with tabs[2]:
    st.subheader("Compare Deals")

    df = fetch_quickchecks_df()
    if df.empty:
        st.info("Save at least 2 deals first.")
    else:
        options = df[["id", "address", "label"]].copy()
        options["display"] = options.apply(
            lambda r: f"{int(r['id'])} — {r['address']}" + (f" ({r['label']})" if str(r["label"]).strip() else ""),
            axis=1
        )
        id_map = dict(zip(options["display"], options["id"]))

        c1, c2 = st.columns(2)
        with c1:
            a = st.selectbox("Deal A", options["display"].tolist(), index=0)
        with c2:
            b = st.selectbox("Deal B", options["display"].tolist(), index=min(1, len(options) - 1))

        a_id = int(id_map[a])
        b_id = int(id_map[b])

        A = fetch_one(a_id)
        B = fetch_one(b_id)

        if not A or not B:
            st.warning("Could not load one of the deals.")
        else:
            metrics = [
                ("Purchase price", "purchase_price", "${:,.0f}"),
                ("Rent (monthly)", "estimated_rent_monthly", "${:,.0f}"),
                ("Sqft", "sqft", "{:,.0f}"),
                ("Cash flow (monthly)", "cash_flow_monthly", "${:,.2f}"),
                ("Cash flow (annual)", "cash_flow_annual", "${:,.2f}"),
                ("Cap rate", "cap_rate_pct", "{:.2f}%"),
                ("Cash-on-cash", "cash_on_cash_pct", "{:.2f}%"),
                ("Mortgage P&I (monthly)", "mortgage_pi_monthly", "${:,.2f}"),
                ("NOI (annual)", "noi_annual", "${:,.2f}"),
            ]

            rows = []
            for label, key, fmt in metrics:
                av = safe_float(A.get(key), 0.0)
                bv = safe_float(B.get(key), 0.0)
                rows.append({
                    "Metric": label,
                    "Deal A": fmt.format(av),
                    "Deal B": fmt.format(bv),
                    "Delta (B - A)": fmt.format(bv - av) if "%" not in fmt else fmt.format(bv - av),
                })

            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            st.divider()
            st.caption("Tip: Compare monthly cash flow and cash-on-cash first; cap rate is NOI-based (before debt).")
