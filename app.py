import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

st.set_page_config(page_title="Dividend Yield & Cluster Analyzer", layout="wide")

st.title("💰 Dividend Yield & ML Cluster Analyzer")
st.write("Calculate real return ratios and group stocks by dividend behavior.")

# 1. User Input for Tickers
tickers_input = st.text_input("Enter Ticker Symbols (comma separated)", 
                             value="ANTM.JK, BBRI.JK, CTRA.JK, JSMR.JK, PNBN.JK, TAPG.JK")
tickers = [t.strip() for t in tickers_input.split(",")]

# 2. Sidebar Filters
st.sidebar.header("Analysis Filters")
min_yield_input = st.sidebar.number_input("Minimum Dividend Yield (%)", min_value=0.0, value=2.0)
search_query = st.sidebar.text_input("🔍 Search specific stock")

@st.cache_data
def get_dividend_data(ticker_list):
    results = []
    for ticker in ticker_list:
        try:
            stock = yf.Ticker(ticker)
            # Get last year's total dividends
            div_history = stock.dividends
            if not div_history.empty:
                last_year_div = div_history.loc['2025-01-01':'2025-12-31'].sum()
            else:
                last_year_div = 0
            
            # Get current price
            current_price = stock.fast_info['last_price']
            
            # Calculate Yield Ratio
            yield_ratio = (last_year_div / current_price) * 100 if current_price > 0 else 0
            
            results.append({
                "Ticker": ticker,
                "Current Price": round(current_price, 2),
                "Total Div 2025": round(last_year_div, 2),
                "Yield %": round(yield_ratio, 2)
            })
        except Exception:
            continue
    return pd.DataFrame(results)

# --- EXECUTION ---
df = get_dividend_data(tickers)

if not df.empty:
    # 3. Machine Learning: Cluster by Yield
    X = df[['Yield %']].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    kmeans = KMeans(n_clusters=3, random_state=42)
    df['Cluster'] = kmeans.fit_predict(X_scaled)
    
    # Labeling clusters logically by yield height
    cluster_means = df.groupby('Cluster')['Yield %'].mean().sort_values()
    label_map = {cluster_means.index[0]: "Low Yield", 
                 cluster_means.index[1]: "Mid Yield", 
                 cluster_means.index[2]: "High Yield"}
    df['Yield Category'] = df['Cluster'].map(label_map)

    # 4. DASHBOARD HIGHLIGHTS
    col1, col2, col3 = st.columns(3)
    highest_stock = df.loc[df['Yield %'].idxmax()]
    
    col1.metric("Highest Yield Stock", highest_stock['Ticker'], f"{highest_stock['Yield %']}%")
    col2.metric("Avg Portfolio Yield", f"{round(df['Yield %'].mean(), 2)}%")
    col3.metric("Total Dividend Payers", len(df[df['Total Div 2025'] > 0]))

    # 5. USER INTERACTION: Filtering & Searching
    st.divider()
    
    # Filter by user input
    filtered_df = df[df['Yield %'] >= min_yield_input]
    
    # Search functionality
    if search_query:
        filtered_df = filtered_df[filtered_df['Ticker'].str.contains(search_query.upper())]

    st.subheader(f"Results (Min {min_yield_input}% Yield)")
    st.dataframe(filtered_df.sort_values(by="Yield %", ascending=False), use_container_width=True)

    # 6. CLUSTER ANALYSIS SUMMARY
    st.subheader("📊 Yield Cluster Distribution")
    cluster_summary = df['Yield Category'].value_counts().reset_index()
    cluster_summary.columns = ['Category', 'Stock Count']
    st.bar_chart(data=cluster_summary, x='Category', y='Stock Count')

else:
    st.warning("Could not fetch data. Please check your ticker symbols or internet connection.")
