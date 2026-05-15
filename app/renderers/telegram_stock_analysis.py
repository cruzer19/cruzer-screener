def render_stock_analysis_message(
    kode,
    timeframe,
    analysis,
    news_result,
    insight_text,
    df_price,
):

    from app.utils.sector_utils import get_sector_badge
    from app.config.saham_profile import SAHAM_PROFILE

    # ==========================================================
    # CLEAN DF
    # ==========================================================

    df_price.columns = [
        c[0] if isinstance(c, tuple) else c
        for c in df_price.columns
    ]

    df_price.columns = [
        str(c).upper()
        for c in df_price.columns
    ]

    # ==========================================================
    # HELPERS
    # ==========================================================

    def rp(x):

        return f"Rp {int(x):,}".replace(",", ".")

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

    # ==========================================================
    # BASIC
    # ==========================================================

    last_price = float(df_price["CLOSE"].iloc[-1])

    sector_emoji, _ = get_sector_badge(kode)

    company_name = SAHAM_PROFILE.get(kode, kode)

    trend = analysis.get("trend", "-")

    # ==========================================================
    # SUPPORT
    # ==========================================================

    major_support = analysis.get("support")

    minor_support = analysis.get("minor_support")

    # ================= MICRO SUPPORT =================

    low_col = next(
        (
            col
            for col in df_price.columns
            if "LOW" in col.upper()
        ),
        None
    )

    if low_col and len(df_price) >= 7:

        micro_support = float(
            df_price[low_col].tail(7).min()
        )

    else:

        micro_support = None

    supports = []

    if micro_support is not None:
        supports.append(("Micro", micro_support))

    if minor_support is not None:
        supports.append(("Minor", minor_support))

    if major_support is not None:
        supports.append(("Major", major_support))

    # fallback
    if not supports:

        supports = [("Unknown", last_price)]

    # ================= SORT =================

    supports_sorted = sorted(
        supports,
        key=lambda x: abs(last_price - x[1])
    )

    near = supports_sorted[0]

    mid = (
        supports_sorted[1]
        if len(supports_sorted) > 1
        else supports_sorted[0]
    )

    far = (
        supports_sorted[2]
        if len(supports_sorted) > 2
        else supports_sorted[-1]
    )

    near_label, near_price = near
    mid_label, mid_price = mid
    far_label, far_price = far

    # ================= ROUND =================

    near_price = round_to_tick(near_price)
    mid_price = round_to_tick(mid_price)
    far_price = round_to_tick(far_price)

    resistance = analysis.get("resistance")

    if resistance:
        resistance = round_to_tick(resistance)

    # ==========================================================
    # ENTRY PLAN (MATCH UI 100%)
    # ==========================================================

    entry_near = (
        round_to_tick(near_price * 0.99),
        round_to_tick(near_price * 1.01)
    )

    entry_deep = (
        round_to_tick(mid_price * 0.97),
        round_to_tick(mid_price * 1.00)
    )

    sl = round_to_tick(mid_price * 0.97)

    risk = (
        ((last_price - sl) / last_price) * 100
        if last_price
        else 0
    )

    # ==========================================================
    # GAP ANALYSIS
    # ==========================================================

    gaps = []

    for i in range(2, len(df_price)):

        c1_high = df_price.iloc[i - 2]["HIGH"]

        c1_low = df_price.iloc[i - 2]["LOW"]

        c3_high = df_price.iloc[i]["HIGH"]

        c3_low = df_price.iloc[i]["LOW"]

        date = df_price.index[i]

        # ================= BULLISH GAP =================

        if c3_low > c1_high:

            gap_low = c1_high

            gap_high = c3_low

            size = (
                (gap_high - gap_low)
                / gap_low
            )

            if size > 0.015:

                gaps.append({

                    "low": gap_low,

                    "high": gap_high,

                    "date": date

                })

        # ================= BEARISH GAP =================

        elif c3_high < c1_low:

            gap_low = c3_high

            gap_high = c1_low

            size = (
                (gap_high - gap_low)
                / gap_low
            )

            if size > 0.015:

                gaps.append({

                    "low": gap_low,

                    "high": gap_high,

                    "date": date

                })

    # ==========================================================
    # SORT BY TIME
    # ==========================================================

    gaps = sorted(
        gaps,
        key=lambda x: x["date"]
    )

    # ==========================================================
    # MERGE ZONE
    # ==========================================================

    merged = []

    for g in gaps:

        if not merged:

            merged.append(g)

            continue

        last = merged[-1]

        if abs(
            g["low"] - last["high"]
        ) / last["high"] < 0.03:

            last["low"] = min(
                last["low"],
                g["low"]
            )

            last["high"] = max(
                last["high"],
                g["high"]
            )

            last["date"] = g["date"]

        else:

            merged.append(g)

    # ==========================================================
    # MATCH UI
    # ==========================================================

    gaps = merged[-10:]

    gaps = sorted(

        gaps,

        key=lambda g: abs(
            (
                (g["low"] + g["high"]) / 2
            ) - last_price
        )

    )[:3]

    # ==========================================================
    # GAP FORMAT
    # ==========================================================

    if gaps:

        gap_text = "📊 <b>Gap Analysis</b>\n"

        for g in gaps:

            low_gap = round_to_tick(g["low"])

            high_gap = round_to_tick(g["high"])

            mid_gap = (
                low_gap + high_gap
            ) / 2

            label = (
                "Gap Atas"
                if mid_gap > last_price
                else "Gap Bawah"
            )

            dist = abs(
                mid_gap - last_price
            ) / last_price * 100

            gap_text += (

                f"{label} : "
                f"{rp(low_gap)} - {rp(high_gap)} "
                f"({dist:.1f}%)\n"

            )

    else:

        gap_text = (
            "📊 <b>Gap Analysis</b>\n"
            "Tidak ada gap signifikan\n"
        )

    # ==========================================================
    # NEWS
    # ==========================================================

    sentiment = news_result.get(
        "sentiment",
        "NEUTRAL"
    )

    sentiment_icon = {

        "POSITIVE": "🟢",

        "NEGATIVE": "🔴",

        "SPECULATIVE": "🟣",

        "NO_RECENT_NEWS": "📰",

    }.get(sentiment, "⚪")

    # ==========================================================
    # NO RECENT NEWS
    # ==========================================================

    if sentiment == "NO_RECENT_NEWS":

        news_lines = (
            news_result.get(
                "message",
                "Tidak ada berita terbaru"
            )
        )

    # ==========================================================
    # NORMAL NEWS
    # ==========================================================

    else:

        news_lines = ""

        for n in news_result.get("news", [])[:5]:

            if n.get("title") and n.get("link"):

                age = n.get("age_days")

                age_text = (
                    f" ({age} hari lalu)"
                    if age is not None
                    else ""
                )

                news_lines += (

                    f'• <a href="{n["link"]}">'
                    f'{n["title"]}</a>'
                    f'{age_text}\n'

                )

        news_lines = news_lines.rstrip()

        if not news_lines:

            news_lines = "Tidak ada berita terbaru"

# ==========================================================
# FINAL MESSAGE
# ==========================================================

    msg = f"""
📊 <b>STOCK ANALYSIS</b>
{sector_emoji} <b>{company_name}</b> ({kode})

🧭 <b>Market Condition</b>
Trend : {trend}
Harga : {rp(last_price)}

📉 <b>Support & Resistance</b>
Support (Near) : {rp(near_price)} ({near_label})
Support (Mid)   : {rp(mid_price)} ({mid_label})
Support (Far)    : {rp(far_price)} ({far_label})
Resistance        : {rp(analysis.get("resistance"))}

🎯 <b>Entry Plan</b>
Entry Near  : {rp(entry_near[0])} - {rp(entry_near[1])}
Entry Deep : {rp(entry_deep[0])} - {rp(entry_deep[1])}
SL                : {rp(sl)}
Risk             : {risk:.2f} %

{gap_text}
📰 <b>News & Sentiment</b>
{sentiment_icon} {sentiment}
{news_lines}

🧠 <b>Insight</b>
{insight_text}
"""

    return msg