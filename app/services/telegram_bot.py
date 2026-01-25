import os
import requests

# ==========================================================
# TELEGRAM CONFIG
# ==========================================================
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Telegram hard limit = 4096
SAFE_LIMIT = 3800  # buffer aman biar gak silent fail


# ==========================================================
# INTERNAL SEND (1 CHUNK)
# ==========================================================
def _send_chunk(text: str, token: str, chat_id: str):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    r = requests.post(
        TELEGRAM_API.format(token=token),
        json=payload,
        timeout=10,
    )

    if not r.ok:
        raise RuntimeError(f"Telegram error {r.status_code}: {r.text}")


# ==========================================================
# PUBLIC SEND MESSAGE
# ==========================================================
def send_message(text: str):
    """
    Telegram sender (HTML mode):
    - SUPPORT <b>, <a>, dll
    - AUTO split message > 4096 char
    - NO silent fail
    """

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError("Telegram token / chat_id belum diset")

    if not text:
        raise ValueError("Telegram message is empty")

    # ======================================================
    # SHORT MESSAGE
    # ======================================================
    if len(text) <= SAFE_LIMIT:
        _send_chunk(text, token, chat_id)
        return

    # ======================================================
    # LONG MESSAGE → SPLIT
    # ======================================================
    parts = [
        text[i : i + SAFE_LIMIT]
        for i in range(0, len(text), SAFE_LIMIT)
    ]

    for idx, part in enumerate(parts, start=1):
        header = f"<b>📦 Part {idx}/{len(parts)}</b>\n\n"
        _send_chunk(header + part, token, chat_id)