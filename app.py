# ================================
# SMART PORTFOLIO ADVISOR
# Single File Streamlit Application
# ================================

import streamlit as st
import pandas as pd
import numpy as np
import json
from groq import Groq
from supabase import create_client

# -------------------------------
# CONFIG
# -------------------------------

st.set_page_config(page_title="Smart Portfolio Advisor", layout="wide")

GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

groq_client = Groq(api_key=GROQ_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------------
# LOAD DATA
# -------------------------------

@st.cache_data
def load_bonds():
    df = pd.read_csv("bonds.csv")
    return df

@st.cache_data
def load_stocks():
    res = supabase.table("stocks").select("*").execute()
    df = pd.DataFrame(res.data)
    return df

bond_df = load_bonds()
stock_df = load_stocks()

# -------------------------------
# DATASET DESCRIPTION
# -------------------------------

DATA_DESCRIPTION = """
Stock dataset fields:

ticker
sector
price
dividend_yield
pe_ratio
payout_ratio
label
cluster

Label meaning:
High Dividend = income oriented
Growth = expansion companies
Defensive = stable sectors
Cyclical = commodity driven

Cluster meaning:
Income Cluster
Balanced Cluster
Growth Cluster
Speculative Cluster

Bond dataset fields:

bond_name
yield
price
maturity_date
duration
"""

# -------------------------------
# AI INTERPRET INVESTOR
# -------------------------------

def interpret_investor(profile):

    prompt = f"""
Investor profile:
{profile}

Dataset structure:
{DATA_DESCRIPTION}

Decide:

1 investor style
2 suitable stock clusters
3 bond preference
4 stock bond allocation

Return JSON:

{{
"investor_style":"",
"stock_clusters":[],
"bond_preference":"",
"stock_allocation":0,
"bond_allocation":0
}}
"""

    chat = groq_client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role":"user","content":prompt}],
        temperature=0.3
    )

    return json.loads(chat.choices[0].message.content)

# -------------------------------
# FILTER STOCKS
# -------------------------------

def get_stock_candidates(clusters):

    df = stock_df.copy()

    df = df[df["cluster"].isin(clusters)]

    df = df.sort_values(
        by=["dividend_yield","pe_ratio"],
        ascending=[False,True]
    )

    return df.head(20)

# -------------------------------
# FILTER BONDS
# -------------------------------

def get_bond_candidates(pref):

    df = bond_df.copy()

    if "short" in pref.lower():
        df = df[df["duration"] <= 3]

    if "high" in pref.lower():
        df = df[df["yield"] >= df["yield"].median()]

    df = df.sort_values("yield",ascending=False)

    return df.head(10)

# -------------------------------
# AI BUILD PORTFOLIO
# -------------------------------

def build_portfolio(profile,stocks,bonds,capital):

    prompt = f"""
Investor profile:
{profile}

Capital:
{capital}

Stock candidates:
{stocks.to_json()}

Bond candidates:
{bonds.to_json()}

Rules:

Stocks must follow IHSG rule:
1 lot = 100 shares

Total spending must not exceed capital.

Return JSON:

{{
"stocks":[{{"ticker":"","lots":0}}],
"bonds":[{{"bond_name":"","amount":0}}],
"expected_return":"",
"risk_level":"",
"narrative":""
}}
"""

    chat = groq_client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role":"user","content":prompt}],
        temperature=0.5
    )

    return json.loads(chat.choices[0].message.content)

# -------------------------------
# USER INTERFACE
# -------------------------------

st.title("Smart Portfolio Advisor")

capital = st.number_input("Total Dana Investasi", value=30000000)

goal = st.selectbox(
"Tujuan Investasi",
["Passive Income","Growth","Balanced"]
)

horizon = st.selectbox(
"Jangka Waktu",
["<1 Tahun","1-3 Tahun","3-5 Tahun",">5 Tahun"]
)

reaction = st.selectbox(
"Jika Portfolio Turun 30%",
["Jual","Tunggu","Beli Lagi"]
)

concern = st.text_area("Kekhawatiran Utama")

# -------------------------------
# GENERATE STRATEGY
# -------------------------------

if st.button("Generate Strategy"):

    profile = f"""
    capital: {capital}
    goal: {goal}
    horizon: {horizon}
    reaction: {reaction}
    concern: {concern}
    """

    with st.spinner("AI analyzing investor profile..."):

        strategy = interpret_investor(profile)

        stocks = get_stock_candidates(strategy["stock_clusters"])

        bonds = get_bond_candidates(strategy["bond_preference"])

        portfolio = build_portfolio(profile,stocks,bonds,capital)

    st.subheader("Alokasi Portfolio")

    st.write("Saham:",strategy["stock_allocation"],"%")
    st.write("Obligasi:",strategy["bond_allocation"],"%")

    st.subheader("Rekomendasi Saham")

    for s in portfolio["stocks"]:
        st.write(
            "Ticker:", s["ticker"],
            "| Lot:", s["lots"],
            "| Shares:", s["lots"]*100
        )

    st.subheader("Rekomendasi Obligasi")

    for b in portfolio["bonds"]:
        st.write(
            "Bond:", b["bond_name"],
            "| Jumlah:", b["amount"]
        )

    st.subheader("Ekspektasi Return")
    st.write(portfolio["expected_return"])

    st.subheader("Penjelasan Strategi")
    st.write(portfolio["narrative"])
