# ==========================================================
# FIX PYTHON PATH
# ==========================================================
import sys
import os
from datetime import date

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

# ==========================================================
# LOAD ENV (WAJIB)
# ==========================================================
from dotenv import load_dotenv
load_dotenv()

# ==========================================================
# IMPORTS
# ==========================================================
import streamlit as st
import pandas as pd
import numpy as np

from app.core.engine import ScreenerEngine
from app.config.saham_list import SAHAM_LIST
from app.config.saham_profile import SAHAM_PROFILE
from app.config.dividend_list import DIVIDEND_LIST
from app.renderers.telegram import render_telegram
from app.services.telegram_bot import send_message
from app.services.logic import round_price
from app.services.logic import detect_day_trade, detect_market_mover
from app.services.data import get_price_data
from app.utils.news_engine import fetch_stock_news

from app.tracker.tracker import (
    load_trades,
    save_buy,
    save_sell,
    enrich_trades,
    delete_trade,
)

from app.renderers.telegram_stock_analysis import render_stock_analysis_message
from app.core.dividend_engine import DividendEngine

# ==========================================================
# PAGE CONFIG
# ==========================================================
st.set_page_config(page_title="Cruzer AI Screener", layout="wide")
st.title("🤖 Stock Screener Dashboard (Beta)")
st.caption("AI-powered multi-strategy stock screening")

# ==========================================================
# ======================= HELPERS ==========================
# ==========================================================
def format_price(x):
    return f"Rp {int(float(x)):,}".replace(",", ".")


def format_range(a, b):
    return f"{format_price(a)} – {format_price(b)}"


def format_tp(tp):
    return " / ".join(format_price(x) for x in tp)


def price_position(last_price, entry_low, entry_high):
    if entry_low <= last_price <= entry_high:
        return "INSIDE"
    elif last_price < entry_low:
        return "BELOW"
    return "ABOVE"

def format_date_indo(d):
    if not d or pd.isna(d):
        return "-"
    return pd.to_datetime(d).strftime("%d-%b-%Y")

def near_resistance(last_price, resistance, threshold_pct=4):
    return 0 <= (resistance - last_price) / resistance * 100 <= threshold_pct


def near_entry(last_price, entry_high, threshold_pct=1):
    return 0 <= (last_price - entry_high) / entry_high * 100 <= threshold_pct


def score_color(val):
    if val >= 85:
        return "background-color:#16a34a;color:white"
    elif val >= 70:
        return "background-color:#22c55e;color:black"
    elif val >= 60:
        return "background-color:#fde047;color:black"
    return "background-color:#f87171;color:white"


def render_df(data):
    df = pd.DataFrame(data)
    if df.empty:
        st.info("Tidak ada data")
        return
    if "Score" in df.columns:
        df = df.style.applymap(score_color, subset=["Score"])
    st.dataframe(df, use_container_width=True)

def require_trading_password():
    SHARE_PASSWORD = st.secrets.get("SHARE_PASSWORD")

    # kalau belum pernah login
    if "trading_auth_time" not in st.session_state:
        st.session_state.trading_auth_time = None

    # cek apakah masih dalam 7 hari
    if st.session_state.trading_auth_time:
        if datetime.now() - st.session_state.trading_auth_time < timedelta(days=7):
            return True  # masih valid

    # ===== FORM PASSWORD =====
    st.warning("🔒 Halaman ini dilindungi password")

    password_input = st.text_input("Masukkan password", type="password")

    if st.button("Login"):
        if password_input == SHARE_PASSWORD:
            st.session_state.trading_auth_time = datetime.now()
            st.success("✅ Login berhasil")
            st.rerun()
        else:
            st.error("❌ Password salah")

    return False

def calc_minor_support(df, lookback=12):
    """
    Minor support = lowest low dari N candle terakhir
    Aman untuk:
    - low / Low
    - MultiIndex
    - memastikan return SELALU float atau None
    """
    if df is None or df.empty:
        return None

    recent = df.tail(lookback)

    # === CASE 1: kolom tunggal ===
    for col in ["low", "Low", "LOW"]:
        if col in recent.columns:
            series = recent[col].dropna()
            if series.empty:
                return None
            return float(series.min())

    # === CASE 2: MultiIndex ===
    if isinstance(recent.columns, pd.MultiIndex):
        for col in recent.columns:
            if str(col[-1]).lower() == "low":
                series = recent[col].dropna()
                if series.empty:
                    return None
                return float(series.min())

    return None

# =============================
# CACHE (biar scan gak berat)
# =============================

@st.cache_data(ttl=3600)
def load_dividend_data(symbols):
    return DividendEngine.scan(symbols)


