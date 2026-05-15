import logging
import asyncio

from datetime import datetime

import pandas as pd

from concurrent.futures import ThreadPoolExecutor

from app.services.data import get_price_data
from app.services.logic import detect_day_trade, detect_market_mover
from app.services.telegram_bot import send_message

from zoneinfo import ZoneInfo

# ======================================================
# HOT LIST PRIORITY
# ======================================================

try:

    from app.config.hot_saham_list import HOT_SAHAM_LIST as SAHAM_LIST

    print("🔥 USING HOT_SAHAM_LIST")

except:

    from app.config.saham_list import SAHAM_LIST

    print("📦 USING FULL SAHAM_LIST")

# ======================================================
# CONFIG
# ======================================================

MAX_WORKERS = 9

executor = ThreadPoolExecutor(
    max_workers=MAX_WORKERS
)

# ======================================================
# PROCESS SINGLE TICKER
# ======================================================

def process_ticker_sync(
    ticker,
    state
):

    results = []

    alerts = []

    alerted = state.get("alerted", {})

    last_status = state.get("last_status", {})

    movers = 0

    try:

        # ======================================================
        # RETRY FETCH DATA
        # ======================================================

        MAX_RETRY = 2

        RETRY_DELAY = 0.5

        df = None

        for attempt in range(MAX_RETRY):

            try:

                df = get_price_data(ticker)

                if df is not None and not df.empty:

                    break

            except Exception as e:

                logging.warning(

                    f"[RETRY {attempt+1}/{MAX_RETRY}] "
                    f"{ticker}: {e}"

                )

            time.sleep(RETRY_DELAY)

        # ======================================================
        # FAILED FETCH
        # ======================================================

        if df is None or df.empty:

            return {

                "results": [],

                "alerts": [],

                "movers": 0

            }


        df.columns = [
            str(c).upper()
            for c in df.columns
        ]

        # ================= BASIC DATA =================

        open_price = df["OPEN"].iloc[-1]

        low_price = df["LOW"].iloc[-1]

        close_price = df["CLOSE"].iloc[-1]

        vol = df["VOLUME"]

        avg_vol = vol.rolling(20).mean().iloc[-1]

        vol_ratio = (
            vol.iloc[-1] / avg_vol
            if avg_vol else 1
        )

        # 🔥 filter liquidity

        if avg_vol < 300_000:

            return {
                "results": [],
                "alerts": [],
                "movers": 0
            }

        body_pct = (
            (close_price - open_price)
            / max(open_price, 1)
        )

        # ================= OPEN LOW =================

        is_open_low = (

            abs(open_price - low_price)
            / max(low_price, 1)

        ) < 0.002

        # ================= MARKET MOVER =================

        is_mover = detect_market_mover(df)

        if is_mover:
            movers += 1

        # ================= MAIN LOGIC =================

        data = detect_day_trade(df)

        if not data:

            return {
                "results": [],
                "alerts": [],
                "movers": movers
            }

        status = data.get("status")

        score = data.get("score", 0)

        status_display = status

        # ================= STRONG TREND =================

        try:

            close_series = df["CLOSE"]

            high_series = df["HIGH"]

            low_series = df["LOW"]

            ma20 = close_series.rolling(20).mean().iloc[-1]

            ma50 = close_series.rolling(50).mean().iloc[-1]

            close_now = close_series.iloc[-1]

            distance = (
                (close_now - ma20)
                / ma20
            ) if ma20 else 0

            high_5d = high_series.tail(5).max()

            low_5d = low_series.tail(5).min()

            range_pct = (
                (high_5d - low_5d)
                / max(low_5d, 1)
            )

            is_strong_trend_v2 = (

                close_now > ma20
                and ma20 > ma50
                and 0.02 <= distance <= 0.10
                and range_pct < 0.08
                and vol_ratio >= 1.2

            )

            if is_strong_trend_v2:

                score += 5

                if "Strong Trend" in str(status):

                    status_display = (
                        f"{status_display} 🔥"
                    )

                else:

                    status_display = (
                        f"{status_display} + 📈 Trend"
                    )

                # ================= SNIPER =================

                if range_pct < 0.05:

                    score += 3

                    if vol_ratio >= 1.5:

                        score += 3

                        status_display = (
                            f"{status_display} + 🎯 Sniper"
                        )

        except:
            pass

        price = data.get("price")

        entry_low = data.get("entry_low")

        entry_high = data.get("entry_high")

        sl = data.get("sl")

        vol_ratio_data = data.get(
            "vol_ratio",
            1
        )

        vol_ratio = max(
            vol_ratio,
            vol_ratio_data
        )

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

        # ================= SOFT FILTER =================

        if vol_ratio < 1.3:
            score -= 5

        if body_pct < 0.015:
            score -= 5

        if not is_mover:
            score -= 5

        score = max(
            0,
            min(95, int(score))
        )

        if open_low_flag:
            status_display = f"{status_display}"
        else:
            status_display = status

        if score >= 70:

            print(
                f"SIGNAL: "
                f"{ticker} | "
                f"{status_display} | "
                f"{score} | "
                f"{vol_ratio:.2f}"
            )

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

            return {
                "results": [],
                "alerts": [],
                "movers": movers
            }

        # ================= ANTI SPAM =================

        key = None

        if alert_type:

            key = (
                f"{ticker}_"
                f"{alert_type}_"
                f"{int(price)}"
            )

        # ================= MESSAGE =================

        if (
            score >= 65
            and alert_type
            and key not in alerted
        ):

            now = datetime.now(
                ZoneInfo("Asia/Jakarta")
            ).strftime(
                "%d %b %Y %H:%M:%S"
            )

            entry_range = (
                f"{entry_low or '-'} "
                f"- {entry_high or '-'}"
            )

            sl = sl or "-"

            msg = (
                f"🔥 <b>{status}</b>\n"
                f"<b>{ticker}</b> @ {price}\n"
                f"⭐ Score : {score}\n"
                f"📊 Vol   : {vol_ratio:.2f}x\n"
                f"⏰ {now}"
            )

            try:

                send_message(msg)

                logging.info(
                    f"📨 Alert sent: "
                    f"{ticker}"
                )

            except Exception as e:

                logging.error(
                    f"❌ Telegram "
                    f"{ticker}: {e}"
                )

            alerts.append(msg)

            alerted[key] = True

        # ================= SAVE STATUS =================

        last_status[ticker] = status

        # ================= RESULT =================

        if score >= 60:

            results.append({

                "Kode": ticker,

                "Harga": price,

                "Score": score,

                "Status": status_display,

                "Volume": round(vol_ratio, 2)

            })

        return {

            "results": results,

            "alerts": alerts,

            "movers": movers

        }

    except Exception as e:

        logging.error(
            f"❌ ERROR {ticker}: {e}"
        )

        return {

            "results": [],

            "alerts": [],

            "movers": 0

        }

