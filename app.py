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
        file_name = "Daftar Saham  - 20260306.xlsx"
    if not os.path.exists(file_name):
        return []
    try:
        df = pd.read_excel(file_name)
        tickers = df['Kode'].dropna().astype(str).tolist()
        return [f"{t}.JK" for t in tickers if len(t) == 4]
    except Exception as e:
        return []

def load_bonds_data():
    file_path = "LIST HARGA OBLIGASI PER 12 MARET 2026.xlsx - Sheet1.csv"
    if not os.path.exists(file_path):
        return pd.DataFrame()
    try:
        df_bonds = pd.read_csv(file_path)
        face_value = 1000000
        df_bonds['real_yield'] = (df_bonds['YEARLY COUPON RATE'] * face_value / df_bonds['LATEST PRICE PER UNIT']) * 100
        return df_bonds
    except:
        return pd.DataFrame()

def get_oldest_price_batch(batch_size=1000):
    try:
        res = supabase.table("master_schedule").select("ticker").order("last_mined", desc=False).limit(batch_size).execute()
        return [row['ticker'] for row in res.data]
    except:
        return []

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
    stock_list = df_stocks[['ticker', 'Category', 'dividend_yield']].head(15).to_dict(orient='records')
    bond_list = df_bonds[['BOND\'S CODE', 'YEARLY COUPON RATE', 'LATEST PRICE PER UNIT', 'real_yield']].to_dict(orient='records')
    
    stock_feed = "\n".join([f"- {s['ticker']}: {s['dividend_yield']}% ({s['Category']})" for s in stock_list])
    bond_feed = "\n".join([f"- {b['BOND\'S CODE']}: Yield {b['real_yield']:.2f}%, Harga Rp {b['LATEST PRICE PER UNIT']:,.0f}" for b in bond_list])
    
    prompt = f"""
    ROLE: Penasihat Investasi Senior.
    ATURAN OBLIGASI: Nilai jatuh tempo SELALU Rp 1.000.000 per unit.
    
    PROFIL INVESTOR:
    - Dana: Rp {profile['budget']:,.0f}
    - Jangka Waktu: {profile['horizon']}
    - Toleransi Risiko: {profile['risk_desc']}
    - Prioritas Utama: {profile['priority']}
    - Kekhawatiran Terbesar: {profile['concern']}
    
    DATA MARKET:
    [Obligasi Pemerintah]
    {bond_feed}
    
    [Saham Pilihan]
    {stock_feed}
    
    TUGAS:
    1. Berikan alokasi aset (Aman vs Agresif) yang sangat spesifik.
    2. Hitung berapa 'Unit' obligasi yang dibeli dengan porsi dana aman.
    3. Pilih 3-4 saham yang paling menjawab 'Prioritas Utama' user.
    4. Jawab 'Kekhawatiran Terbesar' user dengan data.
    """
    
    try:
        completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-8b-8192",
            temperature=0.2,
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Gagal memuat simulasi: {e}"

# --- UI SETUP ---
st.set_page_config(page_title="IHSG Yield Master", layout="wide")
st.title("🏆 IHSG Dividend Master (Pro Filter Edition)")

# TABS DEFINITION
tab_simulation, tab_leaderboard, tab_analysis = st.tabs(["🤖 AI Advisor & Simulation", "🔥 Dividend Leaderboard", "🔍 Ticker Analysis"])

with tab_simulation:
    st.subheader("🤖 AI Portofolio Advisor")
    with st.expander("📝 Ceritakan Profil & Ekspektasi Investasi Anda", expanded=True):
        with st.form("deep_wizard"):
            col1, col2 = st.columns(2)
            with col1:
                u_budget = st.number_input("Dana yang siap diinvestasikan (IDR):", value=50000000, step=10000000)
                u_risk = st.select_slider("Tingkat kenyamanan terhadap fluktuasi harga:", 
                                         options=["Sangat Konservatif (Takut rugi)", "Moderat (Siap fluktuasi kecil)", "Agresif (Siap rugi demi profit besar)"])
                u_priority = st.selectbox("Apa yang paling Anda cari saat ini?", 
                                         ["Dividen besar setiap tahun", "Keamanan modal utama tetap utuh", "Keseimbangan antara bunga & dividen"])
            with col2:
                u_horizon = st.selectbox("Berapa lama dana ini tidak akan disentuh?", ["< 1 Tahun", "1-3 Tahun", "3-5 Tahun", "5+ Tahun"])
                u_concern = st.text_area("Apa kekhawatiran terbesar Anda? (Contoh: Inflasi, saham nyangkut, atau butuh dana mendadak)", 
                                        "Saya takut modal saya berkurang jauh saat jatuh tempo.")
            
            submit_sim = st.form_submit_button("🚀 Jalankan Simulasi Deep Analysis")

    if submit_sim:
        risk_map = {"Sangat Konservatif (Takut rugi)": 0.8, "Moderat (Siap fluktuasi kecil)": 0.5, "Agresif (Siap rugi demi profit besar)": 0.2}
        safe_pct = risk_map[u_risk]
        profile = {
            "budget": u_budget, "horizon": u_horizon, "risk_desc": u_risk, 
            "priority": u_priority, "concern": u_concern,
            "safe_amt": u_budget * safe_pct, "aggr_amt": u_budget * (1 - safe_pct)
        }
        
        df_b = load_bonds_data()
        res_s = supabase.table("master_schedule").select("*").not_.is_("dividend_yield", "null").order("dividend_yield", desc=True).limit(30).execute()
        df_s = pd.DataFrame(res_s.data)
        df_s['Category'] = df_s.apply(lambda x: get_stock_label(x['dividend_yield'], x['pe_ratio'], x['payout_ratio']), axis=1)

        with st.spinner("AI sedang menganalisis profil dan data market..."):
            advice = run_groq_simulation(df_s, df_b, profile)
            st.markdown(advice)

