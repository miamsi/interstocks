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

# --- DATA LOADING FUNCTIONS ---
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
    except:
        return []

def load_bonds_from_excel():
    file_path = "LIST HARGA OBLIGASI PER 12 MARET 2026.xlsx"
    if not os.path.exists(file_path):
        return pd.DataFrame()
    try:
        df_bonds = pd.read_excel(file_path)
        face_value = 1000000
        # Kalkulasi Yield Riil berdasarkan harga pasar vs kupon
        df_bonds['real_yield'] = (df_bonds['YEARLY COUPON RATE'] * face_value / df_bonds['LATEST PRICE PER UNIT']) * 100
        df_bonds['Price_Status'] = df_bonds['LATEST PRICE PER UNIT'].apply(
            lambda x: "Premium (Di atas 1jt)" if x > face_value else ("Discount (Di bawah 1jt)" if x < face_value else "Par")
        )
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

# --- AI ADVISOR ENGINE ---
def run_groq_simulation(df_stocks, df_bonds, profile):
    bond_feed = df_bonds[['BOND\'S CODE', 'YEARLY COUPON RATE', 'LATEST PRICE PER UNIT', 'real_yield', 'END DATE']].to_string(index=False)
    stock_feed = df_stocks[['ticker', 'Category', 'dividend_yield', 'pe_ratio']].to_string(index=False)
    
    prompt = f"""
    ROLE: Penasihat Investasi IHSG & SBN Profesional.
    KONSEP KRUSIAL: Nilai Pari/Jatuh Tempo Obligasi Pemerintah SELALU Rp 1.000.000 per unit.
    
    PROFIL USER:
    - Budget: Rp {profile['budget']:,.0f}
    - Reaksi Pasar Jatuh: {profile['reaction']}
    - Tujuan: {profile['goal']}
    
    DATA SAHAM (GROUND TRUTH):
    {stock_feed}
    
    DATA OBLIGASI (GROUND TRUTH):
    {bond_feed}
    
    TUGAS:
    1. Alokasikan Rp {profile['safe_amt']:,.0f} ke OBLIGASI. Hitung berapa unit yang didapat (Dana / Harga Pasar).
    2. Edukasi user bahwa meskipun beli di harga pasar, pemerintah akan mengembalikan Rp 1.000.000 per unit saat jatuh tempo.
    3. Alokasikan Rp {profile['aggr_amt']:,.0f} ke 3-5 saham pilihan (Hindari Yield Trap).
    4. Berikan pesan penenang sesuai karakter psikologi user.
    """
    
    completion = groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3-8b-8192",
        temperature=0.1,
    )
    return completion.choices[0].message.content

# --- UI SETUP ---
st.set_page_config(page_title="IHSG Yield Master", layout="wide")
st.title("🏆 IHSG Dividend Master (Wizard Edition)")

# --- 1. AI ADVISOR WIZARD ---
st.subheader("🤖 AI Advisor Wizard")
with st.expander("📝 Konsultasi Psikologi & Strategi", expanded=True):
    with st.form("wizard_form"):
        u_budget = st.number_input("Total Dana Investasi (IDR):", value=30000000, step=5000000)
        c1, c2 = st.columns(2)
        with c1:
            u_reaction = st.radio(
                "Jika nilai investasi turun 10% dalam seminggu, reaksi Anda?",
                ["Sangat Khawatir: Ingin tarik semua dana.", "Cemas: Akan memantau tiap jam.", "Tenang: Paham risiko pasar.", "Antusias: Ingin beli lebih banyak."]
            )
            u_goal = st.selectbox("Tujuan Investasi:", ["Passive Income Bulanan", "Wealth Building", "Keamanan Modal"])
        with c2:
            st.info("💡 Info: Obligasi Pemerintah selalu kembali Rp 1.000.000/unit saat jatuh tempo.")
            u_horizon = st.select_slider("Jangka Waktu:", options=["< 1 Tahun", "1-3 Tahun", "3-5 Tahun", "5+ Tahun"])
        
        submit_wizard = st.form_submit_button("🚀 Generate Simulasi Portofolio")