# ======================================================
# ASYNC WRAPPER
# ======================================================

async def process_ticker(
    ticker,
    state
):

    loop = asyncio.get_running_loop()

    return await loop.run_in_executor(

        executor,

        process_ticker_sync,

        ticker,

        state

    )

# ======================================================
# MAIN ASYNC SCAN
# ======================================================

async def scan_day_async(state=None):

    if state is None:

        state = {

            "alerted": {},

            "last_status": {}

        }

    scanned = len(SAHAM_LIST)

    # ======================================================
    # TASKS
    # ======================================================

    tasks = [

        process_ticker(
            ticker,
            state
        )

        for ticker in SAHAM_LIST

    ]

    outputs = await asyncio.gather(*tasks)

    # ======================================================
    # MERGE RESULTS
    # ======================================================

    results = []

    alerts = []

    movers = 0

    for out in outputs:

        results.extend(
            out.get("results", [])
        )

        alerts.extend(
            out.get("alerts", [])
        )

        movers += out.get(
            "movers",
            0
        )

    # ======================================================
    # DATAFRAME
    # ======================================================

    df = pd.DataFrame(results)

    if not df.empty:

        df = df.sort_values(
            by=["Score"],
            ascending=False
        ).reset_index(drop=True)

        df.index = df.index + 1

        df = df.head(15)

    print(f"\nSCAN: {scanned}")

    print(f"MOVERS: {movers}")

    print(f"RESULT: {len(results)}")

    print(f"ALERT: {len(alerts)}\n")

    logging.info(

        f"Scan {scanned} saham | "
        f"Movers {movers} | "
        f"Alert {len(alerts)}"

    )

    return df, alerts, state

# ======================================================
# PUBLIC FUNCTION
# ======================================================

def scan_day(state=None):

    return asyncio.run(
        scan_day_async(state)
    )