import streamlit as st
import pandas as pd
import yfinance as yf
from supabase import create_client, Client
import time
import os

# --- SETUP ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

def load_tickers_from_excel():
    """Reads the Excel file provided. Ensure the file is in the same folder."""
    file_name = "Daftar Saham  - 20260306.xlsx" 
    if not os.path.exists(file_name):
        st.error(f"❌ File not found: {file_name}")
        return []
    try:
        df = pd.read_excel(file_name)
        tickers = df['Kode'].dropna().astype(str).tolist()
        return [f"{t}.JK" for t in tickers if len(t) == 4]
    except Exception as e:
        st.error(f"❌ Error reading Excel: {e}")
        return []

def get_pending_price_tasks():
    """Finds tickers that have dividend data but are missing the yield/price."""
    try:
        # Target rows where we have dividends but haven't fetched yesterday's price yet
        res = supabase.table("master_schedule").select("ticker").is_("previous_close", "null").execute()
        return [row['ticker'] for row in res.data]
    except:
        return []

# --- UI ---
st.set_page_config(page_title="IHSG Yield Master", layout="wide")
st.title("🏆 IHSG Dividend Master (2026 Edition)")

# 1. SEARCH SECTION (Ratio to Today's Price)
st.subheader("🔍 Live 2026 Ratio Search")
search_ticker = st.text_input("Search Ticker (e.g. ITMG, BBCA):", "").upper()
if search_ticker:
    t_jk = f"{search_ticker}.JK" if not search_ticker.endswith(".JK") else search_ticker
    res = supabase.table("master_schedule").select("*").eq("ticker", t_jk).execute()
    if res.data:
        stock_data = res.data[0]
        with st.spinner(f"Fetching live data for {t_jk}..."):
            live_price = yf.Ticker(t_jk).fast_info['last_price']
            div_val = stock_data['total_dividend_2025']
            live_ratio = (div_val / live_price * 100) if live_price > 0 else 0
            
            s1, s2, s3 = st.columns(3)
            s1.metric("2025 Dividend", f"Rp {div_val}")
            s2.metric("Today's Price", f"Rp {live_price:,.0f}")
            s3.metric("Current Yield Ratio", f"{live_ratio:.2f}%")
    else:
        st.warning("Ticker not found in database. Please mine it first.")

st.divider()

# 2. SIDEBAR (Mining Controls)
all_ihsg = load_tickers_from_excel()
pending_prices = get_pending_price_tasks()

with st.sidebar:
    st.header("📊 Database Status")
    st.write(f"Total Tickers: **{len(all_ihsg)}**")
    st.write(f"Missing Yield Data: **{len(pending_prices)}**")
    
    st.divider()
    st.subheader("Action Center")
    # THE PRICE COLLECTOR BUTTON (BATCH 200)
    if st.button("🚀 Collect Yesterday's Prices (Batch 200)"):
        batch = pending_prices[:200]
        st.info(f"Updating prices for {len(batch)} stocks...")
        p_bar = st.progress(0)
        
        for i, ticker in enumerate(batch):
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period="1h")
                if not hist.empty:
                    prev_close = hist['Close'].iloc[-1]
                    
                    # Fetch current div from DB to calc yield
                    db_row = supabase.table("master_schedule").select("total_dividend_2025").eq("ticker", ticker).execute()
                    div_2025 = db_row.data[0]['total_dividend_2025']
                    calc_yield = (div_2025 / prev_close * 100) if prev_close > 0 else 0
                    
                    supabase.table("master_schedule").update({
                        "previous_close": float(prev_close),
                        "dividend_yield": round(float(calc_yield), 2),
                        "last_mined": "now()"
                    }).eq("ticker", ticker).execute()
                
                p_bar.progress((i + 1) / len(batch))
                time.sleep(0.2)
            except:
                continue
        st.rerun()

# 3. MAIN DASHBOARD (Top Percentage)
st.subheader("🔥 Top Dividend Yields (Sorted by Yesterday's Close)")

view_res = supabase.table("master_schedule").select("*").not_.is_("dividend_yield", "null").order("dividend_yield", desc=True).limit(50).execute()

if view_res.data:
    df = pd.DataFrame(view_res.data)
    # Formatting for Dashboard
    df_display = df[["ticker", "company_name", "total_dividend_2025", "previous_close", "dividend_yield", "last_mined"]]
    
    st.dataframe(
        df_display,
        use_container_width=True,
        column_config={
            "total_dividend_2025": "Total Div 2025 (Rp)",
            "previous_close": "Yesterday's Price (Rp)",
            "dividend_yield": st.column_config.NumberColumn("Yield Rate", format="%.2f%%"),
            "last_mined": st.column_config.DatetimeColumn("Price Updated At")
        }
    )
    
    # INDIVIDUAL LIVE UPDATER
    st.write("---")
    st.write("💡 *Use the 'Live Ratio Search' above or click below to refresh the leaderboard.*")
    if st.button("🔄 Refresh Dashboard"):
        st.rerun()
else:

    st.info("No yield data found. Please use the sidebar to 'Collect Yesterday's Prices'.")

