import os
import json
import sqlite3
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

import requests
import streamlit as st
import pandas as pd

# Local modules you created in Steps 4.A–4.C
from attom_client import lookup_property_by_address
from db_ops import upsert_property_fact, insert_deal_input, list_saved_deals, get_deal_by_id

# Optional: ensure schema is present (safe to run repeatedly)
try:
    from db_schema import ensure_columns
    ensure_columns()
except Exception:
    # If db_schema isn't available or fails, app can still run;
    # you already ran schema alignment manually.
    pass


DB_FILE = os.path.join(os.path.dirname(__file__), "realestate.db")


# =========================
# Helpers: API key bridging
# =========================
def ensure_attom_key_available():
    """
    Your attom_client reads ATTOM_API_KEY from environment variables.
    Streamlit Cloud provides secrets via st.secrets.
    This bridges st.secrets -> os.environ when needed.
    """
    if os.getenv("ATTOM_API_KEY"):
        return
    try:
        key = st.secrets.get("ATTOM_API_KEY")
        if key:
            os.environ["ATTOM_API_KEY"] = str(key)
    except Exception:
        pass


# =========================
# Helpers: autocomplete
# =========================
def nominatim_suggest(query: str, limit: int = 6) -> List[str]:
    q = (query or "").strip()
    if len(q) < 4:
        return []

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": q, "format": "json", "addressdetails": 0, "limit": str(limit)}
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


# =========================
# Finance
# =========================
def monthly_payment(principal: float, annual_rate: float, years: int) -> float:
    if principal <= 0:
        return 0.0
    r = annual_rate / 12
    n = years * 12
    if r == 0:
        return principal / n
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


@dataclass
class Inputs:
    address: str
    sqft: Optional[float]
    purchase_price: float
    rent_monthly: float

    down_pct: float
    interest_rate: float
    term_years: int

    vacancy_pct: float
    mgmt_pct: float
    opex_pct: float

    taxes_monthly: float
    insurance_monthly: float
    hoa_monthly: float
    maintenance_monthly: float
    other_monthly: float

    reserves_monthly: float
    capex_monthly: float

    closing_cost_pct: float
    lender_points_pct: float


def underwrite(x: Inputs) -> Dict[str, float]:
    loan = x.purchase_price * (1 - x.down_pct)
    pmt = monthly_payment(loan, x.interest_rate, x.term_years)

    gross_annual = x.rent_monthly * 12
    vacancy_loss = gross_annual * x.vacancy_pct
    effective_gross = gross_annual - vacancy_loss

    mgmt_cost = effective_gross * x.mgmt_pct
    base_opex = effective_gross * x.opex_pct

    fixed_annual = 12 * (
        x.taxes_monthly
        + x.insurance_monthly
        + x.hoa_monthly
        + x.maintenance_monthly
        + x.other_monthly
        + x.reserves_monthly
        + x.capex_monthly
    )

    opex_total = mgmt_cost + base_opex + fixed_annual
    noi = effective_gross - opex_total

    debt_annual = pmt * 12
    cash_flow_annual = noi - debt_annual
    cash_flow_monthly = cash_flow_annual / 12

    cash_down = x.purchase_price * x.down_pct
    closing_costs = x.purchase_price * x.closing_cost_pct
    points_cost = loan * x.lender_points_pct
    cash_invested_total = cash_down + closing_costs + points_cost

    cap_rate = (noi / x.purchase_price * 100) if x.purchase_price else 0.0
    coc = (cash_flow_annual / cash_invested_total * 100) if cash_invested_total else 0.0
    ppsf = (x.purchase_price / x.sqft) if x.sqft and x.sqft > 0 else 0.0

    # Breakeven rent (rough): solve CF = 0
    breakeven_rent_monthly = 0.0
    denom = 12 * (1 - x.vacancy_pct) * (1 - (x.mgmt_pct + x.opex_pct))
    if denom > 0:
        breakeven_rent_monthly = (fixed_annual + debt_annual) / denom

    return {
        "loan_amount": loan,
        "mortgage_pmt_monthly": pmt,
        "gross_rent_annual": gross_annual,
        "effective_gross_annual": effective_gross,
        "operating_expenses_annual": opex_total,
        "noi_annual": noi,
        "debt_service_annual": debt_annual,
        "cash_flow_monthly": cash_flow_monthly,
        "cash_flow_annual": cash_flow_annual,
        "cap_rate_pct": cap_rate,
        "coc_return_pct": coc,
        "cash_invested_total": cash_invested_total,
        "price_per_sqft": ppsf,
        "breakeven_rent_monthly": breakeven_rent_monthly,
    }


