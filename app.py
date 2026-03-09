import streamlit as st
import pandas as pd
import yfinance as yf
from supabase import create_client, Client
import time
import os

# --- SETUP ---
# Ensure your secrets are configured in .streamlit/secrets.toml
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

def load_tickers_from_excel():
    """Reads the Excel file provided. Ensure the file is in the same folder."""
    # Using the specific filename/path from your setup
    file_name = "Daftar Saham  - 20260306.xlsx" 
    if not os.path.exists(file_name):
        # Fallback to absolute path if relative fails
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

def get_pending_price_tasks():
    """
    FIX: Specifically finds tickers that EXIST in the DB 
    but have NULL prices or NULL yields.
    """
    try:
        # We look for rows where the price is missing OR the yield is missing
        res = supabase.table("master_schedule").select("ticker") \
            .or_("previous_close.is.null,dividend_yield.is.null").execute()
        return [row['ticker'] for row in res.data]
    except Exception as e:
        st.sidebar.error(f"Filter Error: {e}")
        return []

# --- UI SETUP ---
st.set_page_config(page_title="IHSG Yield Master", layout="wide")
st.title("🏆 IHSG Dividend Master (2026 Edition)")

# --- 1. SEARCH SECTION (Live Ratio) ---
st.subheader("🔍 Live 2026 Ratio Search")
search_ticker = st.text_input("Search Ticker (e.g. ITMG, BBCA):", "").upper()

if search_ticker:
    t_jk = f"{search_ticker}.JK" if not search_ticker.endswith(".JK") else search_ticker
    res = supabase.table("master_schedule").select("*").eq("ticker", t_jk).execute()
    
    if res.data:
        stock_data = res.data[0]
        with st.spinner(f"Fetching live data for {t_jk}..."):
            # Using fast_info for the absolute latest price
            ticker_obj = yf.Ticker(t_jk)
            live_price = ticker_obj.fast_info['last_price']
            div_val = stock_data['total_dividend_2025']
            live_ratio = (div_val / live_price * 100) if live_price > 0 else 0
            
            s1, s2, s3 = st.columns(3)
            s1.metric("2025 Total Dividend", f"Rp {div_val}")
            s2.metric("Today's Price", f"Rp {live_price:,.0f}")
            s3.metric("Current Yield Ratio", f"{live_ratio:.2f}%")
    else:
        st.warning(f"Ticker {t_jk} not found in database. Please mine it first.")

st.divider()

# --- 2. SIDEBAR (Mining & Price Updates) ---
all_ihsg = load_tickers_from_excel()
pending_prices = get_pending_price_tasks()

with st.sidebar:
    st.header("📊 Database Status")
    st.write(f"Total Tickers: **{len(all_ihsg)}**")
    st.write(f"Missing Price/Yield: **{len(pending_prices)}**")
    
    st.divider()
    st.subheader("Action Center")
    
    # THE PRICE COLLECTOR BUTTON (1-HOUR INTERVAL)
    if st.button("🚀 Fill Empty Prices (Batch 200)"):
        if not pending_prices:
            st.success("All data is already filled!")
        else:
            batch = pending_prices[:200]
            st.info(f"Updating {len(batch)} stocks with 1-Hour Price data...")
            p_bar = st.progress(0)
            status_text = st.empty()
            
            for i, ticker in enumerate(batch):
                try:
                    status_text.text(f"Processing: {ticker}")
                    stock = yf.Ticker(ticker)
                    
                    # Fetching 1-hour interval for "Last Hour Price" accuracy
                    hist = stock.history(period="1d", interval="1h")
                    
                    if not hist.empty:
                        recent_price = hist['Close'].iloc[-1]
                        
                        # Get the dividend from DB to calculate the yield
                        db_row = supabase.table("master_schedule").select("total_dividend_2025").eq("ticker", ticker).execute()
                        div_2025 = db_row.data[0]['total_dividend_2025']
                        
                        calc_yield = (div_2025 / recent_price * 100) if recent_price > 0 else 0
                        
                        # Update the record in the Master Vault
                        supabase.table("master_schedule").update({
                            "previous_close": float(recent_price),
                            "dividend_yield": round(float(calc_yield), 2),
                            "last_mined": "now()"
                        }).eq("ticker", ticker).execute()
                    
                    p_bar.progress((i + 1) / len(batch))
                    time.sleep(0.1) # Fast processing
                except Exception as e:
                    continue
            
            st.success("Batch Complete!")
            st.rerun()

# --- 3. MAIN DASHBOARD (Yield Leaderboard) ---
st.subheader("🔥 Top Dividend Yields (Sorted by Last Hour Price)")

# Query only rows that have a calculated yield
view_res = supabase.table("master_schedule").select("*").not_.is_("dividend_yield", "null").order("dividend_yield", desc=True).limit(50).execute()

if view_res.data:
    df = pd.DataFrame(view_res.data)
    
    # Filter and format columns for display
    df_display = df[["ticker", "company_name", "total_dividend_2025", "previous_close", "dividend_yield", "last_mined"]]
    
    st.dataframe(
        df_display,
        use_container_width=True,
        column_config={
            "total_dividend_2025": "Total Div 2025 (Rp)",
            "previous_close": "Last Hour Price (Rp)",
            "dividend_yield": st.column_config.NumberColumn("Yield Rate", format="%.2f%%"),
            "last_mined": st.column_config.DatetimeColumn("Data Updated At")
        }
    )
    
    st.write("---")
    st.write("💡 *The 'Last Hour Price' reflects the most recently completed trading hour.*")
    if st.button("🔄 Refresh Leaderboard"):
        st.rerun()
else:
    st.info("No yield data found. Please use the sidebar to 'Fill Empty Prices' for your mined dividends.")