with tab_leaderboard:
    st.subheader("🔥 Dividend Leaderboard")
    with st.expander("🛠️ Filter Controls", expanded=True):
        f1, f2, f3 = st.columns(3)
        selected_cat = f1.selectbox("Filter by Category:", ["All Categories", "💎 Dividend King (High Value)", "🐄 Stable Cash Cow", "🔍 Neutral / Under Analysis", "🌀 Speculative (Data Gap)", "🚨 Yield Trap (Unsustainable)", "🎈 Overvalued (Price too high)"])
        min_yield = f2.slider("Minimum Yield %:", 0.0, 30.0, 0.0)
        hide_spec = f3.checkbox("Hide Speculative Stocks", value=False)

    view_res = supabase.table("master_schedule").select("*").not_.is_("dividend_yield", "null").order("dividend_yield", desc=True).limit(500).execute()
    if view_res.data:
        df = pd.DataFrame(view_res.data)
        df['Category'] = df.apply(lambda x: get_stock_label(x['dividend_yield'], x['pe_ratio'], x['payout_ratio']), axis=1)
        if selected_cat != "All Categories": df = df[df['Category'] == selected_cat]
        df = df[df['dividend_yield'] >= min_yield]
        if hide_spec: df = df[~df['Category'].str.contains("Speculative")]
        
        st.caption(f"Showing {len(df)} results matching your filters.")
        st.dataframe(df[["ticker", "Category", "dividend_yield", "pe_ratio", "payout_ratio", "previous_close"]], use_container_width=True)

with tab_analysis:
    st.subheader("🔍 Smart Ticker Analysis")
    search_ticker = st.text_input("Analyze Ticker (e.g. ITMG, ACRO):", "").upper()
    if search_ticker:
        t_jk = f"{search_ticker}.JK" if not search_ticker.endswith(".JK") else search_ticker
        res = supabase.table("master_schedule").select("*").eq("ticker", t_jk).execute()
        if res.data:
            stock_data = res.data[0]
            with st.spinner(f"Getting live price for {t_jk}..."):
                try:
                    ticker_obj = yf.Ticker(t_jk)
                    live_price = ticker_obj.fast_info['last_price']
                    live_ratio = (stock_data['total_dividend_2025'] / live_price * 100) if live_price > 0 else 0
                    label = get_stock_label(live_ratio, stock_data.get('pe_ratio'), stock_data.get('payout_ratio'))
                    st.info(f"**Status:** {label}")
                    s1, s2, s3, s4 = st.columns(4)
                    s1.metric("Live Yield", f"{live_ratio:.2f}%")
                    s2.metric("P/E", f"{stock_data.get('pe_ratio'):.2f}x")
                    s3.metric("Payout", f"{stock_data.get('payout_ratio'):.1f}%")
                    s4.metric("Live Price", f"Rp {live_price:,.0f}")
                except: st.error("Rate limit hit. Showing Vault data only.")

# --- SIDEBAR ---
all_ihsg = load_tickers_from_excel()
update_queue = get_oldest_price_batch(1000)
with st.sidebar:
    st.header("📊 Mining Engine")
    st.write(f"Total Tickers: **{len(all_ihsg)}**")
    if st.button("🚀 Update Next Batch (1000)"):
        if not update_queue: st.error("No stocks found.")
        else:
            p_bar = st.progress(0)
            status_text = st.empty()
            for i, ticker in enumerate(update_queue):
                try:
                    status_text.text(f"Updating [{i+1}/{len(update_queue)}]: {ticker}")
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="1d", interval="1h")
                    if not hist.empty:
                        recent_price = hist['Close'].iloc[-1]
                        info = stock.info
                        pe_r, payout_r = info.get('trailingPE'), info.get('payoutRatio')
                        if payout_r: payout_r = round(payout_r * 100, 2)
                        div_2025 = supabase.table("master_schedule").select("total_dividend_2025").eq("ticker", ticker).execute().data[0]['total_dividend_2025']
                        supabase.table("master_schedule").update({
                            "previous_close": float(recent_price),
                            "dividend_yield": round(float(div_2025/recent_price*100), 2),
                            "pe_ratio": pe_r, "payout_ratio": payout_r, "last_mined": datetime.now().isoformat()
                        }).eq("ticker", ticker).execute()
                    p_bar.progress((i + 1) / len(update_queue))
                    time.sleep(0.2)
                except: continue
            st.rerun()
