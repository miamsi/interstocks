import streamlit as st
import yfinance as yf
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.linear_model import LinearRegression

st.set_page_config(page_title="Stock Relationship Analyzer", layout="wide")

st.title("📈 Stock Portfolio Relationship & ML Analyzer")
st.write("Analyzing: **ANTM, BBRI, CTRA, JSMR, PNBN, TAPG**")

# 1. Sidebar Settings
st.sidebar.header("Settings")
period = st.sidebar.selectbox("Select Time Period", ["1y", "2y", "5y", "ytd"], index=0)
clusters_n = st.sidebar.slider("Number of ML Clusters", 2, 4, 3)

# 2. Data Fetching
tickers = ['ANTM.JK', 'BBRI.JK', 'CTRA.JK', 'JSMR.JK', 'PNBN.JK', 'TAPG.JK']

@st.cache_data
def get_data(ticker_list, p):
    df = yf.download(ticker_list, period=p)['Close']
    return df

data = get_data(tickers, period)
returns = data.pct_change().dropna()

# --- TABBED LAYOUT ---
tab1, tab2, tab3 = st.tabs(["Price History", "Correlation Heatmap", "ML Clustering"])

with tab1:
    st.subheader("Normalized Price Movement (Base 100)")
    # Normalize to 100 to compare different price scales
    normalized_df = (data / data.iloc[0] * 100)
    st.line_chart(normalized_df)

with tab2:
    st.subheader("Inter-Stock Correlation")
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.heatmap(returns.corr(), annot=True, cmap='RdYlGn', center=0, ax=ax)
    st.pyplot(fig)
    st.info("Values close to 1.0 mean the stocks move in lockstep. Values near 0 mean they are independent.")

with tab3:
    st.subheader("Machine Learning: K-Means Clustering")
    
    # Scale data for ML
    scaler = StandardScaler()
    scaled_returns = scaler.fit_transform(returns.T) # Cluster the stocks
    
    # Run K-Means
    kmeans = KMeans(n_clusters=clusters_n, random_state=42)
    clusters = kmeans.fit_predict(scaled_returns)
    
    results = pd.DataFrame({'Stock': tickers, 'Cluster': clusters}).sort_values('Cluster')
    
    col1, col2 = st.columns(2)
    with col1:
        st.dataframe(results, use_container_width=True)
    with col2:
        st.write("**What this means:**")
        st.write("Stocks in the same cluster behave similarly based on daily returns math, regardless of their industry sector.")

# --- RELATIONSHIP PREDICTOR ---
st.divider()
st.subheader("Stock Influence Predictor (Linear Regression)")
col_a, col_b = st.columns(2)

with col_a:
    stock_x = st.selectbox("If this stock moves...", tickers, index=1) # Default BBRI
with col_b:
    stock_y = st.selectbox("...how much does this one move?", tickers, index=2) # Default CTRA

# Run simple regression
X = returns[[stock_x]].values
y = returns[stock_y].values
model = LinearRegression().fit(X, y)
beta = model.coef_[0]

st.metric(label=f"Influence Factor (Beta)", value=f"{beta:.2f}")
st.write(f"Statistical Result: For every **1%** move in {stock_x}, {stock_y} typically moves **{beta:.2f}%**.")
