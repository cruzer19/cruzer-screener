import logging
from datetime import datetime
import pandas as pd

from app.config.saham_list import SAHAM_LIST
from app.services.data import get_price_data
from app.services.logic import detect_day_trade, detect_market_mover
from app.services.telegram_bot import send_message


def scan_day(state=None):

    if state is None:
        state = {
            "alerted": {},
            "last_status": {}
        }

    results = []
    alerts = []

    # ================= STATE =================
    alerted = state.get("alerted", {})
    last_status = state.get("last_status", {})

    scanned = 0
    movers = 0

    # ================= LOOP =================
    for ticker in SAHAM_LIST:

        try:
            scanned += 1

            df = get_price_data(ticker)
            if df is None or df.empty:
                continue

            # ================= MARKET MOVERS FILTER =================
            if not detect_market_mover(df):
                continue

            movers += 1
            print(f"MOVER: {ticker}")

            # ================= MAIN LOGIC =================
            data = detect_day_trade(df)
            if not data:
                continue

            status = data.get("status")
            score = data.get("score", 0)

            price = data.get("price")
            entry_low = data.get("entry_low")
            entry_high = data.get("entry_high")
            sl = data.get("sl")

            vol_ratio = data.get("vol_ratio", 1)

            prev_status = last_status.get(ticker)

            print(f"SIGNAL: {ticker} | {status} | {score}")

            # ================= ALERT TYPE =================
            alert_type = None

            if status == "🔥 Breakout" and score >= 55:
                alert_type = "breakout"

            elif status == "🚀 Early Breakout" and score >= 55:
                alert_type = "early"

            elif status == "⚡ Pre-Breakout" and score >= 50:
                alert_type = "pre"

            elif status == "📈 Strong Trend" and score >= 50:
                alert_type = "trend"

            elif status == "🧲 Rebound ARB" and score >= 45:
                alert_type = "arb"

            elif prev_status == "🔥 Breakout" and status != "🔥 Breakout":
                alert_type = "fake"

            # ================= FILTER FAKE =================
            if alert_type == "fake":
                last_status[ticker] = status
                continue

            # ================= ANTI SPAM =================
            key = None
            if alert_type:
                key = f"{ticker}_{alert_type}"

            # ================= MESSAGE =================
            if alert_type and key not in alerted:

                now = datetime.now().strftime("%d %b %Y %H:%M:%S")
                entry_range = f"{entry_low or '-'} - {entry_high or '-'}"
                sl = sl or "-"

                if alert_type == "breakout":
                    msg = (
                        f"🔥 <b>BREAKOUT (DAY)</b>\n"
                        f"<b>{ticker}</b> @ {price}\n"
                        f"🎯 Entry  : {entry_range}\n"
                        f"🛑 SL     : {sl}\n"
                        f"⭐ <b>Score : {score}</b>\n"
                        f"📊 Vol    : {vol_ratio}x\n"
                        f"⏰ {now}"
                    )

                elif alert_type == "early":
                    msg = (
                        f"🚀 <b>EARLY BREAKOUT</b>\n"
                        f"<b>{ticker}</b> @ {price}\n"
                        f"🎯 Entry  : {entry_range}\n"
                        f"🛑 SL     : {sl}\n"
                        f"⭐ <b>Score : {score}</b>\n"
                        f"📊 Vol    : {vol_ratio}x\n"
                        f"⏰ {now}"
                    )

                elif alert_type == "pre":
                    msg = (
                        f"⚡ <b>PRE-BREAKOUT (DAY)</b>\n"
                        f"<b>{ticker}</b> @ {price}\n"
                        f"🎯 Entry  : {entry_range}\n"
                        f"🛑 SL     : {sl}\n"
                        f"⭐ <b>Score : {score}</b>\n"
                        f"📊 Vol    : {vol_ratio}x\n"
                        f"⏰ {now}"
                    )

                elif alert_type == "trend":
                    msg = (
                        f"📈 <b>STRONG TREND</b>\n"
                        f"<b>{ticker}</b> @ {price}\n"
                        f"⭐ <b>Score : {score}</b>\n"
                        f"📊 Vol    : {vol_ratio}x\n"
                        f"⏰ {now}"
                    )

                elif alert_type == "arb":
                    msg = (
                        f"🧲 <b>ARB REBOUND</b>\n"
                        f"<b>{ticker}</b> @ {price}\n"
                        f"⚠️ Near lower limit\n"
                        f"📊 Volume spike detected\n"
                        f"⭐ <b>Score : {score}</b>\n"
                        f"⏰ {now}"
                    )

                try:
                    send_message(msg)
                    logging.info(f"📨 Alert sent: {ticker} | {status} | {score}")
                except Exception as e:
                    logging.error(f"❌ Telegram error {ticker}: {e}")

                alerts.append(msg)
                alerted[key] = True

            # ================= SAVE STATUS =================
            last_status[ticker] = status

            # ================= RESULT FILTER =================
            if (
                (status == "🔥 Breakout" and score >= 55) or
                (status == "🚀 Early Breakout" and score >= 55) or
                (status == "⚡ Pre-Breakout" and score >= 50) or
                (status == "📈 Strong Trend" and score >= 50) or
                (status == "🧲 Rebound ARB" and score >= 45)
            ):
                results.append({
                    "Kode": ticker,
                    "Harga": price,
                    "Score": score,
                    "Status": status,
                    "Volume": vol_ratio
                })

        except Exception as e:
            logging.error(f"❌ ERROR {ticker}: {e}")
            continue

    # ================= DATAFRAME =================
    df = pd.DataFrame(results)

    if not df.empty:
        df = (
            df.sort_values(by=["Score"], ascending=False)
            .reset_index(drop=True)
        )

        df.index = df.index + 1
        df = df.head(10)

    # ================= UPDATE STATE =================
    state["alerted"] = alerted
    state["last_status"] = last_status

    # ================= FINAL DEBUG =================
    print(f"\nSCAN: {scanned}")
    print(f"MOVERS: {movers}")
    print(f"RESULT: {len(results)}")
    print(f"ALERT: {len(alerts)}\n")

    logging.info(f"Scan {scanned} saham | Movers {movers} | Alert {len(alerts)}")

    return df, alerts, state