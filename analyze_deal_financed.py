import sqlite3
from math import pow

DB = "realestate.db"

def monthly_payment(principal: float, annual_rate: float, years: int) -> float:
    """Standard fixed-rate mortgage payment (P&I)."""
    if principal <= 0:
        return 0.0
    r = annual_rate / 12.0
    n = years * 12
    if r == 0:
        return principal / n
    return principal * (r * pow(1 + r, n)) / (pow(1 + r, n) - 1)

def money(x):
    return f"${x:,.2f}"

def pct(x):
    return f"{x:.2f}%"

conn = sqlite3.connect(DB)
cur = conn.cursor()

# Get the most recent deal input joined to property facts
row = cur.execute("""
SELECT
  pf.id,
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
    raise SystemExit("No deals found. Insert a row into deal_inputs first.")

(property_fact_id, address, sqft, purchase_price, estimated_rent,
 monthly_taxes, monthly_insurance, monthly_hoa, monthly_maintenance_reserve) = row


# ---- Assumptions (edit these later) ----
down_payment_pct = 0.20        # 20% down
annual_interest_rate = 0.07    # 7% APR
loan_term_years = 30

# operating expense ratio (as % of gross rent)
opex_ratio = 0.35              # 35% of rent

# ---- Calculations ----
gross_rent_monthly = float(estimated_rent or 0)
gross_rent_annual = gross_rent_monthly * 12

opex_annual = gross_rent_annual * opex_ratio
noi_annual = gross_rent_annual - opex_annual

down_payment = float(purchase_price) * down_payment_pct
loan_amount = float(purchase_price) - down_payment

p_and_i_monthly = monthly_payment(loan_amount, annual_interest_rate, loan_term_years)
debt_service_annual = p_and_i_monthly * 12

other_costs_annual = 12 * (monthly_taxes + monthly_insurance + monthly_hoa + monthly_maintenance_reserve)

cash_flow_annual = noi_annual - debt_service_annual - other_costs_annual
cash_flow_monthly = cash_flow_annual / 12

# Cash invested (simple): down payment (later we can add closing costs)
cash_invested = down_payment

cap_rate = (noi_annual / float(purchase_price) * 100) if purchase_price else 0
coc_return = (cash_flow_annual / cash_invested * 100) if cash_invested else 0

# ---- Output ----
print("\n=== DEAL SUMMARY (FINANCED) ===")
print("Address:", address)
print("Sqft:", sqft)
print("Purchase price:", money(purchase_price))
print("Estimated rent (monthly):", money(gross_rent_monthly))

print("\n--- Assumptions ---")
print("Down payment %:", pct(down_payment_pct * 100))
print("Interest rate:", pct(annual_interest_rate * 100))
print("Term (years):", loan_term_years)
print("OpEx ratio:", pct(opex_ratio * 100))

print("\n--- Results ---")
print("Gross rent (annual):", money(gross_rent_annual))
print("Operating expenses (annual):", money(opex_annual))
print("NOI (annual):", money(noi_annual))
print("Mortgage P&I (monthly):", money(p_and_i_monthly))
print("Debt service (annual):", money(debt_service_annual))
print("Other costs (annual):", money(other_costs_annual))
print("Cash flow (monthly):", money(cash_flow_monthly))
print("Cash flow (annual):", money(cash_flow_annual))
print("Cap rate:", pct(cap_rate))
print("Cash-on-cash return:", pct(coc_return))
print("Cash invested (down payment):", money(cash_invested))
print("==============================\n")
