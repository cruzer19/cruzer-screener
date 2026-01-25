# ==========================================================
# FIX PYTHON PATH (WAJIB PALING ATAS)
# ==========================================================
import sys
import os
from dotenv import load_dotenv


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

load_dotenv()

# ==========================================================
# IMPORTS
# ==========================================================
import streamlit as st
import pandas as pd

from app.core.engine import ScreenerEngine
from app.config.saham_list import SAHAM_LIST
from app.renderers.telegram import render_telegram
from app.services.telegram_bot import send_message

st.set_page_config(page_title="Cruzer AI Screener", layout="wide")

st.title("🤖 Stock Screener Dashboard (Beta)")
st.caption("AI-powered multi-strategy stock screening")

# ================= HELPERS =================

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
    else:
        return "ABOVE"

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
    else:
        return "background-color:#f87171;color:white"

def render_df(data):
    df = pd.DataFrame(data)
    if df.empty:
        st.info("Tidak ada data.")
        return
    if "Score" in df.columns:
        df = df.style.applymap(score_color, subset=["Score"])
    st.dataframe(df, use_container_width=True)

# ================= SESSION STATE INIT =================

SESSION_DEFAULTS = {
    "min_score": 50,
    "min_gain": 2,
    "price_range": (0, 10_000),
    "last_screener": None,
    "scanned_screener": None,
}

for key, default in SESSION_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ================= SCREENER UI =================

st.sidebar.header("⚙️ Screener Settings")

SCREENER_LABEL_MAP = {
    "Swing Trade (Week)": "swing_trade_week",
    "Swing Trade (Day)": "swing_trade_day",
    "Breakout (BSJP)": "breakout",
}

menu = st.sidebar.radio(
    "📂 Menu",
    ["🔍 Screener", "📊 Stock Analysis", "📒 Trading Tracker"],
)

screener_label = st.sidebar.selectbox(
    "Pilih Tipe Screener",
    options=list(SCREENER_LABEL_MAP.keys()),
)

screener_type = SCREENER_LABEL_MAP[screener_label]

st.session_state["screener_type"] = screener_type

st.session_state.min_score = st.sidebar.slider(
    "Minimum Score",
    0,
    100,
    st.session_state.min_score,
)

st.session_state.min_gain = st.sidebar.slider(
    "Minimum Expected Gain (%)",
    0,
    15,
    st.session_state.min_gain,
)

st.session_state.price_range = st.sidebar.slider(
    "Filter Harga (Rp)",
    0,
    30_000,
    st.session_state.price_range,
    step=500,
)

st.divider()

st.subheader("🔍 Screener")

if st.button("🔍 Scan Market", use_container_width=True):
    with st.spinner("🔎 Scanning market..."):
        engine = ScreenerEngine()
        results = engine.run(SAHAM_LIST, st.session_state["screener_type"])

        st.session_state["results"] = results
        st.session_state["scanned_screener"] = st.session_state["screener_type"]

    st.success(f"Scan selesai ✅ ({len(results)} saham)")

# ================= DISPLAY RESULTS =================

if (
    "results" in st.session_state
    and st.session_state.get("scanned_screener") == st.session_state.get("screener_type")
):
    entry_now = []
    watchlist = []

    min_score = st.session_state.min_score
    min_gain = st.session_state.min_gain
    min_price, max_price = st.session_state.price_range

    for r in st.session_state["results"]:
        if not r.tp or len(r.tp) < 2:
            continue

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

        row = {
            "Kode": r.kode,
            "Harga": int(last_price),
            "Score": r.score,
            "Entry": format_range(r.entry_low, r.entry_high),
            "TP": format_tp(r.tp),
            "SL": format_price(r.sl),
            "Gain (%)": f"{gain_pct:.2f}",
            "Posisi": pos,
        }

        if pos == "INSIDE" and gain_pct >= min_gain:
            entry_now.append(row)
        else:
            watchlist.append(row)

   # ===== CAN ENTRY =====
    st.subheader("🟢 CAN ENTRY")

    if entry_now:
        df_entry = pd.DataFrame(entry_now).sort_values(
            by=["Score", "Harga"],
            ascending=[False, True],
        ).reset_index(drop=True)
        df_entry.index = df_entry.index + 1
        render_df(df_entry)

        # ===== TELEGRAM BUTTON =====
        st.divider()

        if st.button(
            "📩 Send CAN ENTRY to Telegram",
            type="primary",
            use_container_width=True,
        ):
            try:
                if not os.getenv("TELEGRAM_BOT_TOKEN") or not os.getenv("TELEGRAM_CHAT_ID"):
                    st.error("❌ Telegram belum dikonfigurasi (env belum ada)")
                else:
                    message = render_telegram(entry_now)
                    send_message(message)
                    st.success("CAN ENTRY terkirim ke Telegram ✅")
            except Exception as e:
                st.error("❌ Gagal kirim ke Telegram")
                st.code(str(e))

    else:
        st.info("Belum ada CAN ENTRY")


    # ===== WATCHLIST =====
    st.subheader("🟡 WATCHLIST")
    if watchlist:
        df_watch = pd.DataFrame(watchlist).sort_values(
            by=["Score", "Harga"],
            ascending=[False, True],
        ).reset_index(drop=True)
        df_watch.index = df_watch.index + 1
        render_df(df_watch)
    else:
        st.info("Belum ada WATCHLIST")