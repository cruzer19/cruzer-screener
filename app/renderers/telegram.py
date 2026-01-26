from datetime import datetime
import requests
import os


def split_tp(tp_str: str):
    if not tp_str or "/" not in tp_str:
        return tp_str, "-", "-"
    parts = [p.strip() for p in tp_str.split("/")]
    while len(parts) < 3:
        parts.append("-")
    return parts[0], parts[1], parts[2]


def format_score(score):
    try:
        score = float(score)
        return int(score) if score.is_integer() else round(score, 1)
    except Exception:
        return score


def derive_signal(score, trend, rsi, entry: str) -> str:
    """
    Output:
    - 🟢 BUY (Pullback)
    - 🟢 BUY (Breakout)
    - 🟡 HOLD (Trail Stop)
    - 🟡 WAIT
    """
    try:
        score = float(score)
        trend = float(trend)
        rsi = float(rsi)
    except Exception:
        return "🟡 WAIT"

    is_range_entry = "–" in entry or "-" in entry

    # HOLD: already extended
    if score >= 85 and rsi >= 65:
        return "🟡 Hold (Trail Stop)"

    # BUY BREAKOUT
    if trend >= 60 and 50 <= rsi <= 70 and not is_range_entry:
        return "🟢 Buy (Breakout)"

    # BUY PULLBACK
    if trend >= 40 and rsi <= 45 and is_range_entry:
        return "🟢 Buy (Pullback)"

    # WAIT
    if score < 70:
        return "🟡 Wait Confirmation"

    return "🟢 Buy (Pullback)"


def derive_context(score, trend) -> str:
    try:
        score = float(score)
        trend = float(trend)
    except Exception:
        return "Range Consolidation"

    if trend >= 60:
        return "Strong Uptrend"

    if score >= 80:
        return "Bullish Continuation"

    if trend >= 40:
        return "Bullish Pullback Zone"

    return "Range Consolidation"


def render_telegram(
    results,
    title: str = "CRUZER AI — DAILY TRADING PLAN",
    max_items: int = 10
) -> str:
    today = datetime.now().strftime("%d %B %Y")
    lines = []

    # ===== HEADER =====
    lines.append(f"🤖 <b>{title}</b>")
    lines.append(f"📅 {today}")
    lines.append("⏰ Last Price Based")
    lines.append("")

    results = results[:max_items]

    for idx, r in enumerate(results, start=1):
        kode = r.get("Kode", "-")
        harga = r.get("Harga", "-")
        score = r.get("Score", 0)

        trend = r.get("Trend", 0)
        rsi = r.get("RSI", 0)

        entry = r.get("Entry", "-")
        tp_raw = r.get("TP", "-")
        sl = r.get("SL", "-")
        gain = r.get("Gain (%)", "0")

        setup = r.get("Setup", "Swing Setup")

        # numeric parse
        score_val = format_score(score)

        try:
            gain_val = float(gain)
        except Exception:
            gain_val = 0

        # badges
        score_badge = "⭐ " if score_val >= 80 else ""
        gain_badge = "🚀 " if gain_val >= 8 else ""

        signal = derive_signal(score_val, trend, rsi, entry)
        context = derive_context(score_val, trend)

        tp1, tp2, tp3 = split_tp(tp_raw)

        # ===== DESK STYLE BLOCK =====
        lines.extend([
            f"{idx}. <b>{kode}</b> ({harga}) | {score_badge}<b>Score:</b> {score_val}/100",
            f"Setup       : 🎯 {setup}",
            f"Context   : {context}",
            f"Entry        : {entry}",
            f"TP1          : {tp1}",
            f"TP2          : {tp2}",
            f"TP3          : {tp3}",
            f"SL             : {sl}",
            f"RR             : {gain_badge}+{gain_val}%",
            f"Rec           : {signal}",
            ""
        ])

    # ===== FOOTER =====
    lines.append("⚠️ Trading Notes:")
    lines.append("• Semua setup masih berada di fase konsolidasi, belum entry agresif.")
    lines.append("• Prioritaskan entry saat harga mendekati area dengan konfirmasi volume.")
    lines.append("• Jangan FOMO, lebih baik ketinggalan peluang daripada salah entry.")
    lines.append("• Risk terkontrol > profit besar.")
    lines.append("")
    lines.append("🤖 Cruzer AI — Auto Screener System")

    return "\n".join(lines)


def send_telegram_message(text: str) -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        raise RuntimeError("Telegram env vars not set")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    response = requests.post(url, json=payload, timeout=10)

    if response.status_code != 200:
        raise RuntimeError(
            f"Telegram send failed: {response.status_code} {response.text}"
        )