from app.utils.sector_utils import get_sector_badge
from app.config.saham_profile import SAHAM_PROFILE

def render_stock_analysis_message(
    kode,
    timeframe,
    analysis,
    news_result,
    insight_text
):
    lines = []

    # =====================
    # HEADER
    # =====================
    emoji, sector = get_sector_badge(kode)
    company_name = SAHAM_PROFILE.get(kode, kode)

    lines.append("📊 <b>STOCK ANALYSIS</b>")
    lines.append(
        f"{emoji} <b>{company_name} ({kode}</b>)"
    )
    lines.append("")

    # =====================
    # MARKET CONDITION
    # =====================
    lines.append("🧭 <b>Market Condition</b>")
    lines.append(f"Trend  : <b>{analysis['trend']}</b>")
    lines.append(
        f"Harga  : Rp {analysis['last_price']:,}".replace(",", ".")
    )
    lines.append("")

    # =====================
    # SUPPORT RESISTANCE
    # =====================
    lines.append("📉 <b>Support & Resistance</b>")

    last_price = analysis["last_price"]
    major = analysis.get("support")
    minor = analysis.get("minor_support")
    resistance = analysis.get("resistance")

    supports = []

    if major is not None:
        supports.append(("Major", major))
    if minor is not None:
        supports.append(("Minor", minor))

    # Tentukan Near / Far
    if len(supports) == 2:
        supports_sorted = sorted(
            supports,
            key=lambda x: abs(last_price - x[1])
        )
        near_label, near_val = supports_sorted[0]
        far_label, far_val = supports_sorted[1]

        lines.append(
            f"Support (Near)  : Rp {int(near_val):,} ({near_label})".replace(",", ".")
        )
        lines.append(
            f"Support (Far)   : Rp {int(far_val):,} ({far_label})".replace(",", ".")
        )

    elif len(supports) == 1:
        label, val = supports[0]
        lines.append(
            f"Support ({label}) : Rp {val:,}".replace(",", ".")
        )

    # Resistance
    lines.append(
        f"Resistance     : Rp {resistance:,}".replace(",", ".")
    )
    lines.append("")


    # =====================
    # ENTRY PLAN
    # =====================
    entry_low, entry_high = analysis["entry_zone"]
    lines.append("🎯 <b>Entry Plan</b>")
    lines.append(
        f"Entry Zone : Rp {entry_low:,} – Rp {entry_high:,}".replace(",", ".")
    )
    lines.append(f"Risk             : {analysis['risk_pct']}%")
    lines.append("")

    # =====================
    # NEWS SENTIMENT
    # =====================
    sentiment = news_result["sentiment"]

    emoji_map = {
        "POSITIVE": "🟢",
        "NEGATIVE": "🔴",
        "SPECULATIVE": "🟡",
        "NEUTRAL": "⚪"
    }

    lines.append("📰 <b>News & Sentiment</b>")
    lines.append(f"{emoji_map.get(sentiment,'⚪')} <b>{sentiment}</b>")

    for n in news_result["news"][:5]:
        if n.get("link"):
            lines.append(
                f"• <a href=\"{n['link']}\">{n['title']}</a>"
            )
        else:
            lines.append(f"• {n['title']}")

    lines.append("")

    # =====================
    # INSIGHT
    # =====================
    lines.append("🧠 <b>Insight</b>")
    lines.append(insight_text)

    return "\n".join(lines)
