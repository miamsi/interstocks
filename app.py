import streamlit as st
import pandas as pd
import yfinance as yf
from supabase import create_client, Client
from groq import Groq
import time
import os
from datetime import datetime

# --- SETUP ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)
groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# --- DATA FUNCTIONS ---

def load_tickers_from_excel():
    file_name = "Daftar Saham  - 20260306.xlsx"
    if not os.path.exists(file_name):
        return []
    try:
        df = pd.read_excel(file_name)
        tickers = df['Kode'].dropna().astype(str).tolist()
        return [f"{t}.JK" for t in tickers if len(t) == 4]
    except:
        return []


def load_bonds_data():

    possible_files = [
        "LIST HARGA OBLIGASI PER 12 MARET 2026.xlsx - Sheet1.csv",
        "LIST HARGA OBLIGASI PER 12 MARET 2026.xlsx"
    ]

    df_bonds = pd.DataFrame()

    for f in possible_files:
        if os.path.exists(f):
            try:
                df_bonds = pd.read_csv(f) if f.endswith(".csv") else pd.read_excel(f)
                break
            except:
                continue

    if df_bonds.empty:
        return pd.DataFrame()

    df_bonds.columns = [c.strip().replace("'", "").replace('"', "") for c in df_bonds.columns]

    rename_map = {
        "BONDS CODE": "ticker",
        "YEARLY COUPON RATE": "coupon",
        "LATEST PRICE PER UNIT": "price"
    }

    df_bonds = df_bonds.rename(columns=rename_map)

    face = 1000000

    if "coupon" in df_bonds.columns and "price" in df_bonds.columns:

        df_bonds["coupon"] = pd.to_numeric(df_bonds["coupon"], errors="coerce")
        df_bonds["price"] = pd.to_numeric(df_bonds["price"], errors="coerce")

        df_bonds["real_yield"] = (df_bonds["coupon"] * face / df_bonds["price"]) * 100

    return df_bonds.dropna(subset=["ticker", "price"])


def get_oldest_price_batch(batch_size=1000):
    try:
        res = supabase.table("master_schedule")\
            .select("ticker")\
            .order("last_mined", desc=False)\
            .limit(batch_size)\
            .execute()

        return [r["ticker"] for r in res.data]

    except:
        return []


def get_stock_label(yield_val, pe, payout):

    if pd.isna(yield_val) or yield_val <= 0:
        return "⚪ No Data"

    if pd.isna(pe) or pd.isna(payout) or pe == 0:
        return "🌀 Speculative (Data Gap)"

    if payout > 95:
        return "🚨 Yield Trap (Unsustainable)"

    if yield_val > 7 and pe < 12 and payout < 75:
        return "💎 Dividend King (High Value)"

    if yield_val > 4 and payout < 65:
        return "🐄 Stable Cash Cow"

    if pe > 25:
        return "🎈 Overvalued (Price too high)"

    return "🔍 Neutral / Under Analysis"


# --- PORTFOLIO ENGINE ---

def calculate_risk_score(drawdown, horizon):

    score = 0

    if drawdown == "Sell everything":
        score += 1

    elif drawdown == "Wait":
        score += 2

    elif drawdown == "Buy more":
        score += 3

    if horizon == "5+ Tahun":
        score += 2

    return score


def allocation_from_risk(score):

    if score <= 2:
        return 0.25, 0.75

    elif score <= 4:
        return 0.5, 0.5

    else:
        return 0.75, 0.25


def select_stocks(df):

    df = df[
        (df["payout_ratio"] < 85) &
        (df["dividend_yield"] > 3) &
        (df["pe_ratio"] < 20)
    ]

    df["score"] = (
        df["dividend_yield"] * 0.5 +
        (1 / df["pe_ratio"]) * 0.3 +
        (1 - df["payout_ratio"] / 100) * 0.2
    )

    return df.sort_values("score", ascending=False).head(5)


def simulate_portfolio(budget, stock_pct, bond_pct, stocks, bonds):

    stock_capital = budget * stock_pct
    bond_capital = budget * bond_pct

    stock_yield = stocks["dividend_yield"].mean()

    bond_yield = bonds["real_yield"].mean()

    stock_income = stock_capital * (stock_yield / 100)

    bond_income = bond_capital * (bond_yield / 100)

    total_income = stock_income + bond_income

    monthly_income = total_income / 12

    worst_stock = stock_capital * 0.30
    worst_bond = bond_capital * 0.08

    worst_case = budget - worst_stock - worst_bond

    return {
        "stock_capital": stock_capital,
        "bond_capital": bond_capital,
        "stock_income": stock_income,
        "bond_income": bond_income,
        "total_income": total_income,
        "monthly_income": monthly_income,
        "worst_case": worst_case
    }


# --- AI EXPLANATION ---

def run_groq_simulation(profile, stocks, bonds, simulation):

    prompt = f"""
ROLE: Senior Indonesian Portfolio Strategist.

INVESTOR PROFILE
Budget: Rp {profile['budget']:,.0f}
Horizon: {profile['horizon']}
Priority: {profile['priority']}
Concern: {profile['concern']}

SELECTED STOCKS
{stocks[['ticker','dividend_yield','pe_ratio']].to_string(index=False)}

SELECTED BONDS
{bonds[['ticker','real_yield']].to_string(index=False)}

PORTFOLIO SIMULATION

Expected yearly income: Rp {simulation['total_income']:,.0f}
Expected monthly income: Rp {simulation['monthly_income']:,.0f}

Worst case portfolio value: Rp {simulation['worst_case']:,.0f}

Explain why this portfolio fits the investor.
"""

    completion = groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.2
    )

    return completion.choices[0].message.content


