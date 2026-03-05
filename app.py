import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

st.set_page_config(page_title="IHSG Hidden Gem Miner", layout="wide")

st.title("⛏️ IHSG Dividend Miner")
st.write("Scanning the entire market to find hidden high-yield stocks.")

# 1. DYNAMIC TICKER LOADER (Scans all ~900+ IDX Stocks)
@st.cache_data
def get_all_idx_tickers():
    # Pulling from a reliable community list of all active IDX tickers
    url = "https://raw.githubusercontent.com/baguskto/saham-mcp/master/data/ticker_list.csv"
    try:
        df_raw = pd.read_csv(url)
        # Ensure the .JK suffix is added for Yahoo Finance
        return [f"{row['code']}.JK" for _, row in df_raw.iterrows()]
    except:
        st.error("Failed to fetch full ticker list. Falling back to a partial list.")
        return ["ADRO.JK", "ITMG.JK", "PTBA.JK", "BBRI.JK", "TAPG.JK", "JSMR.JK"]

all_tickers = get_all_idx_tickers()

# 2. THE MINING ENGINE
@st.cache_data
def mine_dividends(ticker_list):
    results = []
    one_year_ago = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
    
    # Batch processing to prevent timeout
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # NOTE: To scan ALL 900+ stocks, remove the [:100] limit. 
    # For initial testing, we use a subset to keep it fast.
    subset = ticker_list 
    
    for i, ticker in enumerate(subset):
        try:
            status_text.text(f"Mining {ticker} ({i+1}/{len(subset)})...")
            stock = yf.Ticker(ticker)
            
            # Fetch TTM Dividends
            divs = stock.dividends
            ttm_div = divs[divs.index >= one_year_ago].sum()
            
            # Get Price & Info
            price = stock.fast_info['last_price']
            yield_val = (ttm_div / price * 100) if price > 0 else 0
            
            # We only keep stocks that have a yield > 0 to save memory
            if yield_val > 0:
                results.append({
                    "Ticker": ticker.replace(".JK", ""),
                    "Price": round(price, 2),
                    "TTM Div": round(ttm_div, 2),
                    "Yield %": round(yield_val, 2)
                })
        except:
            continue
        progress_bar.progress((i + 1) / len(subset))
    
    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(results)

# --- APP INTERFACE ---
if st.button("🚀 Start Deep Market Scan"):
    df = mine_dividends(all_tickers)
    st.session_state['mined_data'] = df
else:
    df = st.session_state.get('mined_data', pd.DataFrame())

if not df.empty:
    # 3. FILTERS & SEARCH
    st.sidebar.header("Miner Settings")
    min_yield = st.sidebar.number_input("Min Yield %", value=5.0, step=0.5)
    search = st.sidebar.text_input("🔍 Check Research Stock", "").upper()

    # 4. ML CLUSTERING (Identifying Yield Profiles)
    X = df[['Yield %']].values
    df['Cluster'] = KMeans(n_clusters=3, n_init=10).fit_predict(StandardScaler().fit_transform(X))
    
    # Sort clusters for logical labeling
    means = df.groupby('Cluster')['Yield %'].mean().sort_values()
    labels = {means.index[0]: "Low Yield", means.index[1]: "Mid Yield", means.index[2]: "High Yield"}
    df['Profile'] = df['Cluster'].map(labels)

    # 5. RESULTS DISPLAY
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("💎 Mined Stocks (Hidden Gems)")
        filtered_df = df[df['Yield %'] >= min_yield]
        if search:
            filtered_df = filtered_df[filtered_df['Ticker'].str.contains(search)]
        
        st.dataframe(filtered_df.sort_values("Yield %", ascending=False), use_container_width=True)

    with col2:
        st.subheader("📊 Yield Clusters")
        st.write(f"**Total Payers Found:** {len(df)}")
        st.bar_chart(df['Profile'].value_counts())
        
        # Highlight Top 3 unpopular stocks (High yield, but not blue chips)
        st.write("**Top 'Hidden' Yielders:**")
        st.table(df.sort_values("Yield %", ascending=False).head(5)[['Ticker', 'Yield %']])
else:
    st.info("Click the button above to start scanning the IHSG market for dividends.")