def render_dividend_screener():
    st.header("💰 Dividend Screener")
    st.caption("Daftar saham dividen dipisah per sektor")

    symbols = [s + ".JK" for s in DIVIDEND_LIST]

    with st.spinner("Loading dividend database..."):
        df = load_dividend_data(symbols)

    if df.empty:
        st.warning("Tidak ada data ditemukan")
        return

    # =============================
    # FIX PAYOUT %
    # =============================
    def normalize_payout(x):
        if not x:
            return 0
        if x < 2:
            return x * 100
        return x

    df["payout_ratio"] = df["payout_ratio"].apply(normalize_payout)

    # =============================
    # FORMAT DATA NUMERIC
    # =============================
    df["last_dividend_1"] = df["last_dividend_1"].round(2)
    df["last_dividend_2"] = df["last_dividend_2"].round(2)
    df["price"] = df["price"].fillna(0)

    # Base dividend terbesar
    df["dividend_base"] = df[["last_dividend_1", "last_dividend_2"]].max(axis=1)

    # =============================
    # EXCLUDE YANG TIDAK ADA DIVIDEN
    # =============================
    df = df[
        (df["dividend_base"] > 0) &
        (df["price"] > 0)
    ].copy()

    # =============================
    # SIMPAN DATETIME RAW UNTUK FILTER
    # =============================
    import pandas as pd
    from datetime import datetime, timedelta

    df["dt1"] = pd.to_datetime(df["last_dividend_date_1"], errors="coerce")
    df["dt2"] = pd.to_datetime(df["last_dividend_date_2"], errors="coerce")

    # =============================
    # FILTER BULAN / TAHUN / UPCOMING
    # =============================
    st.subheader("🔎 Filter")

    colf1, colf2, colf3 = st.columns(3)

    # Bulan
    bulan_list = {
        "All": 0,
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "Mei": 5, "Jun": 6,
        "Jul": 7, "Agu": 8, "Sep": 9, "Okt": 10, "Nov": 11, "Des": 12
    }
    selected_month = colf1.selectbox("📅 Bulan Ex-Date", list(bulan_list.keys()))

    # Tahun
    years_available = sorted(
        set(df["dt1"].dropna().dt.year.tolist()) |
        set(df["dt2"].dropna().dt.year.tolist())
    )
    years_available = ["All"] + [str(y) for y in years_available]
    selected_year = colf2.selectbox("🗓️ Tahun", years_available)

    # Apply filter bulan
    if selected_month != "All":
        m = bulan_list[selected_month]
        df = df[
            (df["dt1"].dt.month == m) |
            (df["dt2"].dt.month == m)
        ]

    # Apply filter tahun
    if selected_year != "All":
        y = int(selected_year)
        df = df[
            (df["dt1"].dt.year == y) |
            (df["dt2"].dt.year == y)
        ]

    if df.empty:
        st.warning("Tidak ada data sesuai filter.")
        return

    # =============================
    # FORMAT TANGGAL (DISPLAY)
    # =============================
    bulan_map = {
        "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
        "05": "Mei", "06": "Jun", "07": "Jul", "08": "Agu",
        "09": "Sep", "10": "Okt", "11": "Nov", "12": "Des"
    }

    def format_tanggal(tgl):
        if pd.isna(tgl):
            return "-"
        tgl = str(pd.to_datetime(tgl).date())
        y, m, d = tgl.split("-")
        return f"{int(d)}-{bulan_map[m]}-{y}"

    df["last_dividend_date_1"] = df["dt1"].apply(format_tanggal)
    df["last_dividend_date_2"] = df["dt2"].apply(format_tanggal)

    # Hilangin .JK
    df["symbol"] = df["symbol"].str.replace(".JK", "", regex=False)

    # =============================
    # SORT GLOBAL (BASE DIVIDEND)
    # =============================
    df = df.sort_values("dividend_base", ascending=False).reset_index(drop=True)

    # =============================
    # CLASS 1: SIZE
    # =============================
    total = len(df)

    def classify_dividend(idx):
        pct = idx / total
        if pct <= 0.2:
            return "💰 Big"
        elif pct <= 0.4:
            return "🟢 High"
        elif pct <= 0.6:
            return "🟡 Medium"
        elif pct <= 0.8:
            return "🔵 Low"
        else:
            return "🌱 Tiny"

    df["Class"] = [classify_dividend(i) for i in range(total)]

    class_order = {
        "💰 Big": 1,
        "🟢 High": 2,
        "🟡 Medium": 3,
        "🔵 Low": 4,
        "🌱 Tiny": 5
    }
    df["class_rank"] = df["Class"].map(class_order)

    # =============================
    # CLASS 2: TYPE
    # =============================
    cyclical_sectors = ["Energy", "Basic Materials"]

    def classify_type(row):
        years = row["years_paying"]
        payout = row["payout_ratio"]
        sector = row["sector"]

        if payout > 100:
            return "🔴 Risky"
        elif sector in cyclical_sectors:
            return "🔁 Cyclical"
        elif years >= 10:
            return "🏦 Stable"
        elif years >= 3:
            return "🌱 Growing"
        else:
            return "⚪ New"

    df["Type"] = df.apply(classify_type, axis=1)

    # =============================
    # FORMAT PRICE
    # =============================
    def format_rupiah(x):
        try:
            return f"Rp {int(x):,}".replace(",", ".")
        except:
            return "-"

    df["Harga"] = df["price"].apply(format_rupiah)

    # =============================
    # RENAME
    # =============================
    df = df.rename(columns={
        "symbol": "Ticker",
        "years_paying": "Years Paying",
        "last_dividend_1": "Last Div 1",
        "last_dividend_2": "Last Div 2",
        "last_dividend_date_1": "Date 1",
        "last_dividend_date_2": "Date 2",
        "payout_ratio": "Payout Ratio (%)"
    })

    # =============================
    # METRICS
    # =============================
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Stocks", len(df))
    col2.metric("Highest Dividend", f"{df['dividend_base'].max():,.0f}")
    col3.metric("Avg Dividend", f"{df['dividend_base'].mean():,.0f}")

    st.divider()

    # =============================
    # COLOR PAYOUT
    # =============================
    def color_payout(val):
        try:
            val = float(val)
        except:
            return ""
        if val <= 50:
            return "background-color:#d4edda;color:#155724;"
        elif val <= 80:
            return "background-color:#fff3cd;color:#856404;"
        elif val <= 100:
            return "background-color:#ffe5b4;color:#8a4b00;"
        else:
            return "background-color:#f8d7da;color:#721c24;"

    # =============================
    # LOOP PER SECTOR
    # =============================
    sectors = sorted(df["sector"].dropna().unique())

    for sector in sectors:
        sector_df = df[df["sector"] == sector].copy()

        sector_df = sector_df.sort_values(
            by=["class_rank", "price"],
            ascending=[True, False]
        ).reset_index(drop=True)

        sector_df.insert(0, "Rank", range(1, len(sector_df) + 1))

        sector_df = sector_df[
            [
                "Rank",
                "Ticker",
                "Harga",
                "Class",
                "Type",
                "Last Div 1",
                "Last Div 2",
                "Years Paying",
                "Payout Ratio (%)",
                "Date 1",
                "Date 2"
            ]
        ]

        sector_icons = {
            "Financial Services": "🏦",
            "Energy": "🛢️",
            "Consumer Defensive": "🛒",
            "Consumer Cyclical": "🛍️",
            "Industrials": "🏭",
            "Basic Materials": "🧱",
            "Healthcare": "💊",
            "Technology": "💻",
            "Communication Services": "📡",
            "Utilities": "⚡",
            "Real Estate": "🏢"
        }

        icon = sector_icons.get(sector, "📊")

        st.subheader(f"{icon} {sector} ({len(sector_df)})")

        styled_df = (
            sector_df.style
            .applymap(color_payout, subset=["Payout Ratio (%)"])
            .format({
                "Last Div 1": "{:,.2f}",
                "Last Div 2": "{:,.2f}",
                "Payout Ratio (%)": "{:,.2f}"
            })
        )

        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True
        )

        st.markdown("---")

# ==========================================================
# ===================== IMPORT ==============================
# ==========================================================
import os
import streamlit as st
import pandas as pd
import requests
from datetime import datetime

from app.config.saham_list import SAHAM_LIST
from app.core.scanner import scan_day
from app.core.engine import ScreenerEngine

# 🔥 FIX YFINANCE ERROR
os.environ["YFINANCE_NO_SQLITE"] = "1"


# ==========================================================
# ===================== TELEGRAM ============================
# ==========================================================
def send_telegram(msg):

    bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    try:
        requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=10
        )
    except:
        pass

# ==========================================================
# ===================== WEEK ================================
# ==========================================================
def format_rsi_status(status):

    if not status:
        return "⚪ Normal"

    if "Oversold" in status:
        return "🟢 Oversold"

    elif "Overbought" in status:
        return "🔴 Overbought"

    else:
        return "⚪ Normal"


