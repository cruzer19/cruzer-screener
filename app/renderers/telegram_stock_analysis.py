def render_stock_analysis_message(kode, timeframe, analysis, news_result, insight_text, df_price):

    from app.utils.sector_utils import get_sector_badge
    from app.config.saham_profile import SAHAM_PROFILE

    # ================= CLEAN DF =================
    df_price.columns = [
        c[0] if isinstance(c, tuple) else c
        for c in df_price.columns
    ]
    df_price.columns = [str(c).upper() for c in df_price.columns]

    # ================= BASIC =================
    last_price = df_price["CLOSE"].iloc[-1]
    sector_emoji, _ = get_sector_badge(kode)
    company_name = SAHAM_PROFILE.get(kode, kode)
    trend = analysis.get("trend", "-")

    def rp(x):
        return f"Rp {int(x):,}".replace(",", ".")

    # ================= SUPPORT (ANTI ERROR FIX) =================
    major = analysis.get("support")
    minor = analysis.get("minor_support")

    micro = None
    for c in df_price.columns:
        if "LOW" in c:
            micro = int(df_price[c].tail(7).min())
            break

    supports = []

    if micro:
        supports.append(("Micro", micro))
    if minor:
        supports.append(("Minor", minor))
    if major:
        supports.append(("Major", major))

    # 🔥 safety fallback (biar gak crash)
    if not supports:
        supports = [("Unknown", last_price)]

    supports = sorted(supports, key=lambda x: abs(last_price - x[1]))

    # aman ambil
    near = supports[0]
    mid = supports[1] if len(supports) > 1 else supports[0]
    far = supports[2] if len(supports) > 2 else supports[-1]

    near_label, near_price = near
    mid_label, mid_price = mid
    far_label, far_price = far

    # ================= ENTRY =================
    vol = df_price["CLOSE"].pct_change().std()
    buffer = max(0.01, min(vol * 2, 0.04)) if vol else 0.02

    entry_near = (
        int(near_price * (1 - buffer)),
        int(near_price * (1 + buffer * 1.5))
    )

    entry_deep = (
        int(mid_price * (1 - buffer * 1.5)),
        int(mid_price * (1 + buffer))
    )

    sl = int(mid_price * 0.97)
    risk = ((last_price - sl) / last_price) * 100 if last_price else 0

    # ================= GAP ANALYSIS (MATCH UI 100%) =================
    gaps = []

    for i in range(2, len(df_price)):
        c1_high = df_price.iloc[i - 2]["HIGH"]
        c1_low = df_price.iloc[i - 2]["LOW"]

        c3_high = df_price.iloc[i]["HIGH"]
        c3_low = df_price.iloc[i]["LOW"]

        date = df_price.index[i]

        # bullish imbalance
        if c3_low > c1_high:
            gap_low = c1_high
            gap_high = c3_low

            size = (gap_high - gap_low) / gap_low
            if size > 0.015:
                gaps.append({
                    "low": gap_low,
                    "high": gap_high,
                    "date": date
                })

        # bearish imbalance
        elif c3_high < c1_low:
            gap_low = c3_high
            gap_high = c1_low

            size = (gap_high - gap_low) / gap_low
            if size > 0.015:
                gaps.append({
                    "low": gap_low,
                    "high": gap_high,
                    "date": date
                })

    # sort by time
    gaps = sorted(gaps, key=lambda x: x["date"])

    # ================= MERGE ZONE =================
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

    # ambil 3 terakhir
    gaps = merged[-3:]

    # sort by distance (biar relevan)
    gaps = sorted(
        gaps,
        key=lambda g: abs(((g["low"] + g["high"]) / 2) - last_price)
    )

    # ================= FORMAT =================
    if gaps:
        gap_text = "📊 <b>Gap Analysis</b>\n"

        for g in reversed(gaps):

            mid_gap = (g["low"] + g["high"]) / 2

            # 🔥 label berdasarkan posisi (INI YANG BENER)
            if mid_gap > last_price:
                label = "Gap Atas"
            else:
                label = "Gap Bawah"

            dist = abs(mid_gap - last_price) / last_price * 100

            gap_text += (
                f"{label} : {rp(g['low'])} - {rp(g['high'])} ({dist:.1f}%)\n"
            )

    else:
        gap_text = "📊 <b>Gap Analysis</b>\nTidak ada gap signifikan\n"

    # ================= NEWS =================
    sentiment = news_result.get("sentiment", "NEUTRAL")

    sentiment_icon = {
        "POSITIVE": "🟢",
        "NEGATIVE": "🔴",
        "SPECULATIVE": "🟣",
    }.get(sentiment, "⚪")

    news_lines = ""
    for n in news_result.get("news", [])[:5]:
        if n.get("title") and n.get("link"):
            news_lines += f'• <a href="{n["link"]}">{n["title"]}</a>\n'

    news_lines = news_lines.rstrip()

    # ================= FINAL MESSAGE =================
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