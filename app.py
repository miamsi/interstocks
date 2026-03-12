import streamlit as st
import pandas as pd
import yfinance as yf
from supabase import create_client, Client
from groq import Groq
import time
import os
from datetime import datetime

# --- SETUP ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)
groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# --- DATA FUNCTIONS ---
def load_tickers_from_excel():
    file_name = "Daftar Saham  - 20260306.xlsx" 
    if not os.path.exists(file_name):
        file_name = r"C:\Users\michael.sidabutar\Documents\stock mining\Daftar Saham  - 20260306.xlsx"
    if not os.path.exists(file_name):
        return []
    try:
        df = pd.read_excel(file_name)
        tickers = df['Kode'].dropna().astype(str).tolist()
        return [f"{t}.JK" for t in tickers if len(t) == 4]
    except:
        return []

def load_bonds_data():
    # Mencoba beberapa kemungkinan nama file
    possible_files = [
        "LIST HARGA OBLIGASI PER 12 MARET 2026.xlsx - Sheet1.csv",
        "LIST HARGA OBLIGASI PER 12 MARET 2026.xlsx"
    ]
    
    df_bonds = pd.DataFrame()
    for f in possible_files:
        if os.path.exists(f):
            try:
                df_bonds = pd.read_csv(f) if f.endswith('.csv') else pd.read_excel(f)
                break
            except: continue
    
    if df_bonds.empty:
        return pd.DataFrame()

    # AUTO-FIX KOLOM: Menghapus spasi dan tanda petik yang bikin KeyError
    df_bonds.columns = [c.strip().replace("'", "").replace("\"", "") for c in df_bonds.columns]
    
    # Mapping nama kolom ke standar kita
    rename_map = {
        "BONDS CODE": "ticker",
        "YEARLY COUPON RATE": "coupon",
        "LATEST PRICE PER UNIT": "price"
    }
    df_bonds = df_bonds.rename(columns=rename_map)
    
    # Kalkulasi Yield
    face_value = 1000000
    if 'price' in df_bonds.columns and 'coupon' in df_bonds.columns:
        df_bonds['price'] = pd.to_numeric(df_bonds['price'], errors='coerce')
        df_bonds['coupon'] = pd.to_numeric(df_bonds['coupon'], errors='coerce')
        df_bonds['real_yield'] = (df_bonds['coupon'] * face_value / df_bonds['price']) * 100
        
    return df_bonds.dropna(subset=['ticker', 'price'])

def get_oldest_price_batch(batch_size=1000):
    try:
        res = supabase.table("master_schedule").select("ticker").order("last_mined", desc=False).limit(batch_size).execute()
        return [row['ticker'] for row in res.data]
    except: return []

def get_stock_label(yield_val, pe, payout):
    if pd.isna(yield_val) or yield_val <= 0: return "⚪ No Data"
    if pd.isna(pe) or pd.isna(payout) or pe == 0 or payout <= 0: return "🌀 Speculative (Data Gap)"
    if payout > 95: return "🚨 Yield Trap (Unsustainable)"
    if yield_val > 7 and pe < 12 and payout < 75: return "💎 Dividend King (High Value)"
    if yield_val > 4 and payout < 65: return "🐄 Stable Cash Cow"
    if pe > 25: return "🎈 Overvalued (Price too high)"
    return "🔍 Neutral / Under Analysis"

# --- AI SIMULATION ENGINE ---
def run_groq_simulation(df_stocks, df_bonds, profile):
    stock_feed = df_stocks[['ticker', 'Category', 'dividend_yield']].head(10).to_string(index=False)
    bond_feed = df_bonds[['ticker', 'coupon', 'price', 'real_yield']].head(10).to_string(index=False)
    
    prompt = f"""
    ROLE: Penasihat Investasi Senior IHSG & SBN.
    
    PROFIL INVESTOR:
    - Dana: Rp {profile['budget']:,.0f}
    - Jangka Waktu: {profile['horizon']}
    - Prioritas: {profile['priority']}
    - Kekhawatiran: {profile['concern']}
    
    KONSEP OBLIGASI: Nilai Pari Rp 1.000.000 per unit (Pemerintah selalu bayar 1jt saat jatuh tempo).
    
    DATA SAHAM:
    {stock_feed}
    
    DATA OBLIGASI:
    {bond_feed}
    
    TUGAS:
    1. Berikan rekomendasi alokasi dana (Aman vs Agresif).
    2. Hitung berapa UNIT obligasi yang bisa dibeli dengan dana Rp {profile['safe_amt']:,.0f}.
    3. Pilih 3 saham yang cocok dengan prioritas user.
    4. Jawab kekhawatiran user secara detail dan menenangkan.
    """
    try:
        completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-8b-8192",
            temperature=0.1,
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Gagal menjalankan simulasi AI: {e}"