# --- UI ---

st.set_page_config(page_title="IHSG Dividend Master", layout="wide")

st.title("🏆 IHSG Dividend Master (Pro Filter Edition)")

tab_sim, tab_list, tab_search = st.tabs([
    "🤖 AI Advisor Simulation",
    "🔥 Dividend Leaderboard",
    "🔍 Ticker Analysis"
])

# ---------------- SIMULATION ----------------

with tab_sim:

    st.subheader("🤖 Smart Portfolio Advisor")

    with st.form("deep_wizard"):

        col1, col2 = st.columns(2)

        with col1:

            u_budget = st.number_input(
                "Total Dana Investasi",
                value=50000000,
                step=5000000
            )

            u_priority = st.selectbox(
                "Tujuan Investasi",
                [
                    "Passive Income",
                    "Pertumbuhan Aset",
                    "Keamanan Modal"
                ]
            )

        with col2:

            u_horizon = st.selectbox(
                "Jangka Waktu",
                [
                    "< 1 Tahun",
                    "1-3 Tahun",
                    "3-5 Tahun",
                    "5+ Tahun"
                ]
            )

            u_drawdown = st.selectbox(
                "Jika portfolio turun 30%",
                [
                    "Sell everything",
                    "Wait",
                    "Buy more"
                ]
            )

        u_concern = st.text_area(
            "Kekhawatiran utama",
            "Saya takut kehilangan uang."
        )

        submit_sim = st.form_submit_button("Generate Strategy")

    if submit_sim:

        profile = {
            "budget": u_budget,
            "priority": u_priority,
            "horizon": u_horizon,
            "concern": u_concern
        }

        risk_score = calculate_risk_score(u_drawdown, u_horizon)

        stock_pct, bond_pct = allocation_from_risk(risk_score)

        df_b = load_bonds_data()

        res = supabase.table("master_schedule")\
            .select("*")\
            .not_.is_("dividend_yield", "null")\
            .limit(200)\
            .execute()

        df_s = pd.DataFrame(res.data)

        df_s["Category"] = df_s.apply(
            lambda x: get_stock_label(
                x["dividend_yield"],
                x["pe_ratio"],
                x["payout_ratio"]
            ), axis=1
        )

        top_stocks = select_stocks(df_s)

        bonds = df_b.sort_values("real_yield", ascending=False).head(3)

        simulation = simulate_portfolio(
            u_budget,
            stock_pct,
            bond_pct,
            top_stocks,
            bonds
        )

        st.subheader("Portfolio Allocation")

        st.write(f"Stocks: {stock_pct*100:.0f}%")
        st.write(f"Bonds: {bond_pct*100:.0f}%")

        st.subheader("Expected Passive Income")

        st.write(f"Yearly: Rp {simulation['total_income']:,.0f}")
        st.write(f"Monthly: Rp {simulation['monthly_income']:,.0f}")

        st.subheader("Risk Scenario")

        st.write(f"Worst case portfolio value: Rp {simulation['worst_case']:,.0f}")

        with st.spinner("AI Advisor analyzing..."):

            explanation = run_groq_simulation(
                profile,
                top_stocks,
                bonds,
                simulation
            )

        st.markdown(explanation)


# ---------------- LEADERBOARD ----------------

with tab_list:

    st.subheader("🔥 Dividend Leaderboard")

    with st.expander("Filter Controls", expanded=True):

        f1, f2, f3 = st.columns(3)

        cat_options = [
            "All Categories",
            "💎 Dividend King (High Value)",
            "🐄 Stable Cash Cow",
            "🔍 Neutral / Under Analysis",
            "🌀 Speculative (Data Gap)",
            "🚨 Yield Trap (Unsustainable)",
            "🎈 Overvalued (Price too high)"
        ]

        selected_cat = f1.selectbox("Category", cat_options)

        min_yield = f2.slider("Min Yield", 0.0, 30.0, 0.0)

        hide_spec = f3.checkbox("Hide Speculative", True)

    view_res = supabase.table("master_schedule")\
        .select("*")\
        .not_.is_("dividend_yield", "null")\
        .order("dividend_yield", desc=True)\
        .limit(500)\
        .execute()

    if view_res.data:

        df = pd.DataFrame(view_res.data)

        df["Category"] = df.apply(
            lambda x: get_stock_label(
                x["dividend_yield"],
                x["pe_ratio"],
                x["payout_ratio"]
            ), axis=1
        )

        if selected_cat != "All Categories":
            df = df[df["Category"] == selected_cat]

        df = df[df["dividend_yield"] >= min_yield]

        if hide_spec:
            df = df[~df["Category"].str.contains("Speculative")]

        st.dataframe(
            df[[
                "ticker",
                "Category",
                "dividend_yield",
                "pe_ratio",
                "payout_ratio",
                "previous_close"
            ]],
            use_container_width=True
        )


# ---------------- SEARCH ----------------

with tab_search:

    st.subheader("Smart Ticker Analysis")

    search_ticker = st.text_input("Ticker").upper()

    if search_ticker:

        res = supabase.table("master_schedule")\
            .select("*")\
            .eq("ticker", search_ticker)\
            .execute()

        if res.data:

            df = pd.DataFrame(res.data)

            st.dataframe(df)

        else:

            st.warning("Ticker not found")


# ---------------- SIDEBAR ----------------

all_ihsg = load_tickers_from_excel()

update_queue = get_oldest_price_batch(1000)

with st.sidebar:

    st.header("Mining Engine")

    st.write(f"Total Tickers: {len(all_ihsg)}")

    if st.button("Update Next Batch"):

        st.write("Mining pipeline ready")
