import sqlite3
from math import pow
import streamlit as st

import os

DB = os.path.join(os.path.dirname(__file__), "realestate.db")


def monthly_payment(principal, annual_rate, years):
    if principal <= 0:
        return 0.0
    r = annual_rate / 12
    n = years * 12
    if r == 0:
        return principal / n
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)

st.set_page_config(page_title="Real Estate Deal Analyzer", layout="centered")

st.title("🏠 Real Estate Deal Analyzer")
st.caption("Backend-driven underwriting tool (Python, SQL, API data)")

conn = sqlite3.connect(DB)
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

if not row:
    st.error("No deal data found.")
    st.stop()

address, sqft, price, rent, tax, ins, hoa, maint = row

st.subheader("Property")
st.write(address)
st.write(f"Square Feet: {sqft}")

st.subheader("Inputs")
col1, col2 = st.columns(2)

with col1:
    down_pct = st.slider("Down Payment (%)", 5, 40, 20) / 100
    rate = st.slider("Interest Rate (%)", 3.0, 10.0, 7.0) / 100
    term = st.selectbox("Loan Term (years)", [15, 30], index=1)

with col2:
    opex_ratio = st.slider("Operating Expense (%)", 20, 50, 35) / 100

loan = price * (1 - down_pct)
pmt = monthly_payment(loan, rate, term)

gross_annual = rent * 12
noi = gross_annual * (1 - opex_ratio)
other_costs = 12 * (tax + ins + hoa + maint)

cash_flow_annual = noi - (pmt * 12) - other_costs
cash_flow_monthly = cash_flow_annual / 12
cash_invested = price * down_pct

cap_rate = noi / price * 100
coc = (cash_flow_annual / cash_invested * 100) if cash_invested else 0

st.subheader("Results")

st.metric("Cash Flow (Monthly)", f"${cash_flow_monthly:,.2f}")
st.metric("Cash-on-Cash Return", f"{coc:.2f}%")
st.metric("Cap Rate", f"{cap_rate:.2f}%")