def scan_week(min_price=None, max_price=None):

    engine = ScreenerEngine()
    results = engine.run(SAHAM_LIST, "swing_trade_week")

    rows = []

    for r in results:

        if r is None:
            continue

        try:

            last_price = float(r.last_price)
            rsi_val = float(r.rsi_value) if r.rsi_value else 50

            entry_low = float(r.entry_low)
            entry_high = float(r.entry_high)

            trend = r.score_breakdown.get("Trend", 0) if r.score_breakdown else 0
            volume = r.score_breakdown.get("Volume", 0) if r.score_breakdown else 0

            # 🔥 BAND ACCUMULATION (NEW)
            band = getattr(r, "band_accumulation", 0)

            gain_pct = (r.tp[1] - last_price) / last_price * 100

            # ================= BASIC FILTER =================
            if volume <= 0 or trend <= 0:
                continue

            if r.score < 50:
                continue

            if last_price > entry_high * 1.01:
                continue

            # ================= SETUP =================
            if rsi_val <= 45 and trend >= 20:
                setup = "🔥 Best Entry"
                setup_score = 3

            elif 45 < rsi_val <= 60:
                setup = "🟡 Pullback"
                setup_score = 2

            elif rsi_val > 60 and trend >= 20:
                setup = "🚀 Breakout"
                setup_score = 1

            else:
                continue

            # ================= ENTRY LOGIC =================
            in_entry = entry_low <= last_price <= entry_high

            near_entry = (
                last_price < entry_low and
                (entry_low - last_price) / entry_low <= 0.03
            )

            entry_ready = in_entry or near_entry

            # ================= ENTRY SCORE =================
            if in_entry:
                entry_score = 30
            elif near_entry:
                entry_score = 15
            else:
                entry_score = 0

            # ================= DISTANCE PENALTY =================
            distance = abs(last_price - entry_low) / entry_low
            distance_penalty = distance * 50

            # ================= FINAL RANK =================
            final_rank = (
                setup_score * 40 +
                entry_score +
                volume * 2 +
                trend * 1.5 +
                band * 15 +      # 🔥 BAND ACCUMULATION BOOST
                r.score * 0.5
            )

            final_rank -= distance_penalty

            if not entry_ready:
                final_rank -= 20

            rows.append({
                "Kode": r.kode,
                "Harga": int(last_price),
                "Score": int(r.score),

                "Setup": setup,
                "Trend": trend,

                "RSI Value": round(rsi_val, 2),
                "RSI Status": format_rsi_status(r.rsi_status),

                "Volume": volume,
                "Band": band,  # 🔥 new column

                "Near Entry": entry_ready,

                "Entry": f"{int(entry_low)} - {int(entry_high)}",
                "TP": f"{int(r.tp[0])} / {int(r.tp[1])}",
                "SL": int(r.sl),

                "Gain (%)": round(gain_pct, 2),
                "Rank": final_rank
            })

        except Exception as e:
            print("ERROR PARSING:", r.kode, e)
            continue

    df = pd.DataFrame(rows)

    if df.empty:
        return df, df

    # ================= FILTER HARGA =================
    if min_price is not None and max_price is not None:
        df = df[(df["Harga"] >= min_price) & (df["Harga"] <= max_price)]

    # ================= SPLIT =================
    df_pullback = df[df["Setup"].isin(["🔥 Best Entry", "🟡 Pullback"])].copy()
    df_oversold = df[df["RSI Status"].str.contains("Oversold")].copy()

    df_oversold = df_oversold[~df_oversold["Kode"].isin(df_pullback["Kode"])]

    # ================= SORTING =================
    if not df_pullback.empty:
        df_pullback = (
            df_pullback
            .sort_values(
                by=["Rank", "Near Entry", "Volume", "Score"],
                ascending=[False, False, False, False]
            )
            .head(10)
            .reset_index(drop=True)
        )
        df_pullback.index += 1

    if not df_oversold.empty:
        df_oversold = (
            df_oversold
            .sort_values(
                by=["Rank", "Volume"],
                ascending=[False, False]
            )
            .head(10)
            .reset_index(drop=True)
        )
        df_oversold.index += 1

    # ================= CLEAN TABLE =================
    df_pullback = df_pullback.drop(columns=["Rank"], errors="ignore")
    df_oversold = df_oversold.drop(columns=["Rank"], errors="ignore")

    return df_pullback, df_oversold

# ==========================================================
# ===================== MAIN UI =============================
# ==========================================================
def render_screener():

    st.header("📊 CRUZER AI - SCREENER")

    if st.button("Reset Scanner"):
        st.session_state["scanner_state"] = {
            "alerted": {},
            "last_status": {}
        }

        st.success("Scanner berhasil di-reset")

    screener_type = st.selectbox(
        "Pilih Tipe",
        ["Swing Trade (Day)", "Swing Trade (Week)"]
    )

    if "scanner_state" not in st.session_state:
        st.session_state["scanner_state"] = {
            "alerted": {},
            "last_status": {}
        }

    if st.button("🚀 Scan Market", use_container_width=True):

        with st.spinner("Scanning market..."):

            if screener_type == "Swing Trade (Day)":

                df, alerts, state = scan_day(st.session_state["scanner_state"])

                st.session_state["scanner_state"] = state
                st.session_state["mode"] = "day"
                st.session_state["data"] = df

            else:

                df_pullback, df_oversold = scan_week()

                st.session_state["mode"] = "week"
                st.session_state["pullback"] = df_pullback
                st.session_state["oversold"] = df_oversold

            st.session_state["time"] = datetime.now().strftime("%d %b %H:%M:%S")

    # ================= DISPLAY =================
    if "mode" not in st.session_state:
        return

    st.caption(f"⏱ Last Scan: {st.session_state.get('time','-')}")

    # ================= DAY =================
    if st.session_state["mode"] == "day":

        df = st.session_state["data"]

        if df.empty:
            st.warning("📭 Tidak ada data")
        else:
            st.dataframe(df, use_container_width=True)

    # ================= WEEK =================
    else:

        st.subheader("🔥 BEST PULLBACK (WEEK)")

        df_pullback = st.session_state.get("pullback", pd.DataFrame())

        if df_pullback.empty:
            st.warning("📭 Tidak ada pullback bagus")
        else:
            st.dataframe(df_pullback, use_container_width=True)

        st.divider()

        st.subheader("🔵 OVERSOLD REVERSAL (WEEK)")

        df_oversold = st.session_state.get("oversold", pd.DataFrame())

        if df_oversold.empty:
            st.info("Tidak ada saham oversold")
        else:
            st.dataframe(df_oversold, use_container_width=True)

# ==========================================================
# =================== STOCK ANALYSIS =======================
# ==========================================================
def calculate_smart_money(df):
    df = df.copy()

    df["Value"] = df["CLOSE"] * df["VOLUME"]

    df["Smart"] = df["Value"].where(df["CLOSE"] > df["OPEN"], 0)
    df["Bad"] = df["Value"].where(df["CLOSE"] < df["OPEN"], 0)

    df["Bad"] = -df["Bad"]
    df["Clean"] = df["Smart"] + df["Bad"]

    df["Gain (%)"] = df["CLOSE"].pct_change() * 100

    return df.tail(10)

# ===================== GAP ENGINE =====================
def calculate_gap_fill_rate(df):
    gaps = []

    for i in range(1, len(df)):
        prev_high = df.iloc[i - 1]["HIGH"]

        if df.iloc[i]["OPEN"] > prev_high:

            filled = False

            for j in range(i, min(i + 10, len(df))):
                if df.iloc[j]["LOW"] <= prev_high:
                    filled = True
                    break

            gaps.append(filled)

    if not gaps:
        return 0

    return sum(gaps) / len(gaps) * 100

