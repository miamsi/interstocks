import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

st.set_page_config(page_title="IHSG Dividend Miner (Hardcoded)", layout="wide")

st.title("⛏️ IHSG Dividend Miner: High-Confidence List")
st.write("Mining 60+ stocks known for consistent dividend history.")

# 1. THE DATA: Pre-vetted high-confidence dividend stocks
@st.cache_data
def get_vetted_tickers():
    return [
        # --- BIG BANKS (Consistent) ---
        "BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "BNGA.JK", "BJBR.JK", "BJTM.JK", "BDMN.JK",
        # --- ENERGY & COAL (High Yield Gems) ---
        "ADRO.JK", "ITMG.JK", "PTBA.JK", "UNTR.JK", "BSSR.JK", "GEMS.JK", "MBAP.JK", "HRUM.JK", "KKGI.JK", "INDY.JK", "PGAS.JK",
        # --- CONSUMER & RETAIL (Reliable) ---
        "UNVR.JK", "HMSP.JK", "GGRM.JK", "ICBP.JK", "INDF.JK", "SIDO.JK", "MYOR.JK", "AMRT.JK", "ACES.JK", "LPPF.JK", "RALS.JK", "MPMX.JK",
        # --- INFRA & LOGISTICS ---
        "TLKM.JK", "JSMR.JK", "ASII.JK", "AKRA.JK", "TPMA.JK", "POWR.JK", "IPCC.JK", "NELY.JK",
        # --- INDUSTRIAL & PROPERTY ---
        "TAPG.JK", "SMGR.JK", "INTP.JK", "CTRA.JK", "PWON.JK", "BSDE.JK", "DMAS.JK", "SMSM.JK", "SPTO.JK", "HEXA.JK",
        # --- MID-CAP GEMS (Unpopular but High Yield) ---
        "CFIN.JK", "MFMI.JK", "PLIN.JK", "CLPI.JK", "GHON.JK", "EAST.JK", "DUTI.JK", "TSPC.JK", "MCOL.JK", "SKLT.JK", "MEGA.JK"
    ]

vetted_list = get_vetted_tickers()

# 2. THE MINING ENGINE (Optimized with TTM Logic)
@st.cache_data
def mine_vetted_data(ticker_list):
    results = []
    one_year_ago = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
    
    with st.status("⛏️ Mining Pre-vetted List...", expanded=True) as status:
        pbar = st.progress(0)
        for i, ticker in enumerate(ticker_list):
            try:
                pbar.progress((i + 1) / len(ticker_list), text=f"Checking {ticker}...")
                stock = yf.Ticker(ticker)
                
                # Fetch Dividends & Price
                divs = stock.dividends
                ttm_div = divs[divs.index >= one_year_ago].sum()
                price = stock.fast_info['last_price']
                
                if price > 0:
                    yield_val = (ttm_div / price * 100)
                    results.append({
                        "Ticker": ticker.replace(".JK", ""),
                        "Price": round(price, 2),
                        "Total Div (TTM)": round(ttm_div, 2),
                        "Yield %": round(yield_val, 2)
                    })
            except: continue
        status.update(label="✅ Mining Complete!", state="complete", expanded=False)
    return pd.DataFrame(results)

# --- EXECUTION ---
df = mine_vetted_data(vetted_list)

if not df.empty:
    # 3. FILTERS & SEARCH
    st.sidebar.header("Miner Settings")
    min_yield = st.sidebar.number_input("Minimum Yield %", value=5.0, step=0.5)
    search = st.sidebar.text_input("🔍 Search Ticker", "").upper()

    # 4. ML CLUSTERING
    X = df[['Yield %']].values
    df['Cluster'] = KMeans(n_clusters=3, n_init=10).fit_predict(StandardScaler().fit_transform(X))
    
    # Label Clusters
    means = df.groupby('Cluster')['Yield %'].mean().sort_values()
    labels = {means.index[0]: "Growth/Low Yield", means.index[1]: "Stable Yield", means.index[2]: "High Yield Gem"}
    df['Profile'] = df['Cluster'].map(labels)

    # 5. DASHBOARD DISPLAY
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("💎 Mined Dividend Results")
        filtered_df = df[df['Yield %'] >= min_yield]
        if search:
            filtered_df = filtered_df[filtered_df['Ticker'].str.contains(search)]
        st.dataframe(filtered_df.sort_values("Yield %", ascending=False), use_container_width=True)

    with col2:
        st.subheader("📊 Cluster Summary")
        counts = df['Profile'].value_counts()
        st.bar_chart(counts)
        for p, c in counts.items():
            st.write(f"**{p}:** {c} stocks")

    st.divider()
    st.write("**Top 5 'Hidden' Yielders from this list:**")
    st.table(df.sort_values("Yield %", ascending=False).head(5)[['Ticker', 'Yield %', 'Profile']])
