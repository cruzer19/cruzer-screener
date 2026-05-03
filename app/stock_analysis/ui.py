import streamlit as st

from .helpers import (
    calc_minor_support,
    clean_price_df,
    format_money,
    format_number
)

from .smart_money import calculate_smart_money
from .engine import (
    calculate_gap_fill_rate,
    get_support_levels,
    get_entry_plan
)

from app.utils.news_engine import fetch_stock_news
from app.utils.market_data import load_price_data
from app.renderers.telegram_stock_analysis import render_stock_analysis_message
from app.services.telegram_bot import send_message


# ==========================================================
# 📊 MAIN STOCK ANALYSIS UI
# ==========================================================
def render_stock_analysis():

    from app.utils.market_data import load_price_data
    from app.utils.analysis_engine import analyze_single_stock
    from app.config.saham_list import SAHAM_LIST
    from app.config.saham_profile import SAHAM_PROFILE
    from app.utils.sector_utils import get_sector_badge
    from datetime import datetime, timedelta
    import pandas as pd

    st.header("📊 Stock Analysis")
    st.caption("Analisa mandiri satu saham (independen dari screener)")

    # ================= INPUT =================
    col1, col2 = st.columns([2, 1])

    with col1:
        kode = st.selectbox("Kode Saham", SAHAM_LIST, key="analysis_kode")

    with col2:
        timeframe = st.selectbox("Timeframe", ["Weekly"], key="analysis_tf")

    # ================= RESET =================
    def reset_analysis_state():
        for k in ["analysis_result", "news_result", "analyzed"]:
            st.session_state.pop(k, None)

    if st.session_state.get("last_analysis_kode") != kode:
        reset_analysis_state()
        st.session_state.last_analysis_kode = kode

    if st.session_state.get("last_analysis_tf") != timeframe:
        reset_analysis_state()
        st.session_state.last_analysis_tf = timeframe

    # ================= PROFILE =================
    company_name = SAHAM_PROFILE.get(kode, kode)
    sector_emoji, sector_name = get_sector_badge(kode)

    st.markdown(f"### {sector_emoji} {company_name} ({kode})")
    st.caption(f"Sektor: {sector_name}")

    # ================= ANALYZE =================
    if st.button("🔍 Analyze Stock"):
        df = load_price_data(kode)

        if df.empty:
            st.warning("Data harga tidak tersedia.")
        else:
            result = analyze_single_stock(df)
            result["minor_support"] = calc_minor_support(df)

            news_result = fetch_stock_news(kode)

            st.session_state["analysis_result"] = result
            st.session_state["analysis_df"] = df
            st.session_state["news_result"] = news_result

    if "analysis_result" not in st.session_state:
        return

    result = st.session_state["analysis_result"]
    df_price = clean_price_df(st.session_state["analysis_df"])
    news_result = st.session_state.get("news_result", {})

    # ================= MARKET =================
    st.subheader("🧭 Market Condition")

    last_price = df_price["CLOSE"].iloc[-1]

    ma200 = df_price["CLOSE"].rolling(200).mean().iloc[-1] if len(df_price) >= 200 else None
    ma50 = df_price["CLOSE"].rolling(50).mean().iloc[-1] if len(df_price) >= 50 else None
    std = df_price["CLOSE"].rolling(200).std().iloc[-1] if len(df_price) >= 200 else None

    z_score = (last_price - ma200) / std if ma200 and std else None

    # ================= FAIR RANGE =================
    if ma200 and std:
        fair_low = ma200 - std
        fair_high = ma200 + std
    else:
        fair_low, fair_high = None, None

    trend = result.get("trend", "-")
    st.markdown(f"### {trend}")

    # ================= PRICE INFO =================
    c1, c2 = st.columns(2)

    with c1:
        st.metric("Last Price", f"Rp {int(last_price):,}".replace(",", "."))

    with c2:
        if ma200:
            st.metric("Fair Value (MA200)", f"Rp {int(ma200):,}".replace(",", "."))
        else:
            st.metric("Fair Value", "-")

    # ================= RANGE =================
    if fair_low and fair_high:
        st.caption(
            f"Range Wajar: Rp {int(fair_low):,} - Rp {int(fair_high):,}".replace(",", ".")
        )

    # ================= VALUATION =================
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

    # ===================== SUPPORT & RESISTANCE =====================
    st.subheader("📉 Support & Resistance")

    last_price = df_price["CLOSE"].iloc[-1]

    major_support = result.get("support")
    minor_support = calc_minor_support(df_price)

    # 🔹 Micro support (very near)
    low_col = None

    for col in df_price.columns:
        if "low" in col.lower():
            low_col = col
            break

    if low_col:
        micro_support = int(df_price[low_col].tail(7).min()) if len(df_price) >= 7 else None
    else:
        micro_support = None

    supports = []

    if micro_support:
        supports.append(("Micro", micro_support))
    if minor_support:
        supports.append(("Minor", minor_support))
    if major_support:
        supports.append(("Major", major_support))

    # sort by nearest
    supports_sorted = sorted(
        supports,
        key=lambda x: abs(last_price - x[1])
    )

    rows = []

    labels = ["Near", "Mid", "Far"]

    for i, (label, price) in enumerate(supports_sorted[:3]):
        rows.append(
            (
                f"Support ({labels[i]})",
                f"Rp {int(price):,} ({label})".replace(",", "."),
            )
        )

    # resistance
    if result.get("resistance"):
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

    # ================= BASIC DATA =================
    last_price = df_price["CLOSE"].iloc[-1]

    major_support = result.get("support")
    minor_support = calc_minor_support(df_price)

    # ================= MICRO SUPPORT =================
    low_col = next((col for col in df_price.columns if "low" in col.lower()), None)

    if low_col and len(df_price) >= 7:
        micro_support = float(df_price[low_col].tail(7).min())
    else:
        micro_support = None

    # ================= BUILD SUPPORT =================
    supports = []

    if micro_support is not None:
        supports.append(("Micro", micro_support))
    if minor_support is not None:
        supports.append(("Minor", minor_support))
    if major_support is not None:
        supports.append(("Major", major_support))

    if not supports:
        st.warning("Support tidak tersedia")
    else:
        supports_sorted = sorted(
            supports,
            key=lambda x: abs(last_price - x[1])
        )

        near_support = supports_sorted[0][1]
        deep_support = supports_sorted[1][1] if len(supports_sorted) > 1 else near_support

        # ================= TICK =================
        def round_to_tick(price):
            if price < 200:
                tick = 1
            elif price < 500:
                tick = 2
            elif price < 2000:
                tick = 5
            elif price < 5000:
                tick = 10
            else:
                tick = 25
            return int(round(price / tick) * tick)

        # ================= ENTRY =================
        entry_near_low = round_to_tick(near_support * 0.99)
        entry_near_high = round_to_tick(near_support * 1.01)

        entry_deep_low = round_to_tick(deep_support * 0.97)
        entry_deep_high = round_to_tick(deep_support * 1.00)

        sl = round_to_tick(deep_support * 0.97)

        risk_pct = ((last_price - sl) / last_price) * 100

        def fmt(x):
            return f"Rp {format_number(x)}"

        entry_df = pd.DataFrame({
            "Parameter": [
                "Entry Near (Pullback)",
                "Entry Deep (Discount)",
                "Stop Loss",
                "Risk",
            ],
            "Value": [
                f"{fmt(entry_near_low)} – {fmt(entry_near_high)}",
                f"{fmt(entry_deep_low)} – {fmt(entry_deep_high)}",
                fmt(sl),
                f"{risk_pct:.1f} %",
            ]
        })

        st.table(entry_df.set_index("Parameter"))

    # ================= GAP ANALYSIS =================
    st.subheader("📊 Gap Analysis")

    df_gap = load_price_data(kode)
    df_gap = clean_price_df(df_gap)

    if df_gap is None or df_gap.empty:
        st.warning("Data gap tidak tersedia")

    else:
        last_price = df_gap["CLOSE"].iloc[-1]

        gaps = []

        # ================= FVG DETECTION =================
        for i in range(2, len(df_gap)):
            c1_high = df_gap.iloc[i - 2]["HIGH"]
            c1_low = df_gap.iloc[i - 2]["LOW"]

            c3_high = df_gap.iloc[i]["HIGH"]
            c3_low = df_gap.iloc[i]["LOW"]

            date = df_gap.index[i]

            # Bullish gap
            if c3_low > c1_high:
                gap_low = c1_high
                gap_high = c3_low

                if (gap_high - gap_low) / gap_low > 0.015:
                    gaps.append({"low": gap_low, "high": gap_high, "date": date})

            # Bearish gap
            elif c3_high < c1_low:
                gap_low = c3_high
                gap_high = c1_low

                if (gap_high - gap_low) / gap_low > 0.015:
                    gaps.append({"low": gap_low, "high": gap_high, "date": date})

        # ================= SORT & MERGE =================
        gaps = sorted(gaps, key=lambda x: x["date"])

        merged = []

        for g in gaps:
            if not merged:
                merged.append(g)
                continue

            last = merged[-1]

            if abs(g["low"] - last["high"]) / last["high"] < 0.03:
                last["low"] = min(last["low"], g["low"])
                last["high"] = max(last["high"], g["high"])
                last["date"] = g["date"]
            else:
                merged.append(g)

        # ================= AMBIL TERBAIK =================
        gaps = merged[-10:]

        gaps = sorted(
            gaps,
            key=lambda g: abs(((g["low"] + g["high"]) / 2) - last_price)
        )[:3]

        def fmt_price(x):
            return f"Rp {format_number(round_to_tick(x))}"

        def fmt_date(d):
            return d.strftime("%d-%b-%Y")

        rows = []

        for g in gaps:
            mid = (g["low"] + g["high"]) / 2

            label = "Gap Atas" if mid > last_price else "Gap Bawah"

            dist = abs(mid - last_price) / last_price

            rows.append((
                label,
                f"{fmt_price(g['low'])} – {fmt_price(g['high'])}",
                fmt_date(g["date"]),
                f"{dist*100:.1f}%"
            ))

        if rows:
            gap_df = pd.DataFrame(
                rows,
                columns=["Type", "Range", "Tanggal", "Distance"]
            )
            st.table(gap_df.set_index("Type"))
        else:
            st.caption("Tidak ada gap signifikan")

    # ================= SMART MONEY =================
    st.subheader("💰 Smart Money Flow (10D)")

    result_sm = calculate_smart_money(df_price)

    if result_sm:
        summary = result_sm["summary"]
        table = result_sm["table"].copy()

        col1, col2, col3 = st.columns(3)

        col1.metric("Smart Money", f"{summary['smart']/1e9:.2f} B")
        col2.metric("Clean Money", f"{summary['clean']/1e9:.2f} B")
        col3.metric("Power", f"{summary['power']}%")

        st.markdown(f"**Status: {summary['status']}**")

        if "Date" not in table.columns:
            table["Date"] = table.index.astype(str)

        table["Tx"] = table.get("VOLUME", 0).apply(format_number)
        table["Value"] = table.get("VALUE", 0).apply(format_money)
        table["Smart"] = table.get("SMART", 0).apply(format_money)
        table["Bad"] = table.get("BAD", 0).apply(format_money)
        table["Clean"] = table.get("CLEAN", 0).apply(format_money)

        table["Gain%"] = table.get("GAIN (%)", 0).apply(lambda x: f"{x:.2f}%")
        table["AVP"] = table.get("AVP", 0).astype(int)
        table["RCV"] = table.get("RCV", 0).astype(int)
        table["📊"] = table.get("SIGNAL", "-")

        final_cols = [
            col for col in [
                "Date","Tx","Value","AVP","Gain%","Smart","Bad","Clean","RCV","📊"
            ] if col in table.columns
        ]

        table = table[final_cols]

        table = table.reset_index(drop=True)
        table.index += 1

        st.dataframe(table, use_container_width=True)

        st.caption(
            f"RCV: {summary['avg_rcv']} | Win Rate: {summary['win_rate']}/10 "
            f"{'⬆️' if summary['trend_up'] else '⬇️'}"
        )


        # ===================== CYCLE PROJECTION (SMART + ADAPTIVE) =====================
        st.subheader("📅 Cycle Projection")

        today = datetime.now().date()
        cycle = result.get("cycle") if "result" in locals() else None

        if not cycle:
            st.warning("Data cycle tidak tersedia")

        else:
            import pandas as pd

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

            # ===================== ADVANCED TREND DETECTION =====================
            df_price = st.session_state.get("analysis_df")

            if df_price is not None:
                df_price.columns = [
                    c[0] if isinstance(c, tuple) else c
                    for c in df_price.columns
                ]
                df_price.columns = [str(c).upper() for c in df_price.columns]

            trend_mode = "sideways"

            if df_price is not None and len(df_price) > 50:

                close = df_price["CLOSE"]
                high = df_price["HIGH"]
                low = df_price["LOW"]
                volume = df_price["VOLUME"]

                ma20 = close.rolling(20).mean()
                ma50 = close.rolling(50).mean()

                last_price = close.iloc[-1]

                # ================= STRUCTURE =================
                hh = high.iloc[-1] >= high.tail(20).max() * 0.98
                hl = low.iloc[-1] > low.tail(20).min()

                # ================= MOMENTUM =================
                momentum = (last_price - close.iloc[-10]) / close.iloc[-10]

                # ================= VOLUME =================
                vol_ratio = volume.iloc[-1] / volume.tail(20).mean()

                # ================= STRONG TREND =================
                if (
                    last_price > ma50.iloc[-1]
                    and momentum > 0.07
                ):
                    trend_mode = "strong_up"

                # ================= SPECULATIVE MOVE =================
                if (
                    momentum > 0.20
                    and vol_ratio > 2
                    and last_price > ma20.iloc[-1]
                ):
                    trend_mode = "speculative"

                # ================= NORMAL TREND =================
                elif last_price > ma50.iloc[-1]:
                    trend_mode = "up"

                elif last_price < ma50.iloc[-1]:
                    trend_mode = "down"

            # ===================== CURRENT POSITION =====================
            if in_range(near_low_start, near_low_end):

                if trend_mode in ["strong_up", "speculative"]:
                    st.warning("⚠️ Cycle Low (Low Confidence)")

                else:
                    st.success("🟢 Near Cycle Low")

            elif in_range(near_high_start, near_high_end):

                if trend_mode in ["strong_up", "speculative"]:
                    st.info("📈 Near Cycle High (Trend Continuation)")

                else:
                    st.warning("🔴 Near Cycle High")

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
                        if trend_mode in ["strong_up", "speculative"]:
                            st.info(f"⏳ {name} ({d} hari lagi)")

                        else:
                            st.info(f"⏳ Menuju {name} ({d} hari lagi)")

                    else:
                        st.info(f"📈 Menuju {name} ({d} hari lagi)")

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

            # ===================== CONFIDENCE =====================
            if trend_mode == "speculative":
                st.caption("🚀 Market mode: High Momentum (cycle less reliable)")
            elif trend_mode == "strong_up":
                st.caption("⚠️ Cycle reliability: LOW (strong trend)")
            elif trend_mode in ["up", "down"]:
                st.caption("⚖️ Cycle reliability: MEDIUM")
            else:
                st.caption("🟢 Cycle reliability: HIGH (sideways)")

    # ================= NEWS =================
    st.subheader("📰 News & Sentiment")

    sent = news_result.get("sentiment")

    if sent == "POSITIVE":
        st.success("🟢 Sentimen Positif")
    elif sent == "NEGATIVE":
        st.warning("🟠 Sentimen Negatif")
    elif sent == "SPECULATIVE":
        st.error("🎢 Speculative / High Risk")
    else:
        st.info("⚪ Netral")

    for n in news_result.get("news", [])[:5]:
        st.markdown(f"- [{n['title']}]({n['link']})")

    # ================= INSIGHT =================
    st.subheader("🧠 Insight")

    if "Bullish" in trend:
        st.success("⬆️ Buy on pullback")
    elif "Bearish" in trend:
        st.error("⬇️ Avoid / Wait")
    else:
        st.info("➡️ Sideways / Wait")

    # ================= TELEGRAM =================
    st.subheader("📤 Share Analysis")

    pwd = st.text_input("Password", type="password")

    if st.button("Send to Telegram") and pwd == st.secrets.get("SHARE_PASSWORD"):
        msg = render_stock_analysis_message(
            kode=kode,
            timeframe=timeframe,
            analysis=result,
            news_result=news_result,
            insight_text=trend,
            df_price=df_price,
        )
        send_message(msg)
        st.success("Terkirim ✅")