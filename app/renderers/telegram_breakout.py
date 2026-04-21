# ==========================================================
# ================= TELEGRAM SMART ALERT ====================
# ==========================================================
from datetime import datetime
import requests
import os


# ================= FORMAT MESSAGE =================
def format_smart_alert(alerts: list) -> str:

    if not alerts:
        return ""

    now = datetime.now().strftime("%d %b %Y %H:%M")

    lines = []
    lines.append("🚨 <b>CRUZER AI — SMART ALERT</b>")
    lines.append(f"⏰ {now}")
    lines.append("")

    breakout_list = []
    pre_list = []
    fake_list = []

    # ================= GROUPING =================
    for a in alerts:
        t = a.get("type")

        if t == "breakout":
            breakout_list.append(a)
        elif t == "pre":
            pre_list.append(a)
        elif t == "fake":
            fake_list.append(a)

    # ================= BREAKOUT =================
    if breakout_list:
        lines.append("🔥 <b>BREAKOUT CONFIRMED</b>")
        for i, a in enumerate(breakout_list, 1):

            lines.append(
                f"{i}. <b>{a['ticker']}</b> @ {a['price']}\n"
                f"   ⭐ Score: {round(a['score'],1)}\n"
                f"   🎯 RR: {a['rr']}\n"
            )
        lines.append("")

    # ================= PRE BREAKOUT =================
    if pre_list:
        lines.append("⚡ <b>PRE-BREAKOUT (WATCHLIST)</b>")
        for i, a in enumerate(pre_list, 1):

            lines.append(
                f"{i}. <b>{a['ticker']}</b> @ {a['price']}\n"
                f"   ⭐ Score: {round(a['score'],1)}\n"
                f"   🎯 RR: {a['rr']}\n"
            )
        lines.append("")

    # ================= FAKE BREAKOUT =================
    if fake_list:
        lines.append("❌ <b>FAKE BREAKOUT (AVOID)</b>")
        for i, a in enumerate(fake_list, 1):

            lines.append(
                f"{i}. <b>{a['ticker']}</b> @ {a['price']}\n"
                f"   ⭐ Score: {round(a['score'],1)}\n"
            )
        lines.append("")

    # ================= FOOTER =================
    lines.append("⚠️ Notes:")
    lines.append("• Breakout = valid continuation")
    lines.append("• Pre-breakout = siap meledak")
    lines.append("• Fake breakout = hindari / trap")
    lines.append("")
    lines.append("🤖 Cruzer AI Bot")

    return "\n".join(lines)


# ================= SEND TELEGRAM =================
def send_telegram_message(text: str):

    if not text:
        return

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass