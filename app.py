import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

st.set_page_config(page_title="All IHSG Dividend Analyzer", layout="wide")

st.title("🇮🇩 All IHSG Stock Dividend & Cluster Analyzer")
st.write("Analyzing dividend yields across the entire Indonesia Stock Exchange.")

# 1. Fetch all IHSG Tickers
@st.cache_data
def get_all_ihsg_tickers():
    # Fetching a community-maintained list of IDX tickers
    # This URL points to a reliable raw list of all .JK tickers
    url = "https://raw.githubusercontent.com/baguskto/saham-mcp/master/data/ticker_list.csv"
    try:
        df_tickers = pd.read_csv(url)
        # Assuming the CSV has a column for ticker codes
        return [f"{code}.JK" for code in df_tickers['code'].tolist()]
    except:
        # Fallback list if the URL fails
        return ['ANTM.JK', 'BBRI.JK', 'BMRI.JK', 'ASII.JK', 'TLKM.JK', 'UNVR.JK']

all_tickers = get_all_ihsg_tickers()

# 2. Sidebar Filters
st.sidebar.header("Global Filters")
min_yield = st.sidebar.slider("Min Dividend Yield (%)", 0.0, 15.0, 3.0)
target_stock = st.sidebar.text_input("🔍 Search Stock (e.g. BBCA)", "").upper()

# 3. Data Fetching (Optimized)
@st.cache_data
def fetch_dividend_performance(ticker_list):
    # Note: Fetching 900+ stocks one by one is slow. 
    # In a real app, we batch this or use a pre-scraped database.
    # For this demo, we'll limit to the top 100 or user selection.
    results = []
    # Progress bar for large data
    pbar = st.progress(0)
    
    # We use a smaller subset for speed in this example, 
    # but you can remove the [:50] to run the whole market
    subset = ticker_list[:100] 
    
    for i, ticker in enumerate(subset):
        try:
            stock = yf.Ticker(ticker)
            # Get 2025 Dividends
            divs = stock.dividends
            total_div = divs.loc['2025-01-01':'2025-12-31'].sum() if not divs.empty else 0
            
            # Get Current Price
            price = stock.fast_info['last_price']
            div_yield = (total_div / price * 100) if price > 0 else 0
            
            results.append({
                "Ticker": ticker.replace(".JK", ""),
                "Price": price,
                "Total Div 2025": total_div,
                "Yield %": round(div_yield, 2)
            })
        except:
            continue
        pbar.progress((i + 1) / len(subset))
    
    pbar.empty()
    return pd.DataFrame(results)

# --- EXECUTION ---
with st.spinner("Fetching Market Data..."):
    df = fetch_dividend_performance(all_tickers)

if not df.empty:
    # 4. Machine Learning (K-Means Clustering)
    # We cluster based on Yield % to find "Yield Tiers"
    X = df[['Yield %']].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    kmeans = KMeans(n_clusters=3, random_state=42)
    df['Cluster'] = kmeans.fit_predict(X_scaled)
    
    # Sort labels so Cluster 0 is always Low and Cluster 2 is High
    order = df.groupby('Cluster')['Yield %'].mean().sort_values().index
    mapping = {order[0]: "Low/Growth", order[1]: "Medium", order[2]: "High Yield"}
    df['Tier'] = df['Cluster'].map(mapping)

    # 5. Dashboard
    col1, col2, col3 = st.columns(3)
    
    top_stock = df.loc[df['Yield %'].idxmax()]
    col1.metric("Highest Payer", top_stock['Ticker'], f"{top_stock['Yield %']}%")
    col2.metric("Market Avg Yield", f"{round(df['Yield %'].mean(), 2)}%")
    col3.metric("Analyzed Stocks", len(df))

    # Search Logic
    if target_stock:
        display_df = df[df['Ticker'] == target_stock]
        if display_df.empty:
            st.warning(f"Stock {target_stock} not found in current batch.")
        else:
            st.success(f"Found {target_stock}: Yield is {display_df['Yield %'].values[0]}%")
    
    # Filtered View
    st.subheader(f"Stocks with > {min_yield}% Yield")
    filtered = df[df['Yield %'] >= min_yield].sort_values("Yield %", ascending=False)
    st.dataframe(filtered, use_container_width=True)

    # Cluster Visual
    st.subheader("Yield Tier Distribution")
    st.bar_chart(df['Tier'].value_counts())
else:
    st.error("Could not load market data.")
