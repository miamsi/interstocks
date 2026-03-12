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
        "LATEST PRICE PER UNIT": "price",
        "END DATE": "maturity"
    }

    df_bonds = df_bonds.rename(columns=rename_map)

    face = 1000000

    df_bonds["coupon"] = pd.to_numeric(df_bonds["coupon"], errors="coerce")
    df_bonds["price"] = pd.to_numeric(df_bonds["price"], errors="coerce")

    df_bonds["maturity"] = pd.to_datetime(df_bonds["maturity"], errors="coerce")

    df_bonds["years_to_maturity"] = (
        df_bonds["maturity"] - pd.Timestamp.today()
    ).dt.days / 365

    df_bonds["real_yield"] = (df_bonds["coupon"] * face / df_bonds["price"]) * 100

    return df_bonds.dropna(subset=["ticker", "price"])


# --- BOND FILTER ---


def filter_bonds_by_horizon(df, horizon):

    if horizon == "< 1 Tahun":
        return df[df["years_to_maturity"] <= 2]

    elif horizon == "1-3 Tahun":
        return df[df["years_to_maturity"] <= 5]

    elif horizon == "3-5 Tahun":
        return df[df["years_to_maturity"] <= 10]

    else:
        return df


def select_bonds(df):

    df = df.copy()

    df["score"] = df["real_yield"] / (df["years_to_maturity"] + 1)

    return df.sort_values("score", ascending=False).head(3)


# --- RISK ENGINE ---


def calculate_risk_score(drawdown, horizon, liquidity):

    score = 0

    if drawdown == "Sell semuanya":
        score += 1

    elif drawdown == "Tunggu":
        score += 2

    elif drawdown == "Beli lebih banyak":
        score += 3

    if horizon == "5+ Tahun":
        score += 2

    if liquidity == "Butuh uang dalam waktu dekat":
        score -= 1

    return score


def allocation_from_risk(score):

    if score <= 2:
        return 0.25, 0.75

    elif score <= 4:
        return 0.5, 0.5

    else:
        return 0.75, 0.25


# --- STOCK FILTER ---


def select_stocks(df):

    df = df[
        (df["payout_ratio"] < 85) &
        (df["dividend_yield"] > 3) &
        (df["pe_ratio"] < 20)
    ].copy()

    df["score"] = (
        df["dividend_yield"] * 0.45 +
        (1 / df["pe_ratio"]) * 0.25 +
        (1 - df["payout_ratio"] / 100) * 0.2
    )

    return df.sort_values("score", ascending=False).head(5)


# --- PORTFOLIO SIMULATION ---


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


# --- PURCHASE PLAN ---


def build_purchase_plan(simulation, stocks, bonds):

    stock_capital = simulation["stock_capital"]
    bond_capital = simulation["bond_capital"]

    stock_budget_each = stock_capital / len(stocks)

    stock_plan = []

    for _, row in stocks.iterrows():

        price = row["previous_close"]

        lot_price = price * 100

        lots = int(stock_budget_each / lot_price)

        shares = lots * 100

        total = shares * price

        stock_plan.append({
            "Ticker": row["ticker"],
            "Harga per Saham": price,
            "Jumlah Lot": lots,
            "Jumlah Saham": shares,
            "Total Dana": total
        })

    stock_plan = pd.DataFrame(stock_plan)

    bond_budget_each = bond_capital / len(bonds)

    bond_plan = []

    for _, row in bonds.iterrows():

        price = row["price"]

        units = int(bond_budget_each / price)

        total = units * price

        bond_plan.append({
            "Obligasi": row["ticker"],
            "Harga": price,
            "Unit": units,
            "Total Dana": total
        })

    bond_plan = pd.DataFrame(bond_plan)

    return stock_plan, bond_plan


# --- AI EXPLANATION ---


def run_groq_simulation(profile, stocks, bonds, simulation):

    prompt = f"""
Saya adalah orang awam yang ingin melakukan investasi. Jelaskan strategi investasi berikut dalam bahasa Indonesia kepada saya.

PROFIL INVESTOR
Modal: Rp {profile['budget']:,.0f}
Tujuan: {profile['priority']}
Horizon: {profile['horizon']}
Likuiditas: {profile['liquidity']}

SAHAM TERPILIH
{stocks[['ticker','dividend_yield','pe_ratio']].to_string(index=False)}

OBLIGASI TERPILIH
{bonds[['ticker','real_yield','years_to_maturity']].to_string(index=False)}

SIMULASI
Pendapatan tahunan: Rp {simulation['total_income']:,.0f}
Pendapatan bulanan: Rp {simulation['monthly_income']:,.0f}
Worst case portfolio: Rp {simulation['worst_case']:,.0f}
"""

    completion = groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.2
    )

    return completion.choices[0].message.content


# --- UI ---


st.set_page_config(page_title="IHSG Dividend Master", layout="wide")

st.title("IHSG Smart Portfolio Advisor")


with st.form("advisor"):

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
            "Jika portofolio turun 30%",
            [
                "Sell semuanya",
                "Tunggu",
                "Beli lebih banyak"
            ]
        )

    u_liquidity = st.selectbox(
        "Kebutuhan Likuiditas",
        [
            "Tidak butuh uang dalam waktu dekat",
            "Butuh uang dalam 1-2 tahun",
            "Butuh uang dalam waktu dekat"
        ]
    )

    submit = st.form_submit_button("Generate Portfolio")


if submit:

    profile = {
        "budget": u_budget,
        "priority": u_priority,
        "horizon": u_horizon,
        "liquidity": u_liquidity
    }

    risk_score = calculate_risk_score(u_drawdown, u_horizon, u_liquidity)

    stock_pct, bond_pct = allocation_from_risk(risk_score)

    df_bonds = load_bonds_data()

    filtered_bonds = filter_bonds_by_horizon(df_bonds, u_horizon)

    bonds = select_bonds(filtered_bonds)

    res = supabase.table("master_schedule")\
        .select("*")\
        .not_.is_("dividend_yield", "null")\
        .limit(200)\
        .execute()

    df_stocks = pd.DataFrame(res.data)

    top_stocks = select_stocks(df_stocks)

    simulation = simulate_portfolio(
        u_budget,
        stock_pct,
        bond_pct,
        top_stocks,
        bonds
    )

    stock_plan, bond_plan = build_purchase_plan(
        simulation,
        top_stocks,
        bonds
    )

    st.subheader("Alokasi Portofolio")

    st.write(f"Saham: {stock_pct*100:.0f}%")
    st.write(f"Obligasi: {bond_pct*100:.0f}%")

    st.subheader("Rencana Pembelian Saham")

    st.dataframe(stock_plan, use_container_width=True)

    st.subheader("Rencana Pembelian Obligasi")

    st.dataframe(bond_plan, use_container_width=True)

    st.subheader("Estimasi Passive Income")

    st.write(f"Pendapatan Tahunan: Rp {simulation['total_income']:,.0f}")
    st.write(f"Pendapatan Bulanan: Rp {simulation['monthly_income']:,.0f}")

    st.subheader("Skenario Risiko")

    st.write(f"Nilai terburuk portofolio: Rp {simulation['worst_case']:,.0f}")

    with st.spinner("AI Advisor menganalisis..."):

        explanation = run_groq_simulation(
            profile,
            top_stocks,
            bonds,
            simulation
        )

    st.markdown(explanation)