def score_badge(metrics: Dict[str, float]) -> str:
    cf = metrics["cash_flow_monthly"]
    coc = metrics["coc_return_pct"]
    cap = metrics["cap_rate_pct"]

    if cf >= 250 and coc >= 8 and cap >= 6:
        return "🟢 GREEN"
    if cf >= 0 and coc >= 4 and cap >= 4.5:
        return "🟡 YELLOW"
    return "🔴 RED"


# =========================
# UI
# =========================
st.set_page_config(page_title="Real Estate Deal Analyzer", layout="wide")
st.title("🏠 Real Estate Deal Analyzer")
st.caption("Autocomplete address → ATTOM lookup (sqft) → Underwrite → Save → Compare")

ensure_attom_key_available()

tab1, tab2, tab3 = st.tabs(["QuickCheck", "Saved Deals", "Compare Deals"])

# Session defaults
if "loaded_deal" not in st.session_state:
    st.session_state["loaded_deal"] = None
if "lookup_result" not in st.session_state:
    st.session_state["lookup_result"] = {}


# ==========================================================
# TAB 1 — QUICKCHECK
# ==========================================================
with tab1:
    st.subheader("1) Property Lookup")

    loaded = st.session_state.get("loaded_deal")
    default_address = loaded["address"] if loaded else ""
    default_sqft = float(loaded["sqft"] or 0.0) if loaded else 0.0
    default_price = float(loaded["purchase_price"] or 900000) if loaded else 900000.0
    default_rent = float(loaded["estimated_rent"] or 6000) if loaded else 6000.0
    default_tax = float(loaded["monthly_taxes"] or 0) if loaded else 0.0
    default_ins = float(loaded["monthly_insurance"] or 0) if loaded else 0.0
    default_hoa = float(loaded["monthly_hoa"] or 0) if loaded else 0.0
    default_maint = float(loaded["monthly_maintenance"] or 0) if loaded else 0.0
    default_notes = loaded.get("notes", "") if loaded else ""

    typed = st.text_input("Search address", value=default_address)
    suggestions = nominatim_suggest(typed)
    picked = st.selectbox("Suggestions (optional)", ["(use typed address)"] + suggestions)
    lookup_address = typed if picked == "(use typed address)" else picked

    colL, colR = st.columns([1, 2])
    with colL:
        do_lookup = st.button("🔎 Lookup (ATTOM auto-fill sqft)")
    with colR:
        st.caption("If ATTOM fails, you can still enter sqft manually.")

    if do_lookup:
        try:
            p = lookup_property_by_address(lookup_address)
            if not p:
                st.session_state["lookup_result"] = {"error": "No property found for that address."}
            else:
                addr = (p.get("address") or {}).get("oneLine") or lookup_address
                b = p.get("building") or {}
                size = (b.get("size") or {}) if isinstance(b, dict) else {}
                sqft_val = size.get("livingsize") or size.get("bldgsize") or size.get("grosssize")

                st.session_state["lookup_result"] = {
                    "address": addr,
                    "sqft": float(sqft_val) if sqft_val is not None else None,
                    "raw_property": p,
                }
        except Exception as e:
            st.session_state["lookup_result"] = {"error": str(e)}

    res = st.session_state.get("lookup_result", {}) or {}
    if res.get("error"):
        st.error(res["error"])

    display_address = (res.get("address") or lookup_address or default_address).strip()
    sqft_default = res.get("sqft")
    if sqft_default is None:
        sqft_default = default_sqft

    st.write(f"**Using address:** {display_address or '—'}")

    st.divider()
    st.subheader("2) Underwrite")

    with st.form("quickcheck_form"):
        c1, c2, c3 = st.columns(3)

        with c1:
            purchase_price = st.number_input("Purchase price ($)", min_value=0.0, value=float(default_price))
            rent_monthly = st.number_input("Rent (monthly $)", min_value=0.0, value=float(default_rent))
            sqft_input = st.number_input("Sqft (override)", min_value=0.0, value=float(sqft_default or 0.0))

            label = st.text_input("Label (optional)", value="")
            notes = st.text_area("Notes (optional)", value=default_notes, height=80)

        with c2:
            down_pct = st.slider("Down payment (%)", 5, 40, 20) / 100
            interest_rate = st.slider("Interest rate (%)", 3.0, 12.0, 7.0, 0.1) / 100
            term_years = st.selectbox("Term (years)", [15, 30], index=1)

            vacancy_pct = st.slider("Vacancy (%)", 0, 20, 5) / 100
            mgmt_pct = st.slider("Property management (%)", 0, 20, 8) / 100
            opex_pct = st.slider("Base OpEx ratio (%)", 10, 60, 35) / 100

        with c3:
            taxes_monthly = st.number_input("Taxes ($/mo)", min_value=0.0, value=float(default_tax))
            insurance_monthly = st.number_input("Insurance ($/mo)", min_value=0.0, value=float(default_ins))
            hoa_monthly = st.number_input("HOA ($/mo)", min_value=0.0, value=float(default_hoa))
            maintenance_monthly = st.number_input("Maintenance ($/mo)", min_value=0.0, value=float(default_maint))
            other_monthly = st.number_input("Other ($/mo)", min_value=0.0, value=0.0)

            reserves_monthly = st.number_input("Reserves ($/mo)", min_value=0.0, value=150.0)
            capex_monthly = st.number_input("CapEx estimate ($/mo)", min_value=0.0, value=150.0)

            closing_cost_pct = st.slider("Closing costs (%)", 0.0, 6.0, 2.0, 0.1) / 100
            lender_points_pct = st.slider("Lender points (%)", 0.0, 4.0, 1.0, 0.1) / 100

        run_clicked = st.form_submit_button("Run QuickCheck")
        save_clicked = st.form_submit_button("Run + Save Deal")

    if run_clicked or save_clicked:
        x = Inputs(
            address=display_address,
            sqft=float(sqft_input) if sqft_input and sqft_input > 0 else None,
            purchase_price=float(purchase_price),
            rent_monthly=float(rent_monthly),

            down_pct=float(down_pct),
            interest_rate=float(interest_rate),
            term_years=int(term_years),

            vacancy_pct=float(vacancy_pct),
            mgmt_pct=float(mgmt_pct),
            opex_pct=float(opex_pct),

            taxes_monthly=float(taxes_monthly),
            insurance_monthly=float(insurance_monthly),
            hoa_monthly=float(hoa_monthly),
            maintenance_monthly=float(maintenance_monthly),
            other_monthly=float(other_monthly),

            reserves_monthly=float(reserves_monthly),
            capex_monthly=float(capex_monthly),

            closing_cost_pct=float(closing_cost_pct),
            lender_points_pct=float(lender_points_pct),
        )

        m = underwrite(x)
        st.subheader("3) Results")
        st.write(score_badge(m))

        a, b, c, d = st.columns(4)
        a.metric("Monthly Cash Flow", f"${m['cash_flow_monthly']:,.2f}")
        b.metric("Cash-on-Cash", f"{m['coc_return_pct']:.2f}%")
        c.metric("Cap Rate", f"{m['cap_rate_pct']:.2f}%")
        d.metric("Breakeven Rent", f"${m['breakeven_rent_monthly']:,.0f}/mo")

        a2, b2, c2, d2 = st.columns(4)
        a2.metric("Mortgage P&I", f"${m['mortgage_pmt_monthly']:,.2f}/mo")
        b2.metric("NOI", f"${m['noi_annual']:,.0f}/yr")
        c2.metric("Cash Invested", f"${m['cash_invested_total']:,.0f}")
        d2.metric("Price/Sqft", f"${m['price_per_sqft']:,.2f}" if m["price_per_sqft"] else "—")

        if save_clicked:
            # Save property facts (raw) + address + sqft into property_facts
            raw_property = res.get("raw_property")
            json_raw = json.dumps({"property": [raw_property]} if raw_property else {"property": []})

            conn = sqlite3.connect(DB_FILE)

            pf_id = upsert_property_fact(
                conn,
                json_raw=json_raw,
                address=display_address,
                sqft=float(sqft_input) if sqft_input and sqft_input > 0 else None,
            )

            deal_id = insert_deal_input(
                conn,
                property_fact_id=pf_id,
                purchase_price=float(purchase_price),
                estimated_rent=float(rent_monthly),
                monthly_taxes=float(taxes_monthly),
                monthly_insurance=float(insurance_monthly),
                monthly_hoa=float(hoa_monthly),
                monthly_maintenance=float(maintenance_monthly),
                label=(label.strip() if label else ""),
                notes=(notes.strip() if notes else ""),
            )

            conn.close()
            st.success(f"✅ Saved deal (ID {deal_id}). Go to the Saved Deals tab.")


