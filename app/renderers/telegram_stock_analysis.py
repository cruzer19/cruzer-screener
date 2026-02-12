def render_stock_analysis_message(kode, timeframe, analysis, news_result, insight_text, df_price):
    from app.utils.analysis_engine import round_to_tick
    from app.utils.sector_utils import get_sector_badge
    from app.config.saham_profile import SAHAM_PROFILE
    from datetime import datetime

    # ================= BASIC DATA =================
    last_price = analysis["last_price"]
    support = analysis["support"]
    resistance = analysis["resistance"]
    trend = analysis["trend"]

    sector_emoji, sector_name = get_sector_badge(kode)
    company_name = SAHAM_PROFILE.get(kode, kode)

    # ================= SUPPORT STRUCTURE =================
    major_support = support
    minor_support = analysis.get("minor_support")
    micro_support = int(df_price["Low"].tail(7).min())

    supports = [("Micro", micro_support)]

    if minor_support:
        supports.append(("Minor", minor_support))
    if major_support:
        supports.append(("Major", major_support))

    supports_sorted = sorted(
        supports,
        key=lambda x: abs(last_price - x[1])
    )

    near_support = supports_sorted[0][1]
    near_label = supports_sorted[0][0]

    mid_support = supports_sorted[1][1] if len(supports_sorted) > 1 else near_support
    mid_label = supports_sorted[1][0] if len(supports_sorted) > 1 else near_label

    far_support = supports_sorted[2][1] if len(supports_sorted) > 2 else mid_support
    far_label = supports_sorted[2][0] if len(supports_sorted) > 2 else mid_label

    # ================= ENTRY PLAN =================
    entry_near_low = round_to_tick(near_support * 0.995)
    entry_near_high = round_to_tick(near_support * 1.015)

    entry_deep_low = round_to_tick(mid_support * 0.99)
    entry_deep_high = round_to_tick(mid_support * 1.02)

    risk_pct = analysis["risk_pct"]

    # ================= DATE FORMAT =================
    def fmt_date(date_str):
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%b-%Y")

    def fmt_range(start, end):
        s = fmt_date(start)
        e = fmt_date(end)
        return f"{s} — {e}"

    # ================= CYCLE =================
    cycle = analysis.get("cycle")

    cycle_low_text = ""
    cycle_high_text = ""

    if cycle:
        cycle_low_text = (
            f"\n<b>📉 Cycle Low Window</b>\n"
            f"Last Low  : {fmt_date(cycle['last_low'])}\n"
            f"Near Low : {fmt_range(cycle['next_low_start'], cycle['next_low_end'])}\n"
            f"Next Low : {fmt_range(cycle['second_low_start'], cycle['second_low_end'])}\n"
        )

        cycle_high_text = (
            f"\n<b>📈 Cycle High Window</b>\n"
            f"Near High : {fmt_range(cycle['next_high_start'], cycle['next_high_end'])}\n"
            f"Next High : {fmt_range(cycle['second_high_start'], cycle['second_high_end'])}\n"
        )

    # ================= SENTIMENT ICON =================
    sentiment = news_result.get("sentiment", "NEUTRAL")

    if sentiment == "POSITIVE":
        sentiment_icon = "🟢"
    elif sentiment == "NEGATIVE":
        sentiment_icon = "🔴"
    elif sentiment == "SPECULATIVE":
        sentiment_icon = "🟣"
    else:
        sentiment_icon = "⚪"

    # ================= CLICKABLE NEWS =================
    news_lines = ""
    if news_result.get("news"):
        for n in news_result["news"][:5]:
            if n.get("title") and n.get("link"):
                news_lines += f'\n• <a href="{n["link"]}">{n["title"]}</a>'

    # ================= FINAL MESSAGE =================
    msg = (
        f"<b>📊 STOCK ANALYSIS</b>\n"
        f"{sector_emoji} <b>{company_name}</b> ({kode})\n\n"

        f"<b>🧭 Market Condition</b>\n"
        f"Trend   : {trend}\n"
        f"Harga  : Rp {int(last_price):,}\n\n"

        f"<b>📉 Support & Resistance</b>\n"
        f"Support (Near) : Rp {int(near_support):,} ({near_label})\n"
        f"Support (Mid)   : Rp {int(mid_support):,} ({mid_label})\n"
        f"Support (Far)    : Rp {int(far_support):,} ({far_label})\n"
        f"Resistance        : Rp {int(resistance):,}\n\n"

        f"<b>🎯 Entry Plan</b>\n"
        f"Entry Near : Rp {entry_near_low:,} - Rp {entry_near_high:,}\n"
        f"Entry Deep : Rp {entry_deep_low:,} - Rp {entry_deep_high:,}\n"
        f"Risk            : {risk_pct} %\n"

        f"{cycle_low_text}"
        f"{cycle_high_text}\n"

        f"<b>📰 News & Sentiment</b>\n"
        f"{sentiment_icon} <b>{sentiment}</b>"
        f"{news_lines}\n\n"

        f"<b>🧠 Insight</b>\n"
        f"{insight_text}"
    )

    return msg.replace(",", ".")