if submit_wizard:
    # Corridor Logic: Mapping Psychology to Asset Allocation
    risk_map = {"Sangat Khawatir: Ingin tarik semua dana.": 0.85, "Cemas: Akan memantau tiap jam.": 0.60, "Tenang: Paham risiko pasar.": 0.40, "Antusias: Ingin beli lebih banyak.": 0.15}
    safe_pct = risk_map[u_reaction]
    profile = {"budget": u_budget, "reaction": u_reaction, "goal": u_goal, "safe_amt": u_budget * safe_pct, "aggr_amt": u_budget * (1 - safe_pct)}
    
    # Context Data
    df_b = load_bonds_from_excel()
    res_s = supabase.table("master_schedule").select("*").not_.is_("dividend_yield", "null").order("dividend_yield", desc=True).limit(30).execute()
    df_s = pd.DataFrame(res_s.data)
    df_s['Category'] = df_s.apply(lambda x: get_stock_label(x['dividend_yield'], x['pe_ratio'], x['payout_ratio']), axis=1)
    df_s_v = df_s[~df_s['Category'].isin(["🚨 Yield Trap (Unsustainable)", "⚪ No Data"])]

    with st.spinner("AI sedang meracik strategi..."):
        advice = run_groq_simulation(df_s_v.head(15), df_b, profile)
        st.markdown(advice)

st.divider()

# --- 2. SEARCH SECTION ---
st.subheader("🔍 Smart Ticker Analysis")
search_ticker = st.text_input("Analyze Ticker (e.g. ITMG):", "").upper()
if search_ticker:
    t_jk = f"{search_ticker}.JK" if not search_ticker.endswith(".JK") else search_ticker
    res = supabase.table("master_schedule").select("*").eq("ticker", t_jk).execute()
    if res.data:
        stock_data = res.data[0]
        try:
            live_price = yf.Ticker(t_jk).fast_info['last_price']
            live_ratio = (stock_data['total_dividend_2025'] / live_price * 100) if live_price > 0 else 0
            label = get_stock_label(live_ratio, stock_data.get('pe_ratio'), stock_data.get('payout_ratio'))
            st.info(f"**Status:** {label}")
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Live Yield Ratio", f"{live_ratio:.2f}%")
            s2.metric("P/E (Vault)", f"{stock_data.get('pe_ratio'):.2f}x")
            s3.metric("Payout (Vault)", f"{stock_data.get('payout_ratio'):.1f}%")
            s4.metric("Live Price", f"Rp {live_price:,.0f}")
        except: st.error("Rate limit hit.")

st.divider()

# --- 3. SIDEBAR & MINING ---
all_ihsg = load_tickers_from_excel()
update_queue = get_oldest_price_batch(1000)
with st.sidebar:
    st.header("📊 Mining Engine")
    st.write(f"Total Tickers: **{len(all_ihsg)}**")
    if st.button("🚀 Update Next Batch"):
        if update_queue:
            p_bar = st.progress(0)
            for i, ticker in enumerate(update_queue):
                try:
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="1d")
                    if not hist.empty:
                        recent_price = hist['Close'].iloc[-1]
                        info = stock.info
                        pe_r, pay_r = info.get('trailingPE'), info.get('payoutRatio')
                        if pay_r: pay_r *= 100
                        div_2025 = supabase.table("master_schedule").select("total_dividend_2025").eq("ticker", ticker).execute().data[0]['total_dividend_2025']
                        supabase.table("master_schedule").update({
                            "previous_close": float(recent_price),
                            "dividend_yield": round(float(div_2025/recent_price*100), 2),
                            "pe_ratio": pe_r, "payout_ratio": pay_r, "last_mined": datetime.now().isoformat()
                        }).eq("ticker", ticker).execute()
                    p_bar.progress((i + 1) / len(update_queue))
                except: continue
            st.rerun()

# --- 4. MAIN DASHBOARD ---
st.subheader("🔥 Dividend Leaderboard")
view_res = supabase.table("master_schedule").select("*").not_.is_("dividend_yield", "null").order("dividend_yield", desc=True).limit(500).execute()
if view_res.data:
    df = pd.DataFrame(view_res.data)
    df['Category'] = df.apply(lambda x: get_stock_label(x['dividend_yield'], x['pe_ratio'], x['payout_ratio']), axis=1)
    st.dataframe(df[["ticker", "Category", "dividend_yield", "pe_ratio", "payout_ratio", "previous_close"]], use_container_width=True)