def render_stock_analysis():
    from app.utils.market_data import load_price_data
    from app.utils.analysis_engine import analyze_single_stock, round_to_tick
    from app.config.saham_profile import SAHAM_PROFILE
    from app.utils.sector_utils import get_sector_badge
    from datetime import datetime

    st.header("📊 Stock Analysis")
    st.caption("Analisa mandiri satu saham (independen dari screener)")

    # =========================
    # INPUT
    # =========================
    col1, col2 = st.columns([2, 1])

    with col1:
        kode = st.selectbox(
            "Kode Saham",
            SAHAM_LIST,
            key="analysis_kode",
        )

    with col2:
        timeframe = st.selectbox(
            "Timeframe",
            ["Weekly"],
            key="analysis_tf",
        )

    # =========================
    # RESET FUNCTION
    # =========================
    def reset_analysis_state():
        for k in ["analysis_result", "news_result", "analyzed"]:
            st.session_state.pop(k, None)

    if st.session_state.get("last_analysis_kode") != kode:
        reset_analysis_state()
        st.session_state.last_analysis_kode = kode

    if st.session_state.get("last_analysis_tf") != timeframe:
        reset_analysis_state()
        st.session_state.last_analysis_tf = timeframe

    # =========================
    # SAHAM PROFILE
    # =========================
    company_name = SAHAM_PROFILE.get(kode, kode)
    sector_emoji, sector_name = get_sector_badge(kode)

    st.markdown(f"### {sector_emoji} {company_name} ({kode})")
    st.caption(f"Sektor: {sector_name}")

    # ===================== ANALYZE =====================
    if st.button("🔍 Analyze Stock"):
        df = load_price_data(kode)

        if df.empty:
            st.warning("Data harga tidak tersedia.")
        else:
            result = analyze_single_stock(df)
            news_result = fetch_stock_news(kode)

            minor_support = calc_minor_support(df)
            result["minor_support"] = minor_support

            st.session_state["analysis_result"] = result
            st.session_state["news_result"] = news_result
            st.session_state["analysis_timeframe"] = timeframe
            st.session_state["analysis_df"] = df

    # ===================== DISPLAY =====================
    if "analysis_result" not in st.session_state:
        return

    result = st.session_state["analysis_result"]
    news_result = st.session_state["news_result"]

    # ===================== MARKET CONDITION =====================
    st.subheader("🧭 Market Condition")

    df_price = st.session_state.get("analysis_df", None)

    if df_price is None or df_price.empty:
        st.info("Data tidak tersedia")
        st.stop()

    # ===================== HELPER =====================
    def clean_price_df(df):
        if df is None:
            return None

        df = df.copy()

        # flatten multi index
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [" ".join(col).upper() for col in df.columns]
        else:
            df.columns = [str(c).upper().strip() for c in df.columns]

        # PRIORITAS kolom CLOSE
        priority_cols = ["CLOSE", "ADJ CLOSE", "CLOSE PRICE"]

        close_col = None
        for p in priority_cols:
            for col in df.columns:
                if p in col:
                    close_col = col
                    break
            if close_col:
                break

        if close_col is None:
            st.error(f"Tidak ditemukan kolom CLOSE di: {df.columns.tolist()}")
            return None

        df = df.rename(columns={close_col: "CLOSE"})
        df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")
        df = df.dropna(subset=["CLOSE"])

        # sort index
        df = df.sort_index()

        return df


    # ===================== CLEAN =====================
    df_mc = clean_price_df(df_price)

    if df_mc is None or df_mc.empty:
        st.error("Kolom CLOSE tidak ditemukan di data saham")
        st.stop()

    # ===================== CORE =====================
    last_price = df_mc["CLOSE"].iloc[-1]

    # ===================== MOVING AVERAGE =====================
    if len(df_mc) >= 200:
        ma200 = df_mc["CLOSE"].rolling(200).mean().iloc[-1]
        std = df_mc["CLOSE"].rolling(200).std().iloc[-1]
        ma50 = df_mc["CLOSE"].rolling(50).mean().iloc[-1]
    else:
        ma200 = std = ma50 = None

    # ===================== ATH / ATL =====================
    ath = df_mc["CLOSE"].max()
    atl = df_mc["CLOSE"].min()

    # posisi harga terhadap ATH-ATL
    if ath != atl:
        position_pct = (last_price - atl) / (ath - atl)
    else:
        position_pct = 0.5

    # ===================== Z-SCORE =====================
    if ma200 and std and std != 0:
        z_score = (last_price - ma200) / std
    else:
        z_score = None

    # ===================== PERCENTILE RANGE =====================
    low_pct = df_mc["CLOSE"].quantile(0.2)
    high_pct = df_mc["CLOSE"].quantile(0.8)

    # ===================== HYBRID FAIR VALUE (FIXED) =====================

    if ma200 and std:
        fair_low_stat = ma200 - std
        fair_high_stat = ma200 + std

        # blend dengan percentile (bukan max/min keras)
        fair_low = (fair_low_stat * 0.6) + (low_pct * 0.4)
        fair_high = (fair_high_stat * 0.6) + (high_pct * 0.4)

        # clamp biar gak keluar dari ATH/ATL
        fair_low = max(fair_low, atl)
        fair_high = min(fair_high, ath)

    else:
        fair_low = low_pct
        fair_high = high_pct

    # ===================== TREND =====================
    trend = result.get("trend", "-")
    st.markdown(f"### {trend}")

    # ===================== PRICE INFO =====================
    c1, c2 = st.columns(2)

    with c1:
        st.metric("Last Price", f"Rp {int(last_price):,}".replace(",", "."))

    with c2:
        if ma200:
            st.metric("Fair Value (MA200)", f"Rp {int(ma200):,}".replace(",", "."))
        else:
            st.metric("Fair Value", "-")

    # ===================== RANGE =====================
    st.caption(
        f"Range Wajar: Rp {int(fair_low):,} - Rp {int(fair_high):,}".replace(",", ".")
    )

    # ===================== VALUATION STATUS =====================
    if z_score is not None:
        if z_score < -1:
            fv_status = "🟢 Undervalued"
        elif z_score > 1:
            fv_status = "🔴 Overvalued"
        else:
            fv_status = "⚖️ Fair"
    else:
        fv_status = "-"

    st.markdown(f"**Status: {fv_status}**")

    # ===================== STRUCTURE =====================
    if ma50 and ma200:
        if ma50 > ma200:
            st.success("📈 Bullish structure (MA50 > MA200)")
            structure = "bullish"
        else:
            st.warning("📉 Bearish structure (MA50 < MA200)")
            structure = "bearish"
    else:
        structure = "unknown"

    # ===================== SUPPORT RESISTANCE =====================
    st.subheader("📉 Support & Resistance")

    df_price = st.session_state.get("analysis_df")
    last_price = result["last_price"]

    major_support = result["support"]
    minor_support = calc_minor_support(df_price)

    # 🔹 NEW: Micro support (super dekat)
    micro_support = int(df_price["Low"].tail(7).min())

    supports = []

    if micro_support is not None:
        supports.append(("Micro", micro_support))
    if minor_support is not None:
        supports.append(("Minor", minor_support))
    if major_support is not None:
        supports.append(("Major", major_support))

    # Urutkan dari yang paling dekat ke harga sekarang
    supports_sorted = sorted(
        supports,
        key=lambda x: abs(last_price - x[1])
    )

    rows = []

    if len(supports_sorted) >= 1:
        rows.append(
            (
                "Support (Near)",
                f"Rp {int(supports_sorted[0][1]):,} ({supports_sorted[0][0]})".replace(",", "."),
            )
        )

    if len(supports_sorted) >= 2:
        rows.append(
            (
                "Support (Mid)",
                f"Rp {int(supports_sorted[1][1]):,} ({supports_sorted[1][0]})".replace(",", "."),
            )
        )

    if len(supports_sorted) >= 3:
        rows.append(
            (
                "Support (Far)",
                f"Rp {int(supports_sorted[2][1]):,} ({supports_sorted[2][0]})".replace(",", "."),
            )
        )

    rows.append(
        (
            "Resistance",
            f"Rp {int(result['resistance']):,}".replace(",", "."),
        )
    )

    sr_df = pd.DataFrame(rows, columns=["Level", "Price"])
    st.table(sr_df.set_index("Level"))


    # ===================== ENTRY PLAN =====================
    st.subheader("🎯 Entry Plan")

    # Support yang sudah diurutkan sebelumnya
    near_support = supports_sorted[0][1]

    deep_support = None
    if len(supports_sorted) >= 2:
        deep_support = supports_sorted[1][1]
    else:
        deep_support = supports_sorted[0][1]

    # 🔹 ENTRY NEAR (agresif)
    entry_near_low = round_to_tick(near_support * 0.995)
    entry_near_high = round_to_tick(near_support * 1.015)

    # 🔹 ENTRY DEEP (lebih sabar)
    entry_deep_low = round_to_tick(deep_support * 0.99)
    entry_deep_high = round_to_tick(deep_support * 1.02)

    entry_df = pd.DataFrame(
        {
            "Parameter": [
                "Entry Near (Pullback)",
                "Entry Deep (Discount)",
                "Risk",
            ],
            "Value": [
                f"Rp {entry_near_low:,} – Rp {entry_near_high:,}".replace(",", "."),
                f"Rp {entry_deep_low:,} – Rp {entry_deep_high:,}".replace(",", "."),
                f"{result['risk_pct']} %",
            ],
        }
    )

    st.table(entry_df.set_index("Parameter"))

    # ===================== SMART MONEY FLOW (FINAL) =====================
    st.subheader("💰 Smart Money Flow (10D)")

    df_price = st.session_state.get("analysis_df", None)

    # ===================== HELPER =====================
    def format_money(x):
        if pd.isna(x):
            return "-"
        x = float(x)
        sign = "-" if x < 0 else ""
        x = abs(x)

        if x >= 1_000_000_000_000:
            return f"{sign}{x/1_000_000_000_000:.2f} T"
        elif x >= 1_000_000_000:
            return f"{sign}{x/1_000_000_000:.2f} B"
        elif x >= 1_000_000:
            return f"{sign}{x/1_000_000:.2f} M"
        else:
            return f"{sign}{int(x):,}".replace(",", ".")

    def format_number(x):
        return f"{int(x):,}".replace(",", ".")

    # ===================== VALIDATION =====================
    if df_price is None or df_price.empty:
        st.info("Data tidak tersedia")
    else:
        df = df_price.copy()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]

        df.columns = [str(c).upper().strip() for c in df.columns]

        # ===================== COLUMN MAP =====================
        col_map = {}
        for col in df.columns:
            if "OPEN" in col: col_map["OPEN"] = col
            elif "CLOSE" in col: col_map["CLOSE"] = col
            elif "VOLUME" in col: col_map["VOLUME"] = col
            elif "HIGH" in col: col_map["HIGH"] = col
            elif "LOW" in col: col_map["LOW"] = col

        df = df.rename(columns={
            col_map["OPEN"]: "OPEN",
            col_map["CLOSE"]: "CLOSE",
            col_map["VOLUME"]: "VOLUME",
            **({col_map["HIGH"]: "HIGH"} if "HIGH" in col_map else {}),
            **({col_map["LOW"]: "LOW"} if "LOW" in col_map else {})
        })

        for col in ["OPEN", "CLOSE", "VOLUME"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["OPEN", "CLOSE", "VOLUME"])

        if df.empty:
            st.info("Data kosong")
            st.stop()

        # ===================== CORE =====================
        df["VALUE"] = df["CLOSE"] * df["VOLUME"]

        # ===================== AVP =====================
        if "HIGH" in df.columns and "LOW" in df.columns:
            df["AVP"] = (df["OPEN"] + df["HIGH"] + df["LOW"] + df["CLOSE"]) / 4
        else:
            df["AVP"] = (df["OPEN"] + df["CLOSE"]) / 2

        # ===================== SMART MONEY (SMOOTH FIX 🔥) =====================
        spread = (df["HIGH"] - df["LOW"]).replace(0, 1)

        close_pos = (df["CLOSE"] - df["LOW"]) / spread

        # 🔥 CLAMP BIAR GAK EKSTREM
        close_pos = close_pos.clip(0.2, 0.8)

        df["SMART"] = df["VALUE"] * close_pos
        df["BAD"] = df["VALUE"] * (1 - close_pos)
        df["BAD"] = -df["BAD"]

        df["CLEAN"] = df["SMART"] + df["BAD"]

        df["GAIN (%)"] = df["CLOSE"].pct_change() * 100

        # ===================== RCV =====================
        df["RCV"] = (df["CLEAN"] / df["VALUE"]) * 100
        df["RCV"] = df["RCV"].fillna(0).clip(-100, 100).round(0)

        # ===================== SIGNAL =====================
        def get_signal(rcv):
            if rcv > 50:
                return "🚀"
            elif rcv > 20:
                return "🔥"
            elif rcv > 0:
                return "🟢"
            elif rcv > -20:
                return "⚠️"
            else:
                return "🔴"

        df["SIGNAL"] = df["RCV"].apply(get_signal)

        # ===================== STREAK =====================
        df["ACC"] = df["CLEAN"] > 0
        df["STREAK"] = df["ACC"].astype(int).groupby((~df["ACC"]).cumsum()).cumsum()

        sm_df = df.tail(10)

        # ===================== SUMMARY =====================
        total_value = sm_df["VALUE"].sum()
        total_smart = sm_df["SMART"].sum()
        total_bad = sm_df["BAD"].sum()
        total_clean = sm_df["CLEAN"].sum()

        power = (total_smart / total_value * 100) if total_value > 0 else 0

        status = "🟢 BUYER DOMINANT" if total_clean > 0 else "🔴 SELLER DOMINANT"

        c1, c2, c3 = st.columns(3)

        with c1:
            st.metric("Smart Money", f"{total_smart/1e9:.2f} B")
        with c2:
            st.metric("Clean Money", f"{total_clean/1e9:.2f} B")
        with c3:
            st.metric("Power", f"{power:.1f}%")

        st.markdown(f"**Status: {status}**")

        # ===================== TABLE =====================
        display_df = sm_df.copy()

        display_df["Date"] = display_df.index.strftime("%d-%m-%Y")
        display_df["Tx"] = display_df["VOLUME"].apply(format_number)

        display_df["Value"] = display_df["VALUE"].apply(format_money)
        display_df["Smart"] = display_df["SMART"].apply(format_money)
        display_df["Bad"] = display_df["BAD"].apply(format_money)
        display_df["Clean"] = display_df["CLEAN"].apply(format_money)

        display_df["Gain%"] = display_df["GAIN (%)"].apply(lambda x: f"{x:.2f}%")
        display_df["AVP"] = display_df["AVP"].astype(int)
        display_df["RCV"] = display_df["RCV"].astype(int)
        display_df["📊"] = display_df["SIGNAL"]

        display_df = display_df[
            ["Date","Tx","Value","AVP","Gain%","Smart","Bad","Clean","RCV","📊"]
        ]

        display_df = display_df.reset_index(drop=True)
        display_df.index += 1
        display_df.index.name = "No"

        st.dataframe(display_df, use_container_width=True)

        # ===================== 10D SUMMARY INSIGHT =====================
        # st.subheader("🧠 Smart Money Insight (10D)")

        # ===== FULL 10 DAYS =====
        data10 = sm_df.copy()

        # ===== METRICS =====
        avg_rcv_10 = data10["RCV"].mean()
        positive_days_10 = (data10["CLEAN"] > 0).sum()

        total_clean_10 = data10["CLEAN"].sum()
        total_value_10 = data10["VALUE"].sum()

        flow_strength_10 = (total_clean_10 / total_value_10 * 100) if total_value_10 != 0 else 0

        # ===== TREND =====
        first_half = data10.head(5)["RCV"].mean()
        last_half = data10.tail(5)["RCV"].mean()

        trend_up = last_half > first_half

        # ===== INFO (SIMPLE & CLEAN) =====
        st.write(
            f"RCV (10D): **{avg_rcv_10:.0f}** "
            f"({'⬆️' if trend_up else '⬇️'}) • "
            f"Win Rate: **{positive_days_10}/10 hari**"
        )

        st.caption(f"Flow Strength (10D): {flow_strength_10:.1f}%")

        # ===== ACTION (SIMPLIFIED) =====
        if avg_rcv_10 > 50 and trend_up:
            st.success("🚀 Strong Accumulation (Uptrend)")
        elif avg_rcv_10 > 20:
            st.info("🔥 Accumulation")
        elif avg_rcv_10 > 0:
            st.warning("🟡 Early Accumulation")
        else:
            st.error("🔴 Distribution Dominant")

    # ===================== CYCLE PROJECTION (TIME ONLY CLEAN) =====================

    st.subheader("📅 Cycle Projection")

    today = datetime.now().date()

    cycle = result.get("cycle") if "result" in locals() else None

    if not cycle:
        st.warning("Data cycle tidak tersedia")
    else:

        # ===================== HELPER =====================
        def safe_date(key):
            try:
                return datetime.strptime(cycle.get(key, ""), "%Y-%m-%d").date()
            except:
                return None

        def fmt(d):
            return d.strftime("%d-%b-%Y") if d else "-"

        def fmt_range(s, e):
            return f"{fmt(s)} - {fmt(e)}"

        def days_to(d):
            return (d - today).days if d else None

        def in_range(start, end):
            return start and end and start <= today <= end

        # ===================== PARSE =====================
        last_low = safe_date("last_low")

        near_low_start = safe_date("next_low_start")
        near_low_end = safe_date("next_low_end")

        next_low_start = safe_date("second_low_start")
        next_low_end = safe_date("second_low_end")

        near_high_start = safe_date("next_high_start")
        near_high_end = safe_date("next_high_end")

        next_high_start = safe_date("second_high_start")
        next_high_end = safe_date("second_high_end")

        # ===================== CURRENT POSITION =====================
        if in_range(near_low_start, near_low_end):
            st.success("🟢 Near Cycle Low")
            st.caption("➡️ Bias: Area akumulasi (berdasarkan waktu)")

        elif in_range(near_high_start, near_high_end):
            st.warning("🔴 Near Cycle High")
            st.caption("➡️ Bias: Area distribusi / take profit")

        else:
            events = [
                ("Cycle Low", near_low_start),
                ("Cycle High", near_high_start),
                ("Next Cycle Low", next_low_start),
                ("Next Cycle High", next_high_start),
            ]

            future_events = [(n, d) for n, d in events if d and d >= today]

            if future_events:
                name, date_event = min(
                    future_events,
                    key=lambda x: (x[1] - today).days
                )

                d = days_to(date_event)

                if "Low" in name:
                    st.info(f"⏳ Menuju {name} ({d} hari lagi)")
                    st.caption("➡️ Bias: Mendekati area akumulasi")

                else:
                    st.info(f"📈 Menuju {name} ({d} hari lagi)")
                    st.caption("➡️ Bias: Trend bisa lanjut, tapi waspada puncak")

            else:
                st.caption("⚖️ Tidak ada event cycle ke depan")

        # ===================== TABLE =====================
        st.markdown("### 📉 Cycle Low Window")

        low_df = pd.DataFrame({
            "Parameter": [
                "Last Major Low",
                "Near Cycle Low",
                "Next Cycle Low",
            ],
            "Value": [
                fmt(last_low),
                fmt_range(near_low_start, near_low_end),
                fmt_range(next_low_start, next_low_end),
            ],
        })

        st.table(low_df.set_index("Parameter"))

        st.markdown("### 📈 Cycle High Window")

        high_df = pd.DataFrame({
            "Parameter": [
                "Near High Window",
                "Next High Window",
            ],
            "Value": [
                fmt_range(near_high_start, near_high_end),
                fmt_range(next_high_start, next_high_end),
            ],
        })

        st.table(high_df.set_index("Parameter"))

    # ===================== NEWS =====================
    st.subheader("📰 News & Sentiment")
    sent = news_result.get("sentiment")

    if sent == "SPECULATIVE":
        st.warning("🎢 Speculative Event – volatilitas tinggi, high risk")
    elif sent == "NEGATIVE":
        st.warning("🟠 Sentimen berita negatif – risiko terdeteksi")
    elif sent == "POSITIVE":
        st.success("🟢 Sentimen berita positif")
    else:
        st.info("⚪ Tidak ada sentimen berita signifikan")

    if news_result.get("news"):
        for n in news_result["news"][:5]:
            if n.get("title") and n.get("link"):
                st.markdown(f"- [{n['title']}]({n['link']})")

    # ===================== INSIGHT =====================
    st.subheader("🧠 Insight")
    trend = result["trend"]

    if "Bullish" in trend and "Strong" in trend:
        insight_text = "Trend bullish kuat. Buy on pullback sangat ideal."
        st.success("⬆️ 🟢 " + insight_text)
    elif "Bullish" in trend and "Weak" in trend:
        insight_text = "Trend bullish tapi melemah. Entry bertahap & disiplin risk."
        st.warning("⬆️ 🟡 " + insight_text)
    elif "Bearish" in trend and "Strong" in trend:
        insight_text = "Trend bearish kuat. Hindari entry buy."
        st.error("⬇️ 🔴 " + insight_text)
    elif "Bearish" in trend and "Weak" in trend:
        insight_text = "Trend bearish mulai melemah. Tunggu reversal valid."
        st.warning("⬇️ 🟡 " + insight_text)
    else:
        insight_text = "Market sideways / transisi. Perlu konfirmasi tambahan."
        st.info("➡️ " + insight_text)



    # ===================== SEND TELEGRAM =====================
    st.subheader("📤 Share Analysis")

    SHARE_PASSWORD = st.secrets.get("SHARE_PASSWORD")

    input_pwd = st.text_input(
        "🔐 Password untuk kirim Telegram",
        type="password",
        key="share_pwd",
    )

    is_authorized = input_pwd == SHARE_PASSWORD

    if st.button(
        "📨 Send to Telegram",
        type="primary",
        use_container_width=True,
        disabled=not is_authorized,
    ):
        try:
            msg = render_stock_analysis_message(
                kode=st.session_state["analysis_kode"],
                timeframe=st.session_state["analysis_timeframe"],
                analysis=result,
                news_result=news_result,
                insight_text=insight_text,
                df_price=st.session_state["analysis_df"],   # ← WAJIB TAMBAH INI
            )

            send_message(msg)
            st.success("Terkirim ke Telegram ✅")
        except Exception as e:
            st.error("❌ Gagal kirim ke Telegram")
            st.code(str(e))

    if input_pwd and not is_authorized:
        st.error("❌ Password salah")

