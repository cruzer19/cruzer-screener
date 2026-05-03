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

from app.stock_analysis.ui import render_stock_analysis

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

import pandas as pd

def format_rsi_status(status):

    if not status:
        return "⚪ Normal"

    if "Oversold" in status:
        return "🟢 Oversold"

    elif "Overbought" in status:
        return "🔴 Overbought"

    else:
        return "⚪ Normal"


# ==========================================================
# ===================== WEEK ================================
# ==========================================================
def scan_week(min_price=None, max_price=None):

    engine = ScreenerEngine()
    results = engine.run(SAHAM_LIST[:810], "swing_trade_week")

    rows = []

    for r in results:

        if r is None:
            continue

        try:
            last_price = float(r.last_price)
            entry_low = float(r.entry_low)
            entry_high = float(r.entry_high)

            distance = abs(last_price - entry_low) / entry_low

            if last_price < 100:
                continue

            setup = str(r.setup)

            # ================= ENTRY =================
            in_entry = entry_low <= last_price <= entry_high

            near_entry = (
                last_price < entry_low and
                (entry_low - last_price) / entry_low <= 0.05
            )

            entry_ready = in_entry or near_entry

            rows.append({
                "Kode": r.kode,
                "Harga": int(last_price),

                "Score": int(r.score),
                "Setup": setup,

                "Trend": r.trend,  # 🔥 NEW

                "Near Entry": entry_ready,
                "Distance": round(distance, 3),

                "Entry": f"{int(entry_low)} - {int(entry_high)}",
                "TP": f"{int(r.tp[0])} / {int(r.tp[1])}",
                "SL": int(r.sl),
                "RR (%)": round(r.rr, 1),
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

    # ================= SPLIT (🔥 UPDATED) =================
    df_best = df[
        df["Setup"].str.contains("Accumulation", na=False) &
        df["Setup"].str.contains("Uptrend", na=False)
    ].copy()

    df_acc = df[df["Setup"].str.contains("Smart Accumulation", na=False)].copy()

    # ================= SORT =================
    df_best = df_best.sort_values(by="Score", ascending=False).head(10)
    df_acc = df_acc.sort_values(by="Score", ascending=False).head(10)

    # ================= RESET INDEX =================
    for d in [df_best, df_acc]:
        d.reset_index(drop=True, inplace=True)
        d.index += 1

    return df_best, df_acc


# ==========================================================
# ===================== MAIN UI =============================
# ==========================================================
def render_screener():

    st.header("📊 CRUZER AI - SCREENER")

    # ================= RESET =================
    if st.button("Reset Scanner"):
        st.session_state["scanner_state"] = {
            "alerted": {},
            "last_status": {}
        }
        st.success("Scanner berhasil di-reset")

    # ================= SELECT TYPE =================
    screener_type = st.selectbox(
        "Pilih Tipe",
        ["Swing Trade (Day)", "Swing Trade (Week)"]
    )

    # ================= INIT STATE =================
    if "scanner_state" not in st.session_state:
        st.session_state["scanner_state"] = {
            "alerted": {},
            "last_status": {}
        }

    # ================= SCAN BUTTON =================
    if st.button("🚀 Scan Market", use_container_width=True):

        with st.spinner("Scanning market..."):

            if screener_type == "Swing Trade (Day)":

                df, alerts, state = scan_day(st.session_state["scanner_state"])

                st.session_state["scanner_state"] = state
                st.session_state["mode"] = "day"
                st.session_state["data"] = df

            else:
                df_best = pd.DataFrame()
                df_acc = pd.DataFrame()

                try:
                    df_best, df_acc = scan_week()
                except Exception as e:
                    st.error(f"Scan error: {e}")

                st.session_state["mode"] = "week"
                st.session_state["best"] = df_best
                st.session_state["accumulation"] = df_acc

            st.session_state["time"] = datetime.now().strftime("%d %b %H:%M:%S")

    # ================= DISPLAY =================
    if "mode" not in st.session_state:
        return

    st.caption(f"⏱ Last Scan: {st.session_state.get('time','-')}")

    if st.session_state["mode"] == "day":

        df = st.session_state.get("data", pd.DataFrame())

        if df.empty:
            st.warning("📭 Tidak ada data")
        else:
            st.dataframe(df, use_container_width=True)

    else:

        # 🔥 BEST SETUP (UPDATED)
        st.subheader("🔥 ACCUMULATION + UPTREND (BEST)")

        df_best = st.session_state.get("best", pd.DataFrame())

        if df_best.empty:
            st.warning("📭 Tidak ada setup terbaik")
        else:
            st.dataframe(df_best, use_container_width=True)

        st.divider()

        # 🟢 SMART ACCUMULATION
        st.subheader("🟢 SMART ACCUMULATION")

        df_acc = st.session_state.get("accumulation", pd.DataFrame())

        if df_acc.empty:
            st.info("Tidak ada accumulation")
        else:
            st.dataframe(df_acc, use_container_width=True)

        # ===================== TELEGRAM =====================
        st.divider()
        st.subheader("📤 Share Screener Result")

        SHARE_PASSWORD = st.secrets.get("SHARE_PASSWORD")
        df_ihsg = get_price_data("^JKSE")

        input_pwd = st.text_input(
            "🔐 Password untuk kirim Telegram",
            type="password",
            key="share_pwd_screener",
        )

        is_authorized = input_pwd == SHARE_PASSWORD

        if st.button(
            "📨 Send Screener to Telegram",
            type="primary",
            use_container_width=True,
            disabled=not is_authorized,
        ):
            try:
                results = []

                for df in [df_best, df_acc]:
                    if not df.empty:
                        results.extend(df.to_dict(orient="records"))

                if not results:
                    st.warning("Tidak ada data untuk dikirim")
                else:
                    msg = render_telegram(results, df_ihsg=df_ihsg)
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