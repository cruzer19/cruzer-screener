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
        engine = ScreenerEngine()
        st.session_state["results"] = engine.run(SAHAM_LIST, screener_type)
        st.session_state.scanned_screener = screener_type

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
        st.info("Belum ada CAN ENTRY")
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

    is_authorized = input_pwd == SHARE_PASSWORD

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

    if input_pwd and not is_authorized:
        st.error("❌ Password salah")


    # ================= RENDER WATCHLIST =================
    st.subheader("🟡 WATCHLIST")

    df_watchlist = pd.DataFrame(watchlist)

    if not df_watchlist.empty:
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
    from app.utils.analysis_engine import analyze_single_stock
    from app.config.saham_profile import SAHAM_PROFILE
    from app.utils.sector_utils import get_sector_badge

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

    # =========================
    # RESET SAAT INPUT BERUBAH
    # =========================
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

            # === tambahan untuk Support Minor (dipakai UI & Telegram) ===
            minor_support = calc_minor_support(df)
            result["minor_support"] = minor_support

            # === simpan ke session_state ===
            st.session_state["analysis_result"] = result
            st.session_state["news_result"] = news_result
            st.session_state["analysis_timeframe"] = timeframe
            st.session_state["analysis_df"] = df

    # ===================== DISPLAY =====================
    if "analysis_result" not in st.session_state:
        return

    result = st.session_state["analysis_result"]
    news_result = st.session_state["news_result"]

    st.subheader("🧭 Market Condition")
    c1, c2 = st.columns(2)

    with c1:
        st.metric("Trend", result["trend"])

    with c2:
        st.metric(
            "Last Price",
            f"Rp {int(result['last_price']):,}".replace(",", "."),
        )

    # ---------- Support Resistance ----------
    st.subheader("📉 Support & Resistance")

    df_price = st.session_state.get("analysis_df")
    minor_support = calc_minor_support(df_price)
    major_support = result["support"]
    last_price = result["last_price"]

    supports = []

    if major_support is not None:
        supports.append(("Major", major_support))
    if minor_support is not None:
        supports.append(("Minor", minor_support))

    rows = []

    # ===== NEAR / FAR LOGIC (SAMA DENGAN TELEGRAM) =====
    if len(supports) == 2:
        supports_sorted = sorted(
            supports,
            key=lambda x: abs(last_price - x[1])
        )

        near_label, near_val = supports_sorted[0]
        far_label, far_val = supports_sorted[1]

        rows.extend([
            (
                "Support (Near)",
                f"Rp {int(near_val):,} ({near_label})".replace(",", "."),
            ),
            (
                "Support (Far)",
                f"Rp {int(far_val):,} ({far_label})".replace(",", "."),
            ),
        ])

    elif len(supports) == 1:
        label, val = supports[0]
        rows.append(
            (
                f"Support ({label})",
                f"Rp {int(val):,}".replace(",", "."),
            )
        )

    # ===== RESISTANCE =====
    rows.append(
        (
            "Resistance",
            f"Rp {int(result['resistance']):,}".replace(",", "."),
        )
    )

    sr_df = pd.DataFrame(rows, columns=["Level", "Price"])
    st.table(sr_df.set_index("Level"))


    # ---------- Entry ----------
    st.subheader("🎯 Entry Plan")

    # ===== DEFAULT (WAJIB ADA) =====
    entry_low, entry_high = result["entry_zone"]
    entry_label = "Entry Zone (Default)"

    entry_df = pd.DataFrame(
        {
            "Parameter": [entry_label, "Risk"],
            "Value": [
                f"Rp {int(entry_low):,} – Rp {int(entry_high):,}".replace(",", "."),
                f"{result['risk_pct']} %",
            ],
        }
    )

    # ===== SMART ENTRY (OPTIONAL OVERRIDE) =====
    if minor_support is not None:
        buffer_pct = 0.015  # 1.5%
        smart_low = minor_support
        smart_high = minor_support * (1 + buffer_pct)

        last_price = result["last_price"]

        if smart_low <= last_price <= smart_high * 1.05:
            entry_df = pd.DataFrame(
                {
                    "Parameter": ["Entry Zone (Support Minor)", "Risk"],
                    "Value": [
                        f"Rp {int(smart_low):,} – Rp {int(smart_high):,}".replace(",", "."),
                        f"{result['risk_pct']} %",
                    ],
                }
            )

    # ===== RENDER (AMAN) =====
    st.table(entry_df.set_index("Parameter"))


        # ---------- News ----------
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

    # 🔗 LINK BERITA (SELALU DITAMPILKAN, SAMA SEPERTI VERSI LAMA YANG DIHARAPKAN)
    if news_result.get("news"):
        for n in news_result["news"][:5]:
            if n.get("title") and n.get("link"):
                st.markdown(f"- [{n['title']}]({n['link']})")

    # ---------- Insight ----------

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
def render_trading_tracker():
    st.header("📒 Trading Tracker (Journal)")

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

        if st.form_submit_button("Simpan BUY"):
            save_buy(
                kode=kode,
                buy_date=buy_date,
                buy_price=buy_price,
                buy_lot=buy_lot,
                note=note,
            )
            st.success("BUY dicatat ✅")
            st.divider()

    # ===================== SELL =====================
    df = load_trades()
    if not df.empty:
        df["remaining_lot"] = pd.to_numeric(df["remaining_lot"], errors="coerce").fillna(0).astype(int)

        open_trades = df[df["remaining_lot"] > 0]

        if not open_trades.empty:
            st.subheader("✏️ Jual (Partial / Full)")

            idx = st.selectbox(
                "Pilih posisi",
                open_trades.index,
                format_func=lambda i: f"{df.loc[i,'kode']} | Sisa {df.loc[i,'remaining_lot']} lot",
            )

            # =====================
            # INIT STATE
            # =====================
            if "sell_attempted" not in st.session_state:
                st.session_state.sell_attempted = False

            # =====================
            # INPUT
            # =====================
            remaining_lot = int(df.loc[idx, "remaining_lot"])

            sell_price = st.number_input("Harga Jual", min_value=0, step=1, key="sell_price")
            sell_lot = st.number_input(
                "Lot Dijual",
                min_value=0,
                step=1,
                value=0,
                key="sell_lot",
            )
            sell_date = st.date_input("Tanggal Jual", value=date.today(), key="sell_date")

            # =====================
            # VALIDATION (SILENT)
            # =====================
            errors = []

            if sell_price <= 0:
                errors.append("Harga jual harus lebih dari 0")
            if sell_lot <= 0:
                errors.append("Lot jual minimal 1")
            if sell_lot > remaining_lot:
                errors.append(f"Lot jual tidak boleh lebih dari {remaining_lot} lot")

            is_invalid = len(errors) > 0

            # =====================
            # BONUS: PREVIEW P/L
            # =====================
            buy_price = float(df.loc[idx, "buy_price"])

            if sell_price > 0 and sell_lot > 0:
                pnl_per_lot = (sell_price - buy_price) * 100
                pnl_total = pnl_per_lot * sell_lot

                if pnl_total >= 0:
                    st.success(f"📈 Estimasi P/L: Rp {pnl_total:,.0f}".replace(",", "."))
                else:
                    st.warning(f"📉 Estimasi P/L: Rp {pnl_total:,.0f}".replace(",", "."))

            # =====================
            # ACTION BUTTON
            # =====================
            jual_clicked = st.button("Jual", disabled=is_invalid)

            if jual_clicked:
                st.session_state.sell_attempted = True

            # =====================
            # SHOW ERROR (AFTER CLICK ONLY)
            # =====================
            if st.session_state.sell_attempted and is_invalid:
                for err in errors:
                    st.error(f"❌ {err}")

            # =====================
            # BACKEND GUARD + EXECUTE
            # =====================
            if jual_clicked and not is_invalid:
                save_sell(idx, sell_date, sell_price, sell_lot)
                st.success("Transaksi jual tercatat ✅")
                st.session_state.sell_attempted = False
                st.rerun()
                st.divider()

    # ===================== HISTORY =====================
    st.subheader("📊 Trading History")

    df_view = enrich_trades(load_trades())

    if df_view.empty:
        st.info("Belum ada trade.")
    else:
        for idx, row in df_view.iterrows():
            col_left, col_right = st.columns([8, 2])

            sell_info = (
                f"Sell Date: {row['Sell Date']}"
                if row["Status"] in ["CLOSED", "PARTIAL"] and row["Sell Date"] != ""
                else "Sell Date: -"
            )

            # ===== LEFT: INFO =====
            with col_left:
                st.markdown(
                    f"""
                    **{row['Kode']}**  
                    Buy Date: {row['buy_date']} (**{row['Holding Days']} hari**)  
                    {sell_info}  
                    Buy: {row['Buy']} | Now: {row['Now']}  
                    Sisa Lot: {row['Sisa Lot']}  
                    Status: **{row['Status']}**  
                    P/L: Rp {row['PnL (Rp)']:,} ({row['PnL (%)']}%)
                    """,
                    unsafe_allow_html=True,
                )

            # ===== RIGHT: ACTION =====
            with col_right:
                if st.button("🗑️ Hapus", key=f"del_{idx}", use_container_width=True):
                    st.session_state["delete_target"] = idx

                if st.session_state.get("delete_target") == idx:
                    st.warning("⚠️ Yakin hapus trade ini?")
                    if st.button("❌ Batal", key=f"cancel_{idx}", use_container_width=True):
                        st.session_state.pop("delete_target")

                    if st.button(
                        "✅ Hapus Permanen",
                        key=f"confirm_{idx}",
                        type="primary",
                        use_container_width=True,
                    ):
                        delete_trade(idx)
                        st.session_state.pop("delete_target")
                        st.rerun()

            st.divider()


# ==========================================================
# ======================= ROUTER ===========================
# ==========================================================
menu = st.sidebar.radio("📂 Menu", ["🔍 Screener", "📊 Stock Analysis", "📒 Trading Tracker"])

if menu == "🔍 Screener":
    render_screener()
elif menu == "📊 Stock Analysis":
    render_stock_analysis()
else:
    render_trading_tracker()

# ==========================================================
# FOOTER
# ==========================================================
st.markdown("---")
st.caption("© 2026 Cruzer AI • Stock Screener Engine. All rights reserved.")