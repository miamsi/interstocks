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
    try:
        res = supabase.table("master_schedule") \
            .select("ticker") \
            .order("last_mined", desc=False) \
            .limit(batch_size) \
            .execute()
        return [row['ticker'] for row in res.data]
    except Exception as e:
        st.sidebar.error(f"Queue Error: {e}")
        return []

def get_stock_label(yield_val, pe, payout):
    """Categorizes the stock based on Value and Safety metrics with robust NaN handling."""
    
    # 1. Check for missing or zero yield
    if pd.isna(yield_val) or yield_val <= 0:
        return "⚪ No Data"
    
    # 2. CRITICAL FIX: Robust check for missing Safety Data (ACRO Fix)
    # Using pd.isna() ensures that 'None' and 'NaN' are both caught.
    if pd.isna(pe) or pd.isna(payout) or pe == 0 or payout <= 0:
        return "🌀 Speculative (Data Gap)"
    
    # 3. Dividend Trap (Payout too high - e.g., PTBA/DMAS)
    if payout > 95:
        return "🚨 Yield Trap (Unsustainable)"
    
    # 4. Dividend King (The target: High yield + Low price + Safe payout)
    if yield_val > 7 and pe < 12 and payout < 75:
        return "💎 Dividend King (High Value)"
    
    # 5. Stable Cash Cow (Safe yield, safe payout)
    if yield_val > 4 and payout < 65:
        return "🐄 Stable Cash Cow"
    
    # 6. Overvalued (Price is too high regardless of yield)
    if pe > 25:
        return "🎈 Overvalued (Price too high)"
        
    return "🔍 Neutral / Under Analysis"

# --- UI SETUP ---
st.set_page_config(page_title="IHSG Yield Master", layout="wide")
st.title("🏆 IHSG Dividend Master (Full Fix)")

# --- 1. SEARCH SECTION ---
st.subheader("🔍 Smart Ticker Analysis")
search_ticker = st.text_input("Analyze Ticker (e.g. ITMG, ACRO):", "").upper()

if search_ticker:
    t_jk = f"{search_ticker}.JK" if not search_ticker.endswith(".JK") else search_ticker
    res = supabase.table("master_schedule").select("*").eq("ticker", t_jk).execute()
    
    if res.data:
        stock_data = res.data[0]
        pe_val = stock_data.get('pe_ratio')
        payout = stock_data.get('payout_ratio')
        div_val = stock_data['total_dividend_2025']
        
        with st.spinner(f"Getting live price for {t_jk}..."):
            try:
                ticker_obj = yf.Ticker(t_jk)
                live_price = ticker_obj.fast_info['last_price']
                live_ratio = (div_val / live_price * 100) if live_price > 0 else 0
                
                label = get_stock_label(live_ratio, pe_val, payout)
                
                if "Speculative" in label:
                    st.warning(f"**Status:** {label}")
                else:
                    st.info(f"**Status:** {label}")
                
                s1, s2, s3, s4 = st.columns(4)
                s1.metric("Live Yield Ratio", f"{live_ratio:.2f}%")
                s2.metric("P/E (Vault)", f"{pe_val:.2f}x" if not pd.isna(pe_val) else "N/A")
                s3.metric("Payout (Vault)", f"{payout:.1f}%" if not pd.isna(payout) else "0.0%")
                s4.metric("Live Price", f"Rp {live_price:,.0f}")
            except Exception:
                st.error("Rate limit hit. Showing Vault data only.")
    else:
        st.warning(f"Ticker {t_jk} not found.")

st.divider()

# --- 2. SIDEBAR ---
all_ihsg = load_tickers_from_excel()
update_queue = get_oldest_price_batch(1000)

with st.sidebar:
    st.header("📊 Mining Engine")
    st.write(f"Total Tickers: **{len(all_ihsg)}**")
    if st.button("🚀 Update Next Batch (1000)"):
        if not update_queue:
            st.error("No stocks found.")
        else:
            p_bar = st.progress(0)
            status_text = st.empty()
            for i, ticker in enumerate(update_queue):
                try:
                    status_text.text(f"Updating [{i+1}/956]: {ticker}")
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="1d", interval="1h")
                    if not hist.empty:
                        recent_price = hist['Close'].iloc[-1]
                        try:
                            info = stock.info
                            pe_r = info.get('trailingPE')
                            payout_r = info.get('payoutRatio')
                            if payout_r: payout_r = round(payout_r * 100, 2)
                        except: pe_r, payout_r = None, None
                        
                        db_row = supabase.table("master_schedule").select("total_dividend_2025").eq("ticker", ticker).execute()
                        div_2025 = db_row.data[0]['total_dividend_2025']
                        calc_y = (div_2025 / recent_price * 100) if recent_price > 0 else 0
                        
                        supabase.table("master_schedule").update({
                            "previous_close": float(recent_price),
                            "dividend_yield": round(float(calc_y), 2),
                            "pe_ratio": pe_r,
                            "payout_ratio": payout_r,
                            "last_mined": datetime.now().isoformat()
                        }).eq("ticker", ticker).execute()
                    p_bar.progress((i + 1) / len(update_queue))
                    time.sleep(0.2)
                except Exception: continue
            st.rerun()

# --- 3. MAIN DASHBOARD ---
st.subheader("🔥 Dividend Leaderboard")
view_res = supabase.table("master_schedule").select("*").not_.is_("dividend_yield", "null").order("dividend_yield", desc=True).limit(100).execute()

if view_res.data:
    df = pd.DataFrame(view_res.data)
    # Apply robust label logic
    df['Category'] = df.apply(lambda x: get_stock_label(x['dividend_yield'], x['pe_ratio'], x['payout_ratio']), axis=1)
    
    st.dataframe(
        df[["ticker", "Category", "dividend_yield", "pe_ratio", "payout_ratio", "previous_close"]],
        use_container_width=True,
        column_config={
            "dividend_yield": st.column_config.NumberColumn("Yield %", format="%.2f%%"),
            "pe_ratio": st.column_config.NumberColumn("P/E", format="%.2f x"),
            "payout_ratio": st.column_config.NumberColumn("Payout %", format="%.1f%%"),
            "previous_close": "Price"
        }
    )
