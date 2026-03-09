import streamlit as st
import pandas as pd
import yfinance as yf
from supabase import create_client, Client
import time
import os
from datetime import datetime

# --- SETUP ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

def load_tickers_from_excel():
    file_name = "Daftar Saham  - 20260306.xlsx" 
    if not os.path.exists(file_name):
        file_name = r"C:\Users\michael.sidabutar\Documents\stock mining\Daftar Saham  - 20260306.xlsx"
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

def get_oldest_price_batch(batch_size=1000):
    """
    Logic: Pulls the stocks that haven't been updated for the longest time.
    This creates a rotation so every stock eventually gets the 'Last Hour' price.
    """
    try:
        # Sort by last_mined ascending (Oldest first)
        res = supabase.table("master_schedule") \
            .select("ticker") \
            .order("last_mined", desc=False) \
            .limit(batch_size) \
            .execute()
        return [row['ticker'] for row in res.data]
    except Exception as e:
        st.sidebar.error(f"Queue Error: {e}")
        return []

# --- UI SETUP ---
st.set_page_config(page_title="IHSG Yield Master", layout="wide")
st.title("🏆 IHSG Dividend Master (Last Hour Price Edition)")

# --- 1. SEARCH SECTION (Live Ratio) ---
st.subheader("🔍 Live 2026 Ratio Search")
search_ticker = st.text_input("Search Ticker (e.g. ITMG, BBCA):", "").upper()

if search_ticker:
    t_jk = f"{search_ticker}.JK" if not search_ticker.endswith(".JK") else search_ticker
    res = supabase.table("master_schedule").select("*").eq("ticker", t_jk).execute()
    
    if res.data:
        stock_data = res.data[0]
        with st.spinner(f"Fetching live data for {t_jk}..."):
            ticker_obj = yf.Ticker(t_jk)
            live_price = ticker_obj.fast_info['last_price']
            div_val = stock_data['total_dividend_2025']
            live_ratio = (div_val / live_price * 100) if live_price > 0 else 0
            
            s1, s2, s3 = st.columns(3)
            s1.metric("2025 Total Dividend", f"Rp {div_val}")
            s2.metric("Today's Price", f"Rp {live_price:,.0f}")
            s3.metric("Current Yield Ratio", f"{live_ratio:.2f}%")
    else:
        st.warning(f"Ticker {t_jk} not found in database.")

st.divider()

# --- 2. SIDEBAR (The Batch Rotation Engine) ---
all_ihsg = load_tickers_from_excel()
# Get the next batch of 200 based on who is 'oldest' in the database
update_queue = get_oldest_price_batch(200)

with st.sidebar:
    st.header("📊 Mining Engine")
    st.write(f"Total Tickers: **{len(all_ihsg)}**")
    
    st.divider()
    st.subheader("Action Center")
    st.write("This button updates the **oldest 200** records to the current Last Hour Price.")
    
    if st.button("🚀 Update Next Batch (200)"):
        if not update_queue:
            st.error("No stocks found in database to update.")
        else:
            p_bar = st.progress(0)
            status_text = st.empty()
            
            for i, ticker in enumerate(update_queue):
                try:
                    status_text.text(f"Updating [{i+1}/200]: {ticker}")
                    stock = yf.Ticker(ticker)
                    
                    # Last 1-hour price
                    hist = stock.history(period="1d", interval="1h")
                    
                    if not hist.empty:
                        recent_price = hist['Close'].iloc[-1]
                        
                        # Get existing dividend
                        db_row = supabase.table("master_schedule").select("total_dividend_2025").eq("ticker", ticker).execute()
                        div_2025 = db_row.data[0]['total_dividend_2025']
                        
                        calc_yield = (div_2025 / recent_price * 100) if recent_price > 0 else 0
                        
                        # Update timestamp to NOW so it moves to the 'back of the line'
                        supabase.table("master_schedule").update({
                            "previous_close": float(recent_price),
                            "dividend_yield": round(float(calc_yield), 2),
                            "last_mined": datetime.now().isoformat()
                        }).eq("ticker", ticker).execute()
                    
                    p_bar.progress((i + 1) / len(update_queue))
                    time.sleep(0.05) # Optimized speed
                except Exception:
                    continue
            
            st.success("Batch finished! These 200 are now at the back of the queue.")
            st.rerun()

# --- 3. MAIN DASHBOARD ---
st.subheader("🔥 Top Dividend Yields (Sorted by Recently Mined Price)")

# Show the leaderboard
view_res = supabase.table("master_schedule").select("*").not_.is_("dividend_yield", "null").order("dividend_yield", desc=True).limit(50).execute()

if view_res.data:
    df = pd.DataFrame(view_res.data)
    df_display = df[["ticker", "company_name", "total_dividend_2025", "previous_close", "dividend_yield", "last_mined"]]
    
    st.dataframe(
        df_display,
        use_container_width=True,
        column_config={
            "total_dividend_2025": "Total Div 2025 (Rp)",
            "previous_close": "Last Hour Price (Rp)",
            "dividend_yield": st.column_config.NumberColumn("Yield Rate", format="%.2f%%"),
            "last_mined": st.column_config.DatetimeColumn("Price Timestamp")
        }
    )
    
    if st.button("🔄 Refresh Dashboard View"):
        st.rerun()