# ==========================================================
# TAB 2 — SAVED DEALS
# ==========================================================
with tab2:
    st.subheader("Saved Deals")

    saved = list_saved_deals(limit=100)
    if not saved:
        st.info("No saved deals yet. Use QuickCheck → Run + Save Deal.")
    else:
        df = pd.DataFrame(saved)
        st.dataframe(df, use_container_width=True)

        st.divider()
        st.subheader("Load a saved deal into QuickCheck")

        deal_ids = df["deal_id"].tolist()
        selected_id = st.selectbox("Choose a deal_id", deal_ids)

        if st.button("Load into QuickCheck"):
            d = get_deal_by_id(int(selected_id))
            if not d:
                st.error("Could not load that deal.")
            else:
                st.session_state["loaded_deal"] = d
                # Clear lookup result so defaults come from loaded deal
                st.session_state["lookup_result"] = {}
                st.success("Loaded. Switch to QuickCheck tab.")
                st.rerun()


# ==========================================================
# TAB 3 — COMPARE DEALS
# ==========================================================
with tab3:
    st.subheader("Compare Deals")

    saved = list_saved_deals(limit=200)
    if len(saved) < 2:
        st.info("Save at least 2 deals to compare them.")
    else:
        df = pd.DataFrame(saved)

        # Choose deals
        labels = []
        id_map = {}
        for _, row in df.iterrows():
            tag = f"{int(row['deal_id'])} • {row.get('label','')} • {row.get('address','')[:60]} • ${float(row['purchase_price']):,.0f}"
            labels.append(tag)
            id_map[tag] = int(row["deal_id"])

        selected = st.multiselect("Select 2+ deals", labels, default=labels[:2])

        if len(selected) >= 2:
            compare_rows = []
            for tag in selected:
                did = id_map[tag]
                d = get_deal_by_id(did)
                if not d:
                    continue

                # Use reasonable defaults for comparison (same as QuickCheck defaults)
                x = Inputs(
                    address=d.get("address", ""),
                    sqft=float(d["sqft"]) if d.get("sqft") else None,
                    purchase_price=float(d["purchase_price"]),
                    rent_monthly=float(d["estimated_rent"]),

                    down_pct=0.20,
                    interest_rate=0.07,
                    term_years=30,

                    vacancy_pct=0.05,
                    mgmt_pct=0.08,
                    opex_pct=0.35,

                    taxes_monthly=float(d.get("monthly_taxes", 0)),
                    insurance_monthly=float(d.get("monthly_insurance", 0)),
                    hoa_monthly=float(d.get("monthly_hoa", 0)),
                    maintenance_monthly=float(d.get("monthly_maintenance", 0)),
                    other_monthly=0.0,

                    reserves_monthly=150.0,
                    capex_monthly=150.0,

                    closing_cost_pct=0.02,
                    lender_points_pct=0.01,
                )

                m = underwrite(x)

                compare_rows.append({
                    "deal_id": did,
                    "label": d.get("label",""),
                    "address": d.get("address",""),
                    "purchase_price": float(d["purchase_price"]),
                    "rent_monthly": float(d["estimated_rent"]),
                    "cash_flow_monthly": float(m["cash_flow_monthly"]),
                    "coc_return_pct": float(m["coc_return_pct"]),
                    "cap_rate_pct": float(m["cap_rate_pct"]),
                    "breakeven_rent_monthly": float(m["breakeven_rent_monthly"]),
                })

            out = pd.DataFrame(compare_rows)
            st.dataframe(out, use_container_width=True)

            st.subheader("Monthly Cash Flow (comparison)")
            chart_series = out.set_index("deal_id")["cash_flow_monthly"]
            st.bar_chart(chart_series)
