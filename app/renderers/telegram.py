from datetime import datetime, time
import requests
import os


# ================= UTIL =================
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


# ================= MARKET CONDITION =================
def get_market_condition(df_ihsg):

    if df_ihsg is None or df_ihsg.empty or len(df_ihsg) < 2:
        return "unknown", 0

    last = float(df_ihsg.iloc[-1]["CLOSE"])
    prev = float(df_ihsg.iloc[-2]["CLOSE"])

    change_pct = ((last - prev) / prev) * 100
    change_pct = round(change_pct, 2)

    now = datetime.now().time()
    market_open = time(9, 0) <= now <= time(16, 0)

    if change_pct >= 1.0:
        state = "strong_bull"
    elif change_pct >= 0.3:
        state = "bull"
    elif change_pct <= -1.0:
        state = "strong_bear"
    elif change_pct <= -0.3:
        state = "bear"
    else:
        state = "sideways"

    if not market_open:
        state = f"premarket_{state}"

    return state, change_pct


# ================= LEGACY (DIBIARKAN, TIDAK DIPAKAI) =================
def derive_signal(score, trend, rsi, entry: str, setup: str):
    return "🟡 Wait"


def derive_context(score, trend) -> str:
    return "Range Consolidation"


def format_rsi_status(rsi):
    return "⚪ Normal"


# ================= FORMAT PER STOCK (UPDATED) =================
def format_stock_block(r, idx):

    kode = r.get("Kode", "-")
    harga = r.get("Harga", "-")
    score = format_score(r.get("Score", 0))

    setup = r.get("Setup", "-")
    trend = r.get("Trend", "-")

    entry = r.get("Entry", "-")
    tp_raw = r.get("TP", "-")
    sl = r.get("SL", "-")

    tp1, tp2, _ = split_tp(tp_raw)

    return f"""
<b>{idx}. {kode}</b> ({harga}) | <b>Score:</b> {score}/100
Setup       : {setup}
Trend       : {trend}
Entry        : {entry}
TP1          : {tp1}
TP2          : {tp2}
SL             : {sl}
"""


# ================= TRADING NOTES (UPDATED) =================
def generate_trading_notes(state, change_pct):

    pct = f"{change_pct:+.2f}%"

    if "strong_bull" in state:
        return (
            "⚠️ <b>Trading Plan (Next Day)</b>\n"
            f"• IHSG strong bullish ({pct})\n"
            "• Bias: kemungkinan lanjut naik (continuation)\n"
            "• Skenario:\n"
            "  - Jika pullback → peluang entry terbaik\n"
            "  - Jika gap up tinggi → hindari kejar\n"
            "• Fokus: Acc + Uptrend (Early)\n"
            "• Strategi: buy on weakness, bukan strength"
        )

    elif "bull" in state:
        return (
            "⚠️ <b>Trading Plan (Next Day)</b>\n"
            f"• IHSG naik ({pct})\n"
            "• Bias: cenderung lanjut naik, tapi bisa pullback dulu\n"
            "• Skenario:\n"
            "  - Pullback sehat → entry opportunity\n"
            "  - Sideways → tunggu konfirmasi\n"
            "• Fokus: Early / Mid trend\n"
            "• Strategi: entry bertahap"
        )

    elif "bear" in state:
        return (
            "⚠️ <b>Trading Plan (Next Day)</b>\n"
            f"• IHSG melemah ({pct})\n"
            "• Bias: potensi lanjut turun / weak bounce\n"
            "• Skenario:\n"
            "  - Rebound lemah → peluang sell / avoid\n"
            "  - Jika ada reversal kuat → baru entry selektif\n"
            "• Fokus: Smart Accumulation\n"
            "• Strategi: tunggu konfirmasi, jangan agresif"
        )

    elif "strong_bear" in state:
        return (
            "⚠️ <b>Trading Plan (Next Day)</b>\n"
            f"• IHSG turun tajam ({pct})\n"
            "• Bias: high risk, bisa lanjut turun / dead cat bounce\n"
            "• Skenario:\n"
            "  - Rebound cepat → biasanya tidak sustain\n"
            "  - Breakdown lanjutan → hindari entry\n"
            "• Fokus: capital preservation\n"
            "• Strategi: wait & see"
        )

    else:
        return (
            "⚠️ <b>Trading Plan (Next Day)</b>\n"
            f"• IHSG sideways ({pct})\n"
            "• Bias: market masih wait & see\n"
            "• Skenario:\n"
            "  - Break atas → lanjut uptrend\n"
            "  - Break bawah → lanjut turun\n"
            "• Fokus: accumulation phase\n"
            "• Strategi: entry dekat support, jangan di tengah"
        )

# ================= MAIN RENDER (UPDATED) =================
def render_telegram(
    results,
    df_ihsg=None,
    title: str = "CRUZER AI - DAILY TRADING PLAN",
    max_items: int = 15
) -> str:

    now = datetime.now()
    today = now.strftime("%d %B %Y")
    time_now = now.strftime("%H:%M WIB")

    msg = f"""🤖 <b>{title}</b>
📅 {today} | ⏰ {time_now}
📡 Real-time Price Based
"""

    SEPARATOR = "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"

    # ================= GROUPING =================
    best = []
    accumulation = []

    for r in results:
        setup = str(r.get("Setup", ""))

        if "Uptrend" in setup:
            best.append(r)
        elif "Accumulation" in setup:
            accumulation.append(r)

    # ================= SORT =================
    best.sort(key=lambda x: float(x.get("Score", 0)), reverse=True)
    accumulation.sort(key=lambda x: float(x.get("Score", 0)), reverse=True)

    has_data = False

    # ================= ACC + UPTREND =================
    if best:
        has_data = True
        msg += f"{SEPARATOR}<b>🔥 ACCUMULATION + UPTREND</b>\n"
        for i, r in enumerate(best[:5], 1):
            msg += format_stock_block(r, i)

    # ================= SMART ACC =================
    if accumulation:
        has_data = True
        msg += f"{SEPARATOR}<b>🟢 SMART ACCUMULATION</b>\n"
        for i, r in enumerate(accumulation[:5], 1):
            msg += format_stock_block(r, i)

    # ================= EMPTY =================
    if not has_data:
        msg += "\n⚠️ Tidak ada setup valid hari ini\n"

    # ================= NOTES =================
    msg += SEPARATOR

    if df_ihsg is not None:
        try:
            state, change_pct = get_market_condition(df_ihsg)
            notes = generate_trading_notes(state, change_pct)
        except:
            notes = "⚠️ <b>Trading Notes</b>\n• Gagal membaca kondisi market"
    else:
        notes = "⚠️ <b>Trading Notes</b>\n• Data IHSG tidak tersedia"

    msg += f"{notes}\n\n🤖 Cruzer AI - Swing Engine v2"

    return msg


# ================= TELEGRAM SENDER =================
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