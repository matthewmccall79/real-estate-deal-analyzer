import sqlite3
import streamlit as st
import os

# ----------------------------
# Config
# ----------------------------
st.set_page_config(
    page_title="Real Estate Deal Analyzer",
    layout="centered"
)

DB_PATH = os.path.join(os.path.dirname(__file__), "realestate.db")

# ----------------------------
# Helpers
# ----------------------------
def monthly_payment(principal, annual_rate, years):
    if principal <= 0:
        return 0.0
    r = annual_rate / 12
    n = years * 12
    if r == 0:
        return principal / n
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


def get_latest_deal():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    row = cur.execute("""
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
    """).fetchone()

    conn.close()
    return row


# ----------------------------
# App Header
# ----------------------------
st.title("🏠 Real Estate Deal Analyzer")
st.caption("Backend-driven underwriting tool (Python • SQL • API data)")

deal = get_latest_deal()

if not deal:
    st.error("No deal data found in database.")
    st.stop()

address, sqft, price, rent, tax, ins, hoa, maint = deal

# ----------------------------
# Tabs
# ----------------------------
tab1, tab2, tab3 = st.tabs(["QuickCheck", "Saved Deals", "Compare Deals"])

# ==========================================================
# TAB 1 — QUICKCHECK
# ==========================================================
with tab1:
    st.subheader("Property")
    st.write(address)
    st.write(f"Square Feet: {sqft}")

    st.subheader("Financing & Operating Assumptions")

    with st.form("quickcheck_form"):
        col1, col2 = st.columns(2)

        with col1:
            down_pct = st.slider("Down Payment (%)", 5, 40, 20) / 100
            interest_rate = st.slider("Interest Rate (%)", 3.0, 10.0, 7.0) / 100
            term_years = st.selectbox("Loan Term (years)", [15, 30], index=1)

        with col2:
            opex_ratio = st.slider("Operating Expense (%)", 20, 50, 35) / 100

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            monthly_taxes = st.number_input("Taxes ($/mo)", min_value=0.0, value=tax)
        with c2:
            monthly_insurance = st.number_input("Insurance ($/mo)", min_value=0.0, value=ins)
        with c3:
            monthly_hoa = st.number_input("HOA ($/mo)", min_value=0.0, value=hoa)
        with c4:
            monthly_maintenance = st.number_input("Maintenance ($/mo)", min_value=0.0, value=maint)

        submitted = st.form_submit_button("Run QuickCheck")

    if submitted:
        loan_amount = price * (1 - down_pct)
        mortgage_pmt = monthly_payment(loan_amount, interest_rate, term_years)

        gross_rent_annual = rent * 12
        noi_annual = gross_rent_annual * (1 - opex_ratio)
        fixed_costs_annual = 12 * (
            monthly_taxes +
            monthly_insurance +
            monthly_hoa +
            monthly_maintenance
        )

        cash_flow_annual = noi_annual - (mortgage_pmt * 12) - fixed_costs_annual
        cash_flow_monthly = cash_flow_annual / 12
        cash_invested = price * down_pct

        cap_rate = (noi_annual / price) * 100 if price else 0
        coc_return = (cash_flow_annual / cash_invested) * 100 if cash_invested else 0

        st.subheader("Results")
        colA, colB, colC = st.columns(3)
        colA.metric("Monthly Cash Flow", f"${cash_flow_monthly:,.2f}")
        colB.metric("Cash-on-Cash Return", f"{coc_return:.2f}%")
        colC.metric("Cap Rate", f"{cap_rate:.2f}%")

# ==========================================================
# TAB 2 — SAVED DEALS
# ==========================================================
with tab2:
    st.info("Saved deals functionality ready for expansion.")
    st.write("Future version will list saved underwriting runs from the database.")

# ==========================================================
# TAB 3 — COMPARE DEALS
# ==========================================================
with tab3:
    st.info("Deal comparison functionality ready for expansion.")
    st.write("Future version will allow side-by-side deal comparison.")
