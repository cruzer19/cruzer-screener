import requests
from app.config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# ==========================================================
# TELEGRAM CONFIG
# ==========================================================
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# Telegram hard limit = 4096
SAFE_LIMIT = 3800  # buffer aman biar gak silent fail


# ==========================================================
# INTERNAL SEND (1 CHUNK)
# ==========================================================
def _send_chunk(text: str):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    r = requests.post(TELEGRAM_API, json=payload, timeout=10)

    if not r.ok:
        raise RuntimeError(
            f"Telegram error {r.status_code}: {r.text}"
        )


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

    print(">>> SEND_MESSAGE CALLED")
    print(">>> TEXT LENGTH:", len(text))

    if not text:
        raise ValueError("Telegram message is empty")

    # ======================================================
    # SHORT MESSAGE
    # ======================================================
    if len(text) <= SAFE_LIMIT:
        _send_chunk(text)
        return

    # ======================================================
    # LONG MESSAGE → SPLIT
    # ======================================================
    parts = [
        text[i:i + SAFE_LIMIT]
        for i in range(0, len(text), SAFE_LIMIT)
    ]

    for idx, part in enumerate(parts, start=1):
        header = f"<b>📦 Part {idx}/{len(parts)}</b>\n\n"
        _send_chunk(header + part)