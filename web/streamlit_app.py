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
# ======================= SCREENER =========================
# ==========================================================
def render_screener():
    SCREENER_LABEL_MAP = {
        "Swing Trade (Week)": "swing_trade_week",
        "Swing Trade (Day)": "swing_trade_day",
        "Breakout (BSJP)": "breakout",
    }

    # MAP ENGINE MODE → TELEGRAM SETUP LABEL (dipertahankan untuk kompatibilitas lama)
    SETUP_LABEL_MAP = {
        "swing_trade_week": "Swing Setup (Week)",
        "swing_trade_day": "Swing Setup (Day)",
        "breakout": "BSJP Setup",
    }

    SCREENER_GUIDE = {
        "swing_trade_day": """
🟡 **Swing Trade DAY** 

• Target: 1–3% 

• Timeframe: Intraday 

• Cocok saat market aktif 

• Entry: Pagi / entry zone 

• Exit: Sore hari
""",
        "swing_trade_week": """
🟢 **Swing Trade WEEK** 

• Target: 5–15% 

• Timeframe: Beberapa hari 

• Cocok saat market sideways sehat 

• Entry: Entry zone / Pullback 

• Exit: Bertahap
""",
        "breakout": """
🔴 **Breakout (BSJP)** 

• Target: Follow-through cepat 

• Timeframe: Sore → pagi 

• Entry: 14.45–15.00 WIB 

• Exit: Gap up / resistance berikutnya
""",
    }

    # ===== INIT SESSION STATE =====
    for key, default in {
        "min_score": 50,
        "min_gain": 2,
        "price_range": (0, 10_000),
        "last_screener": None,
        "scanned_screener": None,
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default

    # ===== SIDEBAR =====
    st.sidebar.header("⚙️ Screener Settings")

    screener_label = st.sidebar.selectbox(
        "Pilih Tipe Screener",
        options=list(SCREENER_LABEL_MAP.keys()),
    )
    screener_type = SCREENER_LABEL_MAP[screener_label]

    with st.expander("ℹ️ Panduan Penggunaan Screener"):
        st.markdown(SCREENER_GUIDE[screener_type])

    # reset hasil jika ganti screener
    if st.session_state.last_screener != screener_type:
        st.session_state.pop("results", None)
        st.session_state.scanned_screener = None
        st.session_state.last_screener = screener_type

    st.session_state.min_score = st.sidebar.slider(
        "Minimum Score", 0, 100, st.session_state.min_score
    )
    st.session_state.min_gain = st.sidebar.slider(
        "Minimum Expected Gain (%)", 0, 15, st.session_state.min_gain
    )
    st.session_state.price_range = st.sidebar.slider(
        "Filter Harga (Rp)",
        0,
        30_000,
        st.session_state.price_range,
        step=500,
    )

    min_score = st.session_state.min_score
    min_gain = st.session_state.min_gain
    min_price, max_price = st.session_state.price_range

    # ================= SCAN =================
    if st.button("🔍 Scan Market", use_container_width=True):
        with st.spinner("🔍 Scanning market... Mohon tunggu"):
            engine = ScreenerEngine()
            st.session_state["results"] = engine.run(SAHAM_LIST, screener_type)
            st.session_state.scanned_screener = screener_type

        st.success("✅ Scan market selesai")

    # ================= DISPLAY =================
    if not (
        "results" in st.session_state
        and st.session_state.scanned_screener == screener_type
    ):
        return

    entry_now, watchlist = [], []

    for r in st.session_state["results"]:
        last_price = float(r.last_price)
        gain_pct = (r.tp[1] - last_price) / last_price * 100

        # GLOBAL FILTER
        if not (min_price <= last_price <= max_price):
            continue
        if r.score < min_score:
            continue
        if gain_pct < min_gain:
            continue

        pos = price_position(last_price, r.entry_low, r.entry_high)
        trend_score = r.score_breakdown.get("Trend", 0)
        volume_score = r.score_breakdown.get("Volume", 0)

        row = {
            "Kode": r.kode,
            "Harga": int(last_price),
            "Score": r.score,
            "Trend": trend_score,
            "RSI": r.score_breakdown.get("RSI", 0),
            "Volume": volume_score,
            "Entry": format_range(r.entry_low, r.entry_high),
            "TP": format_tp(r.tp),
            "SL": format_price(r.sl),
            "Gain (%)": f"{gain_pct:.2f}",
        }

        if screener_type == "breakout":
            if (
                r.score >= min_score
                and trend_score >= 20
                and volume_score >= 10
                and near_resistance(last_price, r.entry_high)
            ):
                entry_now.append(row)
            else:
                watchlist.append(row)

        elif screener_type == "swing_trade_day":
            if (
                r.score >= min_score
                and gain_pct >= min_gain
                and (pos == "INSIDE" or near_entry(last_price, r.entry_high))
            ):
                entry_now.append(row)
            else:
                watchlist.append(row)

        else:
            if pos == "INSIDE" and r.score >= min_score and gain_pct >= min_gain:
                entry_now.append(row)
            else:
                watchlist.append(row)

    # ================= RENDER CAN ENTRY =================
    st.subheader("🟢 CAN ENTRY")

    df_entry = pd.DataFrame(entry_now)

    if df_entry.empty:
        st.info(
            "📭 Belum ada saham yang memenuhi kriteria **CAN ENTRY**.\n\n"
            "📌 Tunggu konfirmasi harga / volume, atau sesuaikan parameter screener."
        )
    else:
        df_entry = (
            df_entry.sort_values(by=["Score", "Harga"], ascending=[False, False])
            .reset_index(drop=True)
        )
        df_entry.index = df_entry.index + 1
        render_df(df_entry)

    # ===== BUTTON TELEGRAM (SETELAH TABEL) =====
    st.subheader("📤 Share CAN ENTRY")

    # ambil password (secrets → env fallback)
    def get_share_password():
        try:
            return st.secrets.get("SHARE_PASSWORD")
        except Exception:
            return os.getenv("SHARE_PASSWORD")

    SHARE_PASSWORD = get_share_password()

    input_pwd = st.text_input(
        "🔐 Password untuk kirim CAN ENTRY",
        type="password",
        key="share_pwd_can_entry",
    )

    # cek apakah ada CAN ENTRY
    has_entry = len(entry_now) > 0

    is_authorized = input_pwd == SHARE_PASSWORD and has_entry

    if st.button(
        "📩 Send CAN ENTRY to Telegram",
        type="primary",
        use_container_width=True,
        key="btn_send_can_entry_telegram",
        disabled=not is_authorized,
    ):
        bot_token = (
            st.secrets.get("TELEGRAM_BOT_TOKEN", None)
            if hasattr(st, "secrets")
            else None
        ) or os.getenv("TELEGRAM_BOT_TOKEN")

        chat_id = (
            st.secrets.get("TELEGRAM_CHAT_ID", None)
            if hasattr(st, "secrets")
            else None
        ) or os.getenv("TELEGRAM_CHAT_ID")

        if not bot_token or not chat_id:
            st.error("Telegram belum dikonfigurasi (Secrets / ENV belum ada)")
        else:
            try:
                message = render_telegram(results=entry_now)
                send_message(message)
                st.success("CAN ENTRY terkirim ke Telegram ✅")
            except Exception as e:
                st.error("❌ Gagal kirim ke Telegram")
                st.code(str(e))


    if not has_entry:
        st.info("📭 Tidak ada CAN ENTRY untuk dikirim ke Telegram.")

    elif input_pwd and input_pwd != SHARE_PASSWORD:
        st.error("❌ Password salah")


    # ================= RENDER WATCHLIST =================
    st.subheader("🟡 WATCHLIST")

    df_watchlist = pd.DataFrame(watchlist)

    if df_watchlist.empty:
        st.info(
            "📭 Tidak ada saham yang masuk **WATCHLIST** saat ini.\n\n"
            "ℹ️ Biasanya terjadi saat market sepi atau filter cukup ketat."
        )
    else:
        df_watchlist = (
            df_watchlist.sort_values(by=["Score", "Harga"], ascending=[False, False])
            .reset_index(drop=True)
        )
        df_watchlist.index = df_watchlist.index + 1
        render_df(df_watchlist)


# ==========================================================
# =================== STOCK ANALYSIS =======================
# ==========================================================
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
    c1, c2 = st.columns(2)

    with c1:
        st.metric("Trend", result["trend"])

    with c2:
        st.metric(
            "Last Price",
            f"Rp {int(result['last_price']):,}".replace(",", "."),
        )

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


    # ===================== CYCLE PROJECTION =====================
    cycle = result.get("cycle")

    if cycle:
        st.subheader("📅 Cycle Projection")

        def format_date_only(date_str):
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%d-%b-%Y")

        def format_range(start, end):
            s = datetime.strptime(start, "%Y-%m-%d").strftime("%d-%b-%Y")
            e = datetime.strptime(end, "%Y-%m-%d").strftime("%d-%b-%Y")
            return f"{s} - {e}"

        # ===================== CYCLE LOW WINDOW =====================
        st.markdown("**📉 Cycle Low Window**")

        low_df = pd.DataFrame(
            {
                "Parameter": [
                    "Last Major Low",
                    "Near Cycle Low",
                    "Next Cycle Low",
                ],
                "Value": [
                    format_date_only(cycle["last_low"]),
                    format_range(cycle["next_low_start"], cycle["next_low_end"]),
                    format_range(cycle["second_low_start"], cycle["second_low_end"]),
                ],
            }
        )

        st.table(low_df.set_index("Parameter"))

        # ===================== CYCLE HIGH WINDOW =====================
        st.markdown("**📈 Cycle High Window**")

        high_df = pd.DataFrame(
            {
                "Parameter": [
                    "Near High Window",
                    "Next High Window",
                ],
                "Value": [
                    format_range(cycle["next_high_start"], cycle["next_high_end"]),
                    format_range(cycle["second_high_start"], cycle["second_high_end"]),
                ],
            }
        )

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