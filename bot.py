from dotenv import load_dotenv
load_dotenv()

import logging
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from app.core.scanner import scan_day


# ==========================================================
# ===================== CONFIG TIMEZONE =====================
# ==========================================================
TZ = ZoneInfo("Asia/Jakarta")


# ==========================================================
# ===================== LOGGING =============================
# ==========================================================
logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# ==========================================================
# ===================== CONFIG ==============================
# ==========================================================
INTERVAL = 180  # scan setiap 3 menit


# ==========================================================
# ===================== MARKET TIME =========================
# ==========================================================
def is_market_open():

    now = datetime.now(TZ).time()

    morning_open = (
        now >= dtime(9, 0) and
        now <= dtime(12, 0)
    )

    afternoon_open = (
        now >= dtime(13, 30) and
        now <= dtime(16, 0)
    )

    return morning_open or afternoon_open


# ==========================================================
# ===================== MAIN LOOP ===========================
# ==========================================================
def run_bot():

    print("🚀 BOT STARTED...")
    logging.info("BOT STARTED")

    state = {
        "alerted": {},
        "last_status": {},
        "date": datetime.now(TZ).date()
    }

    while True:

        try:

            now = datetime.now(TZ)

            # ================= RESET DAILY =================
            if now.date() != state["date"]:

                print("🔄 Reset Daily State")
                logging.info("Reset Daily State")

                state = {
                    "alerted": {},
                    "last_status": {},
                    "date": now.date()
                }

            # ================= MARKET CHECK =================
            if not is_market_open():

                print("⏸ Market Closed - Sleeping 5 minutes")
                time.sleep(300)
                continue

            print(f"\n🕒 Scan Time: {now.strftime('%H:%M:%S')}")

            # ================= RUN SCANNER =================
            df, alerts, state = scan_day(state)

            print(f"📊 Top Result : {len(df)}")
            print(f"🚨 Alerts Sent: {len(alerts)}")

            logging.info(f"Scan Result {len(df)} | Alerts {len(alerts)}")

            # ================= OPTIONAL DEBUG =================
            if not df.empty:
                print(df)

        except Exception as e:

            print("❌ BOT ERROR:", e)
            logging.error(f"BOT ERROR: {e}")

            time.sleep(30)

        time.sleep(INTERVAL)


# ==========================================================
# ===================== ENTRY POINT =========================
# ==========================================================
if __name__ == "__main__":
    run_bot()