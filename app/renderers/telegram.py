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

        return (
            int(score)
            if score.is_integer()
            else round(score, 1)
        )

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

    market_open = (
        time(9, 0) <= now <= time(16, 0)
    )

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


# ================= FORMAT STOCK =================
def format_stock_block(r, idx):

    kode = r.get("Kode", "-")
    harga = r.get("Harga", "-")

    score = format_score(
        r.get("Score", 0)
    )

    setup = r.get("Setup", "-")
    trend = r.get("Trend", "-")
    entry = r.get("Entry", "-")

    tp_raw = r.get("TP", "-")
    sl = r.get("SL", "-")

    tp1, tp2, tp3 = split_tp(tp_raw)

    return (
        f"\n<b>{idx}. {kode}</b> ({harga}) | "
        f"<b>Score:</b> {score}/100\n"
        f"Setup       : {setup}\n"
        #f"Trend       : {trend}\n"
        f"Entry        : {entry}\n"
        f"TP1          : {tp1}\n"
        f"TP2          : {tp2}\n"
        f"SL             : {sl}\n"
    )

# ================= TRADING NOTES =================
def generate_trading_notes(state, change_pct):

    pct = f"{change_pct:+.2f}%"

    # ======================================================
    # STRONG BULL
    # ======================================================

    if "strong_bull" in state:

        return (
            "⚠️ <b>Trading Plan</b>\n"
            f"• IHSG sedang sangat kuat ({pct})\n"
            "• Aliran buyer masih dominan dan momentum naik masih terjaga\n"
            "• Selama market tidak breakdown support intraday, peluang lanjut naik masih besar\n"
            "• Fokus cari entry saat pullback sehat, jangan terlalu agresif chase hijau tinggi\n"
            "• Hari ini market berpotensi lanjut bullish"
        )

    # ======================================================
    # BULL
    # ======================================================

    elif "bull" in state:

        return (
            "⚠️ <b>Trading Plan</b>\n"
            f"• IHSG masih bergerak positif ({pct})\n"
            "• Buyer masih cukup kuat menjaga trend naik market\n"
            "• Selama volume tetap bagus, peluang naik masih terbuka\n"
            "• Fokus entry dekat support atau saat breakout valid\n"
            "• Hari ini market cenderung masih menguat"
        )

    # ======================================================
    # BEAR
    # ======================================================

    elif "bear" in state:

        return (
            "⚠️ <b>Trading Plan</b>\n"
            f"• IHSG mulai melemah ({pct})\n"
            "• Tekanan jual mulai terasa dan market agak rawan fake breakout\n"
            "• Sebaiknya lebih selektif pilih saham dengan volume dan momentum kuat\n"
            "• Hindari terlalu banyak entry di saham yang trend-nya belum jelas\n"
            "• Hari ini market cenderung bergerak mixed ke bearish"
        )

    # ======================================================
    # STRONG BEAR
    # ======================================================

    elif "strong_bear" in state:

        return (
            "⚠️ <b>Trading Plan</b>\n"
            f"• IHSG sedang dalam tekanan cukup besar ({pct})\n"
            "• Seller masih mendominasi dan risk market cukup tinggi\n"
            "• Potensi panic sell atau breakdown support masih perlu diwaspadai\n"
            "• Prioritaskan risk management dan jangan terlalu agresif entry\n"
            "• Hari ini market berpotensi lanjut melemah"
        )

    # ================= SIDEWAYS =================

    else:

        return (
            "⚠️ <b>Trading Plan</b>\n"
            f"• IHSG masih bergerak sideways ({pct})\n"
            "• Buyer dan seller masih sama-sama menahan arah market\n"
            "• Pergerakan saham kemungkinan masih naik turun tipis dan belum terlalu agresif\n"
            "• Fokus cari saham yang tetap kuat meski IHSG belum naik signifikan\n"
            "• Hari ini market kemungkinan masih cenderung datar dengan pergerakan terbatas"
        )

# ================= MAIN RENDER =================
def render_telegram(
    results,
    df_ihsg=None,
    title: str = "CRUZER AI - SWING TRADE PLAN",
    max_items: int = 9
) -> str:

    now = datetime.now()

    today = now.strftime("%d %B %Y")
    time_now = now.strftime("%H:%M WIB")

    msg = f"""
🤖 <b>{title}</b>
📅 {today} | ⏰ {time_now}
📡 Real-time Price Based
"""

    SEPARATOR = "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"

    # ======================================================
    # FILTER VALID
    # ======================================================

    valid_results = []

    for r in results:

        try:

            score = float(
                r.get("Score", 0)
            )

            if score > 0:
                valid_results.append(r)

        except Exception:
            pass

    # ======================================================
    # SORT BY SCORE
    # ======================================================

    valid_results.sort(
        key=lambda x: float(
            x.get("Score", 0)
        ),
        reverse=True
    )

    # ======================================================
    # TOP 9 ONLY
    # ======================================================

    top_results = valid_results[:max_items]

    # ======================================================
    # HEADER SECTION
    # ======================================================

    msg += (
        f"{SEPARATOR}"
        f"🔥 <b>TOP SWING PICKS</b>\n"
    )

    # ======================================================
    # STOCK LIST
    # ======================================================

    if top_results:

        for i, r in enumerate(top_results, 1):

            msg += format_stock_block(r, i)

    else:

        msg += (
            "\n⚠️ Tidak ada setup valid hari ini\n"
        )

    # ======================================================
    # NOTES
    # ======================================================

    msg += SEPARATOR

    if df_ihsg is not None:

        try:

            state, change_pct = (
                get_market_condition(df_ihsg)
            )

            notes = generate_trading_notes(
                state,
                change_pct
            )

        except Exception:

            notes = (
                "⚠️ <b>Trading Notes</b>\n"
                "• Gagal membaca kondisi market"
            )

    else:

        notes = (
            "⚠️ <b>Trading Notes</b>\n"
            "• Data IHSG tidak tersedia"
        )

    msg += (
        f"{notes}\n\n"
        f"🤖 Cruzer AI - Swing Engine v2"
    )

    return msg


# ================= TELEGRAM SENDER =================
def send_telegram_message(text: str) -> None:

    bot_token = os.getenv(
        "TELEGRAM_BOT_TOKEN"
    )

    chat_id = os.getenv(
        "TELEGRAM_CHAT_ID"
    )

    if not bot_token or not chat_id:

        raise RuntimeError(
            "Telegram env vars not set"
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{bot_token}/sendMessage"
    )

    payload = {

        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"

    }

    response = requests.post(
        url,
        json=payload,
        timeout=10
    )

    if response.status_code != 200:

        raise RuntimeError(
            f"Telegram send failed: "
            f"{response.status_code} "
            f"{response.text}"
        )