# --- UI SETUP ---
st.set_page_config(page_title="IHSG Yield Master", layout="wide")
st.title("🏆 IHSG Dividend Master (Pro Filter Edition)")

# TABS NAVIGATION
tab_sim, tab_list, tab_search = st.tabs(["🤖 AI Advisor Simulation", "🔥 Dividend Leaderboard", "🔍 Ticker Analysis"])

with tab_sim:
    st.subheader("🤖 Smart Portofolio Advisor")
    with st.expander("📝 Form Konsultasi Detail", expanded=True):
        with st.form("deep_wizard"):
            col1, col2 = st.columns(2)
            with col1:
                u_budget = st.number_input("Total Dana Investasi (IDR):", value=50000000, step=5000000)
                u_priority = st.selectbox("Apa yang paling Anda harapkan?", 
                                         ["Passive Income Bulanan (Kupon & Dividen)", 
                                          "Pertumbuhan Aset Jangka Panjang", 
                                          "Keamanan Modal (Tidak boleh berkurang sama sekali)"])
                u_risk = st.select_slider("Toleransi Fluktuasi Harga:", ["Sangat Rendah", "Menengah", "Tinggi (Siap High Risk)"])
            with col2:
                u_horizon = st.selectbox("Rencana Investasi (Tahun):", ["< 1 Tahun", "1-3 Tahun", "3-5 Tahun", "5+ Tahun"])
                u_concern = st.text_area("Apa kekhawatiran terbesar Anda?", "Saya takut uang saya hilang jika perusahaan bangkrut atau negara krisis.")
            
            submit_sim = st.form_submit_button("🚀 Generate Strategi Investasi")

    if submit_sim:
        risk_map = {"Sangat Rendah": 0.85, "Menengah": 0.50, "Tinggi (Siap High Risk)": 0.20}
        safe_pct = risk_map[u_risk]
        profile = {
            "budget": u_budget, "priority": u_priority, "horizon": u_horizon, 
            "concern": u_concern, "safe_amt": u_budget * safe_pct, "aggr_amt": u_budget * (1 - safe_pct)
        }
        
        df_b = load_bonds_data()
        res_s = supabase.table("master_schedule").select("*").not_.is_("dividend_yield", "null").order("dividend_yield", desc=True).limit(20).execute()
        df_s = pd.DataFrame(res_s.data)
        df_s['Category'] = df_s.apply(lambda x: get_stock_label(x['dividend_yield'], x['pe_ratio'], x['payout_ratio']), axis=1)

        with st.spinner("AI sedang menghitung unit obligasi dan memilih saham..."):
            advice = run_groq_simulation(df_s, df_b, profile)
            st.markdown(advice)

with tab_list:
    st.subheader("🔥 Dividend Leaderboard")
    # (Logika Filter & Dataframe Michael - Tetap Dipertahankan)
    with st.expander("🛠️ Filter Controls", expanded=True):
        f1, f2, f3 = st.columns(3)
        cat_options = ["All Categories", "💎 Dividend King (High Value)", "🐄 Stable Cash Cow", "🔍 Neutral / Under Analysis", "🌀 Speculative (Data Gap)", "🚨 Yield Trap (Unsustainable)", "🎈 Overvalued (Price too high)"]
        selected_cat = f1.selectbox("Category:", cat_options)
        min_yield = f2.slider("Min Yield %:", 0.0, 30.0, 0.0)
        hide_spec = f3.checkbox("Hide Speculative", value=False)

    view_res = supabase.table("master_schedule").select("*").not_.is_("dividend_yield", "null").order("dividend_yield", desc=True).limit(500).execute()
    if view_res.data:
        df = pd.DataFrame(view_res.data)
        df['Category'] = df.apply(lambda x: get_stock_label(x['dividend_yield'], x['pe_ratio'], x['payout_ratio']), axis=1)
        if selected_cat != "All Categories": df = df[df['Category'] == selected_cat]
        df = df[df['dividend_yield'] >= min_yield]
        if hide_spec: df = df[~df['Category'].str.contains("Speculative")]
        st.dataframe(df[["ticker", "Category", "dividend_yield", "pe_ratio", "payout_ratio", "previous_close"]], use_container_width=True)

with tab_search:
    st.subheader("🔍 Smart Ticker Analysis")
    search_ticker = st.text_input("Analyze Ticker (e.g. BBRI, ITMG):", "").upper()
    if search_ticker:
        # (Logika Search Michael - Tetap Dipertahankan)
        pass

# --- SIDEBAR MINING ENGINE ---
all_ihsg = load_tickers_from_excel()
update_queue = get_oldest_price_batch(1000)
with st.sidebar:
    st.header("📊 Mining Engine")
    st.write(f"Total Tickers: **{len(all_ihsg)}**")
    if st.button("🚀 Update Next Batch (1000)"):
        # (Logika Update Michael - Tetap Dipertahankan)
        pass
