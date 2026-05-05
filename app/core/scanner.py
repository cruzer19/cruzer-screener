import logging
from datetime import datetime
import pandas as pd

from app.config.saham_list import SAHAM_LIST
from app.services.data import get_price_data
from app.services.logic import detect_day_trade, detect_market_mover
from app.services.telegram_bot import send_message

from zoneinfo import ZoneInfo


def scan_day(state=None):

    if state is None:
        state = {
            "alerted": {},
            "last_status": {}
        }

    results = []
    alerts = []

    alerted = state.get("alerted", {})
    last_status = state.get("last_status", {})

    scanned = 0
    movers = 0

    for ticker in SAHAM_LIST:

        try:
            scanned += 1

            df = get_price_data(ticker)
            if df is None or df.empty:
                continue

            df.columns = [str(c).upper() for c in df.columns]

            # ================= BASIC DATA =================
            open_price = df["OPEN"].iloc[-1]
            low_price = df["LOW"].iloc[-1]
            close_price = df["CLOSE"].iloc[-1]

            vol = df["VOLUME"]
            avg_vol = vol.rolling(20).mean().iloc[-1]
            vol_ratio = vol.iloc[-1] / avg_vol if avg_vol else 1

            # 🔥 filter liquidity (ringan)
            if avg_vol < 300_000:
                continue

            body_pct = (close_price - open_price) / max(open_price, 1)

            # ================= OPEN LOW DETECTION =================
            is_open_low = abs(open_price - low_price) / max(low_price, 1) < 0.002

            # ================= MARKET MOVER =================
            is_mover = detect_market_mover(df)

            if is_mover:
                movers += 1

            # ================= MAIN LOGIC =================
            data = detect_day_trade(df)
            if not data:
                continue

            status = data.get("status")
            score = data.get("score", 0)

            status_display = status

            # ================= STRONG TREND ENHANCER (NEW) =================
            try:
                close_series = df["CLOSE"]
                high_series = df["HIGH"]
                low_series = df["LOW"]

                ma20 = close_series.rolling(20).mean().iloc[-1]
                ma50 = close_series.rolling(50).mean().iloc[-1]
                close_now = close_series.iloc[-1]

                # distance dari MA20
                distance = (close_now - ma20) / ma20 if ma20 else 0

                # range 5 hari (deteksi konsolidasi)
                high_5d = high_series.tail(5).max()
                low_5d = low_series.tail(5).min()
                range_pct = (high_5d - low_5d) / max(low_5d, 1)

                # ================= FILTER STRONG TREND =================
                is_strong_trend_v2 = (
                    close_now > ma20 and
                    ma20 > ma50 and
                    0.02 <= distance <= 0.10 and
                    range_pct < 0.08 and
                    vol_ratio >= 1.2
                )

                if is_strong_trend_v2:
                    score += 5

                    if "Strong Trend" in str(status):
                        status_display = f"{status_display} 🔥"
                    else:
                        status_display = f"{status_display} + 📈 Trend"

                    # ================= SNIPER MODE =================
                    if range_pct < 0.05:
                        score += 3

                        if vol_ratio >= 1.5:
                            score += 3
                            status_display = f"{status_display} + 🎯 Sniper"

            except:
                pass

            price = data.get("price")
            entry_low = data.get("entry_low")
            entry_high = data.get("entry_high")
            sl = data.get("sl")

            vol_ratio_data = data.get("vol_ratio", 1)
            vol_ratio = max(vol_ratio, vol_ratio_data)

            prev_status = last_status.get(ticker)

            # ================= OPEN LOW BOOST =================
            open_low_flag = False

            if is_open_low:
                open_low_flag = True

                if vol_ratio >= 2:
                    score += 6
                elif vol_ratio >= 1.5:
                    score += 8
                else:
                    score += 4

            # 🔥 soft filter (bukan kill)
            if vol_ratio < 1.3:
                score -= 5

            if body_pct < 0.015:
                score -= 5

            # ================= SOFT FILTER (NO MORE HARD SKIP) =================
            if not is_mover:
                score -= 5

            score = max(0, min(95, int(score)))

            if open_low_flag:
                status_display = f"{status_display} + 🚀 Open Low"
            else:
                status_display = status

            if score >= 70:
                print(f"SIGNAL: {ticker} | {status_display} | {score} | {vol_ratio:.2f}")

            # ================= ALERT TYPE =================
            alert_type = None

            if score >= 70:
                if status == "🚀 Open Low Breakout":
                    alert_type = "openlow"
                elif status == "🔥 Breakout":
                    alert_type = "breakout"
                elif status == "🚀 Early Breakout":
                    alert_type = "early"
                elif status == "⚡ Pre-Breakout":
                    alert_type = "pre"
                elif status == "📈 Strong Trend":
                    alert_type = "trend"
                elif status == "🧲 Rebound ARB":
                    alert_type = "arb"

            # ================= FAKE FILTER =================
            if alert_type == "fake":
                last_status[ticker] = status
                continue

            # ================= ANTI SPAM =================
            key = None
            if alert_type:
                key = f"{ticker}_{alert_type}_{int(price)}"

            # ================= MESSAGE =================
            if score >= 65 and alert_type and key not in alerted:

                now = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d %b %Y %H:%M:%S")
                entry_range = f"{entry_low or '-'} - {entry_high or '-'}"
                sl = sl or "-"

                if alert_type == "openlow":
                    msg = (
                        f"🚀 <b>OPEN LOW BREAKOUT</b>\n"
                        f"<b>{ticker}</b> @ {price}\n"
                        f"🔥 Open = Low detected\n"
                        f"🎯 Entry  : {entry_range}\n"
                        f"🛑 SL       : {sl}\n"
                        f"⭐ <b>Score : {score}</b>\n"
                        f"📊 Vol      : {vol_ratio:.2f}x\n"
                        f"⏰ {now}"
                    )

                elif alert_type == "breakout":
                    msg = (
                        f"🔥 <b>BREAKOUT (DAY)</b>\n"
                        f"<b>{ticker}</b> @ {price}\n"
                        f"🎯 Entry  : {entry_range}\n"
                        f"🛑 SL       : {sl}\n"
                        f"⭐ <b>Score : {score}</b>\n"
                        f"📊 Vol      : {vol_ratio:.2f}x\n"
                        f"⏰ {now}"
                    )

                elif alert_type == "early":
                    msg = (
                        f"🚀 <b>EARLY BREAKOUT</b>\n"
                        f"<b>{ticker}</b> @ {price}\n"
                        f"🎯 Entry  : {entry_range}\n"
                        f"🛑 SL       : {sl}\n"
                        f"⭐ <b>Score : {score}</b>\n"
                        f"📊 Vol      : {vol_ratio:.2f}x\n"
                        f"⏰ {now}"
                    )

                elif alert_type == "pre":
                    msg = (
                        f"⚡ <b>PRE-BREAKOUT (DAY)</b>\n"
                        f"<b>{ticker}</b> @ {price}\n"
                        f"🎯 Entry  : {entry_range}\n"
                        f"🛑 SL       : {sl}\n"
                        f"⭐ <b>Score : {score}</b>\n"
                        f"📊 Vol      : {vol_ratio:.2f}x\n"
                        f"⏰ {now}"
                    )

                elif alert_type == "trend":
                    msg = (
                        f"📈 <b>STRONG TREND</b>\n"
                        f"<b>{ticker}</b> @ {price}\n"
                        f"⭐ <b>Score : {score}</b>\n"
                        f"📊 Vol      : {vol_ratio:.2f}x\n"
                        f"⏰ {now}"
                    )

                elif alert_type == "arb":
                    msg = (
                        f"🧲 <b>ARB REBOUND</b>\n"
                        f"<b>{ticker}</b> @ {price}\n"
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
            if score >= 70:
                results.append({
                    "Kode": ticker,
                    "Harga": price,
                    "Score": score,
                    "Status": status_display,
                    "Volume": round(vol_ratio, 2)
                })

        except Exception as e:
            logging.error(f"❌ ERROR {ticker}: {e}")
            continue

    # ================= DATAFRAME =================
    df = pd.DataFrame(results)

    if not df.empty:
        df = df.sort_values(by=["Score"], ascending=False).reset_index(drop=True)
        df.index = df.index + 1
        df = df.head(10)

    state["alerted"] = alerted
    state["last_status"] = last_status

    print(f"\nSCAN: {scanned}")
    print(f"MOVERS: {movers}")
    print(f"RESULT: {len(results)}")
    print(f"ALERT: {len(alerts)}\n")

    logging.info(f"Scan {scanned} saham | Movers {movers} | Alert {len(alerts)}")

    return df, alerts, state