# ==========================================================
# =================== TRADING TRACKER ======================
# ==========================================================
from datetime import datetime, timedelta

def format_holding_days(days):
    if days is None or days == 0:
        return "0 hari"

    years = days // 365
    months = (days % 365) // 30
    remaining_days = (days % 365) % 30

    parts = []
    if years:
        parts.append(f"{years} thn -")
    if months:
        parts.append(f"{months} bln -")
    if remaining_days:
        parts.append(f"{remaining_days} hari")

    return " ".join(parts)


def render_trading_summary():
    if not require_trading_password():
        return

    st.header("📊 Trading Tracker - Summary")

    import os
    import pandas as pd

    DIV_FILE = "dividends.csv"

    if not os.path.exists(DIV_FILE):
        pd.DataFrame(columns=["trade_id", "date", "amount"]).to_csv(DIV_FILE, index=False)

    def load_dividends():
        return pd.read_csv(DIV_FILE)

    # ===================== BUY =====================
    with st.form("add_buy"):
        st.subheader("➕ Catat BUY")

        col1, col2 = st.columns(2)
        with col1:
            kode = st.selectbox("Kode Saham", SAHAM_LIST)
            buy_price = st.number_input("Harga Beli", min_value=0)
            buy_lot = st.number_input("Lot", min_value=1, value=1)

        with col2:
            buy_date = st.date_input("Tanggal Beli", value=date.today())
            note = st.text_input("Catatan (opsional)")

        submitted_buy = st.form_submit_button("Simpan BUY")

        if submitted_buy:
            if buy_price < 1:
                st.error("❌ Harga beli minimal 1")
            else:
                save_buy(kode, buy_date, buy_price, buy_lot, note)
                st.success("BUY dicatat ✅")
                st.rerun()

    # ===================== LOAD DATA =====================
    df_trades = enrich_trades(load_trades())
    df_div = load_dividends()

    st.subheader("📊 Trading Summary")

    if df_trades.empty:
        st.info("Belum ada trade yang tercatat.")
        return

    df_trades["Modal"] = df_trades["Buy"] * df_trades["Sisa Lot"] * 100

    total_modal = df_trades["Modal"].sum()
    total_capital = df_trades["PnL (Rp)"].sum()
    total_dividend = df_div["amount"].sum() if not df_div.empty else 0
    total_profit = total_capital + total_dividend
    profit_pct = (total_profit / total_modal * 100) if total_modal > 0 else 0

    def rp(x):
        return f"Rp {int(x):,}".replace(",", ".")

    # ===================== METRICS =====================
    c1, c2, c3 = st.columns(3)
    c1.metric("Modal", rp(total_modal))
    c2.metric("Capital Gain", rp(total_capital))
    c3.metric("Dividend", rp(total_dividend))

    c4, c5, spacer = st.columns(3)
    c4.metric("Total Profit", rp(total_profit))
    c5.metric("Profit %", f"{profit_pct:.1f}%")
    spacer.empty()

    st.divider()

    # ===================== TRADING HISTORY =====================
    st.subheader("📋 Trading History")

    table_df = df_trades.copy()

    # Nama perusahaan
    table_df["Nama"] = table_df["Kode"].apply(
        lambda x: SAHAM_PROFILE.get(x, x)
    )

    # Format tanggal
    table_df["Buy Date"] = table_df["buy_date"].apply(format_date_indo)
    table_df["Sell Date"] = table_df["Sell Date"].apply(format_date_indo)

    # Format holding days
    table_df["Holding Days"] = table_df["Holding Days"].apply(format_holding_days)

    # Sorting terbaru
    table_df = table_df.sort_values("buy_date", ascending=False)

    table_df = table_df[
        [
            "Kode",
            "Nama",
            "Buy Date",
            "Sell Date",
            "Buy",
            "Now",
            "Sisa Lot",
            "Status",
            "Holding Days",
            "PnL (Rp)",
            "PnL (%)",
        ]
    ]

    table_df["PnL (Rp)"] = table_df["PnL (Rp)"].apply(rp)
    table_df["PnL (%)"] = table_df["PnL (%)"].apply(lambda x: f"{x:.1f}%")

    st.dataframe(table_df, use_container_width=True, hide_index=True)

    # ===================== DIVIDEND HISTORY =====================
    st.subheader("💰 Dividend History")

    if df_div.empty:
        st.info("Belum ada dividen tercatat.")
    else:
        div_table = df_div.copy()

        # Ambil kode dari trade
        div_table["Kode"] = div_table["trade_id"].apply(
            lambda i: df_trades.loc[i, "Kode"] if i in df_trades.index else "-"
        )

        # Nama perusahaan
        div_table["Nama"] = div_table["Kode"].apply(
            lambda x: SAHAM_PROFILE.get(x, x)
        )

        div_table["date"] = pd.to_datetime(div_table["date"])

        # Sort: kode → tanggal terbaru
        div_table = div_table.sort_values(
            by=["Kode", "date"],
            ascending=[True, False]
        )

        # Format tanggal
        div_table["Tanggal"] = div_table["date"].apply(
            lambda x: x.strftime("%d-%b-%Y")
        )

        # Format rupiah
        div_table["Dividen"] = div_table["amount"].apply(rp)

        show_df = div_table[["Kode", "Nama", "Tanggal", "Dividen"]]

        st.dataframe(
            show_df,
            use_container_width=True,
            hide_index=True
        )

    # ===================== TAMBAH DIVIDEN =====================
    df = load_trades()
    st.subheader("➕ Tambah Dividen")

    def save_dividend(trade_id, date, amount):
        df = load_dividends()
        new_row = pd.DataFrame([{
            "trade_id": trade_id,
            "date": date,
            "amount": amount
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(DIV_FILE, index=False)

    idx_div = st.selectbox(
        "Pilih Trade",
        df.index,
        format_func=lambda i: f"{df.loc[i,'kode']} | {df.loc[i,'remaining_lot']} lot"
    )

    div_date = st.date_input("Tanggal Dividen", value=date.today())
    div_amount = st.number_input("Nominal Dividen (Rp)", min_value=0)

    if st.button("Simpan Dividen"):
        if div_amount < 1:
            st.error("❌ Nominal dividen minimal 1")
        else:
            save_dividend(idx_div, div_date, div_amount)
            st.session_state["div_success"] = True
            st.rerun()

    if "div_success" in st.session_state:
        st.success("✅ Dividen berhasil disimpan")
        del st.session_state["div_success"]



def render_manage_data():
    if not require_trading_password():
        return
    st.header("⚙️ Trading Tracker - Manage Data")

    import os
    import pandas as pd

    DIV_FILE = "dividends.csv"

    if not os.path.exists(DIV_FILE):
        pd.DataFrame(columns=["trade_id", "date", "amount"]).to_csv(DIV_FILE, index=False)

    def load_dividends():
        return pd.read_csv(DIV_FILE)

    def delete_dividends_by_trade(trade_id):
        df = load_dividends()
        df = df[df["trade_id"] != trade_id]
        df.to_csv(DIV_FILE, index=False)

    df_trades = enrich_trades(load_trades())
    df_div = load_dividends()

    # ===================== SELL =====================
    df = load_trades()
    df["remaining_lot"] = pd.to_numeric(df["remaining_lot"], errors="coerce").fillna(0).astype(int)
    open_trades = df[df["remaining_lot"] > 0]

    if not open_trades.empty:
        st.subheader("✏️ Jual")

        idx = st.selectbox(
            "Pilih posisi",
            open_trades.index,
            format_func=lambda i: f"{df.loc[i,'kode']} | {df.loc[i,'remaining_lot']} lot",
        )

        remaining_lot = int(df.loc[idx, "remaining_lot"])

        sell_price = st.number_input("Harga Jual", min_value=0)
        sell_lot = st.number_input("Lot Dijual", min_value=0, value=0)
        sell_date = st.date_input("Tanggal Jual", value=date.today())

        if st.button("Jual"):
            errors = []

            if sell_price < 1:
                errors.append("Harga jual minimal 1")

            if sell_lot < 1:
                errors.append("Lot jual minimal 1")

            if sell_lot > remaining_lot:
                errors.append(f"Lot jual tidak boleh lebih dari {remaining_lot}")

            if errors:
                for e in errors:
                    st.error(f"❌ {e}")
            else:
                save_sell(idx, sell_date, sell_price, sell_lot)
                st.success("Transaksi jual tercatat")
                st.rerun()

    # ===================== DELETE TRADE =====================
    st.divider()
    st.subheader("🗑️ Hapus Trade")

    selected_idx = st.selectbox(
        "Pilih trade",
        df_trades.index,
        format_func=lambda i: f"{df_trades.loc[i,'Kode']} | {df_trades.loc[i,'Buy']}"
    )

    if st.button("Hapus Trade"):
        st.session_state["confirm_delete_trade"] = selected_idx

    if "confirm_delete_trade" in st.session_state:
        idx_confirm = st.session_state["confirm_delete_trade"]

        st.warning("⚠️ Anda yakin ingin menghapus trade ini beserta semua dividennya?")

        col1, col2 = st.columns(2)

        if col1.button("❌ Batal"):
            del st.session_state["confirm_delete_trade"]

        if col2.button("🗑️ Ya, Hapus Permanen"):
            delete_trade(idx_confirm)
            delete_dividends_by_trade(idx_confirm)
            del st.session_state["confirm_delete_trade"]
            st.success("Trade & dividen terkait berhasil dihapus")
            st.rerun()

    # ===================== DELETE DIVIDEND =====================
    st.subheader("🧾 Hapus Dividen")

    if df_div.empty:
        st.info("Belum ada dividen untuk dihapus.")
    else:
        div_options = df_div.reset_index()

        def format_div_option(i):
            trade_id = div_options.loc[i, "trade_id"]

            if trade_id in df_trades.index:
                kode = df_trades.loc[trade_id, "Kode"]
            else:
                kode = "(Trade sudah dihapus)"

            tanggal = div_options.loc[i, "date"]
            amount = f"Rp {int(div_options.loc[i,'amount']):,}".replace(",", ".")

            return f"{kode} | {tanggal} | {amount}"

        selected_div = st.selectbox(
            "Pilih dividen",
            div_options["index"],
            format_func=format_div_option
        )

        if st.button("Hapus Dividen"):
            st.session_state["confirm_delete_div"] = selected_div

        if "confirm_delete_div" in st.session_state:
            idx_div_confirm = st.session_state["confirm_delete_div"]

            st.warning("⚠️ Anda yakin ingin menghapus dividen ini?")

            col1, col2 = st.columns(2)

            if col1.button("❌ Batal", key="cancel_div"):
                del st.session_state["confirm_delete_div"]

            if col2.button("🗑️ Ya, Hapus", key="confirm_div"):
                df_div2 = load_dividends()
                df_div2 = df_div2.drop(idx_div_confirm)
                df_div2.to_csv(DIV_FILE, index=False)

                del st.session_state["confirm_delete_div"]
                st.success("Dividen berhasil dihapus")
                st.rerun()

# ==========================================================
# ======================= ROUTER ===========================
# ==========================================================
menu = st.sidebar.radio(
    "📂 Menu",
    [
        "🔍 Screener",
        "📊 Stock Analysis",
        "💰 Dividend Screener",
        "📒 Trading Tracker - Summary",
        "⚙️ Trading Tracker - Manage"
    ]
)

if menu == "🔍 Screener":
    render_screener()

elif menu == "📊 Stock Analysis":
    render_stock_analysis()

elif menu == "💰 Dividend Screener":
    render_dividend_screener()

elif menu == "📒 Trading Tracker - Summary":
    render_trading_summary()

elif menu == "⚙️ Trading Tracker - Manage":
    render_manage_data()

# ==========================================================
# FOOTER
# ==========================================================
st.markdown("---")
st.caption("© 2026 Cruzer AI • Stock Screener Engine. All rights reserved.")