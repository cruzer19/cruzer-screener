import logging
import asyncio

from datetime import datetime

import pandas as pd

from concurrent.futures import ThreadPoolExecutor

from app.services.data import get_price_data
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

# ==========================================================
# CONFIG
# ==========================================================

MAX_WORKERS = 9

executor = ThreadPoolExecutor(
    max_workers=MAX_WORKERS
)

# ==========================================================
# PROCESS SINGLE TICKER
# ==========================================================

def process_bsjp_ticker_sync(
    ticker,
    state
):

    results = []

    alerts = []

    alerted = state.get(
        "alerted",
        {}
    )

    try:

        # ==========================================================
        # RETRY FETCH DATA
        # ==========================================================

        MAX_RETRY = 2

        RETRY_DELAY = 1.0

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

        # ==========================================================
        # FAILED FETCH
        # ==========================================================

        if df is None or df.empty:

            return {

                "results": [],

                "alerts": []

            }

        df.columns = [

            str(c).upper()

            for c in df.columns

        ]

        # ==========================================================
        # 🔥 AMBIL DATA HARI INI SAJA
        # ==========================================================

        today = df.index[-1].date()

        df_today = df[
            df.index.date == today
        ]

        if (
            df_today is None
            or len(df_today) < 5
        ):

            return {

                "results": [],

                "alerts": []

            }

        # ================= DATA =================

        open_price = df_today["OPEN"].iloc[0]

        close_price = df_today["CLOSE"].iloc[-1]

        high_price = df_today["HIGH"].max()

        prev_close = df["CLOSE"].iloc[
            -len(df_today) - 1
        ]

        # ================= PRICE CHANGE =================

        price_change = (

            (high_price - open_price)

            / max(open_price, 1)

        ) * 100

        # ================= VOLUME =================

        day_vol = df_today["VOLUME"].sum()

        avg_vol = (

            df["VOLUME"]

            .rolling(20)

            .mean()

            .iloc[-1]

        )

        vol_ratio = (

            day_vol / avg_vol

            if avg_vol else 1

        )

        if avg_vol < 200_000:

            return {

                "results": [],

                "alerts": []

            }

        # ================= MA =================

        ma5 = (

            df["CLOSE"]

            .rolling(5)

            .mean()

            .iloc[-1]

        )

        ma20 = (

            df["CLOSE"]

            .rolling(20)

            .mean()

            .iloc[-1]

        )

        # ==========================================================
        # 🔥 FILTER
        # ==========================================================

        if price_change < 2:
            return {

                "results": [],

                "alerts": []

            }

        if vol_ratio < 1.1:
            return {

                "results": [],

                "alerts": []

            }

        if close_price < ma20:
            return {

                "results": [],

                "alerts": []

            }

        # ==========================================================
        # 🔥 SCORING
        # ==========================================================

        score = 0

        # ================= MOMENTUM =================

        momentum_score = min(
            price_change * 1.2,
            40
        )

        score += momentum_score

        # ================= VOLUME =================

        if vol_ratio >= 1:

            volume_score = min(
                (vol_ratio - 1) * 15,
                30
            )

        else:

            volume_score = -10

        score += volume_score

        # ================= TREND =================

        trend_score = 0

        if close_price > ma20:
            trend_score += 10

        if close_price > ma5:
            trend_score += 5

        if ma5 > ma20:
            trend_score += 5

        score += trend_score

        # ================= POSITION BONUS =================

        distance_from_ma = (
            (close_price - ma20)
            / ma20
        )

        if distance_from_ma > 0.3:

            score -= 15

        elif distance_from_ma > 0.2:

            score -= 5

        elif distance_from_ma < 0.05:

            score += 5

        # ================= FINAL =================

        score = int(

            max(
                0,
                min(100, score)
            )

        )

        status = "🚀 BSJP Momentum"

        print(

            f"BSJP: {ticker} | "

            f"score={score} | "

            f"chg={price_change:.2f}% | "

            f"vol={vol_ratio:.2f}"

        )

        # ================= SAVE =================
        if score >= 50:
            results.append({

                "Kode": ticker,

                "Harga": int(close_price),

                "Score": score,

                "Status": status,

                "Volume": round(
                    vol_ratio,
                    2
                )

            })

        # ================= ALERT =================

        key = f"{ticker}_bsjp"

        if (

            key not in alerted

            and score >= 75

        ):

            now = datetime.now(

                ZoneInfo("Asia/Jakarta")

            ).strftime(

                "%d %b %Y %H:%M:%S"

            )

            msg = (

                f"🚀 <b>BSJP MOMENTUM</b>\n"

                f"<b>{ticker}</b> @ "

                f"{int(close_price)}\n"

                f"⭐ <b>Score : {score}</b>\n"

                f"📊 Vol      : "

                f"{vol_ratio:.2f}x\n"

                f"📈 Change : "

                f"{price_change:.2f}%\n"

                f"⏰ {now}"

            )

            try:

                send_message(msg)

            except Exception:

                pass

            alerts.append(msg)

            alerted[key] = True

        return {

            "results": results,

            "alerts": alerts

        }

    except Exception as e:

        logging.error(
            f"❌ ERROR {ticker}: {e}"
        )

        return {

            "results": [],

            "alerts": []

        }

# ==========================================================
# ASYNC WRAPPER
# ==========================================================

async def process_bsjp_ticker(
    ticker,
    state
):

    loop = asyncio.get_running_loop()

    return await loop.run_in_executor(

        executor,

        process_bsjp_ticker_sync,

        ticker,

        state

    )

# ==========================================================
# MAIN ASYNC SCAN
# ==========================================================

async def scan_bsjp_async(state=None):

    if state is None:

        state = {

            "alerted": {}

        }

    scanned = len(SAHAM_LIST)

    results = []

    alerts = []

    # ==========================================================
    # TASKS
    # ==========================================================

    tasks = [

        process_bsjp_ticker(
            ticker,
            state
        )

        for ticker in SAHAM_LIST

    ]

    outputs = await asyncio.gather(
        *tasks
    )

    # ==========================================================
    # MERGE RESULTS
    # ==========================================================

    for out in outputs:

        results.extend(
            out.get("results", [])
        )

        alerts.extend(
            out.get("alerts", [])
        )

    # ================= OUTPUT =================

    df = pd.DataFrame(results)

    if not df.empty:

        df = df.sort_values(
            by=["Score"],
            ascending=False
        ).reset_index(drop=True)

        df.index = df.index + 1

        df = df.head(15)

    print(f"\nBSJP SCAN: {scanned}")

    print(f"RESULT: {len(results)}")

    print(f"ALERT: {len(alerts)}\n")

    return df, alerts, state

# ==========================================================
# PUBLIC FUNCTION
# ==========================================================

def scan_bsjp(state=None):

    return asyncio.run(
        scan_bsjp_async(state)
    )

# ==========================================================
# 📊 SINGLE STOCK BSJP SCORE
# ==========================================================

def calculate_bsjp_score(df):

    """
    BSJP Score untuk Stock Analysis UI
    """

    try:

        # ======================================================
        # VALIDATION
        # ======================================================

        if df is None or len(df) < 30:
            return 0

        # ======================================================
        # NORMALIZE COLUMN
        # ======================================================

        df = df.copy()

        df.columns = [
            str(c).strip().lower()
            for c in df.columns
        ]

        # ======================================================
        # DATA
        # ======================================================

        close = df["close"]

        open_price = df["open"]

        high = df["high"]

        low = df["low"]

        volume = df["volume"]

        # ======================================================
        # LAST VALUE
        # ======================================================

        last_close = float(close.iloc[-1])

        prev_close = float(close.iloc[-2])

        last_open = float(open_price.iloc[-1])

        last_high = float(high.iloc[-1])

        vol_last = float(volume.iloc[-1])

        # ======================================================
        # MOVING AVERAGE
        # ======================================================

        ma5 = close.rolling(5).mean()

        ma20 = close.rolling(20).mean()

        ma5_last = float(ma5.iloc[-1])

        ma20_last = float(ma20.iloc[-1])

        # ======================================================
        # VOLUME
        # ======================================================

        vol_ma20 = volume.rolling(20).mean()

        vol_ma20_last = float(
            vol_ma20.iloc[-1]
        )

        vol_ratio = (
            vol_last /
            max(vol_ma20_last, 1)
        )

        # ======================================================
        # RESISTANCE
        # ======================================================

        resistance = high.tail(20).max()

        breakout_distance = (
            (resistance - last_close)
            / max(last_close, 1)
        ) * 100

        # ======================================================
        # PRICE ACTION
        # ======================================================

        return_pct = (
            (last_close - prev_close)
            / max(prev_close, 1)
        ) * 100

        body_pct = (
            abs(last_close - last_open)
            / max(last_open, 1)
        ) * 100

        close_near_high = (
            (last_high - last_close)
            / max(last_high, 1)
        ) * 100

        distance_ma20 = (
            (last_close - ma20_last)
            / max(ma20_last, 1)
        ) * 100

        # ======================================================
        # BASE SCORE
        # ======================================================

        score = 50

        # ======================================================
        # BREAKOUT DISTANCE
        # ======================================================

        if breakout_distance <= 1:

            score += 20

        elif breakout_distance <= 3:

            score += 15

        elif breakout_distance <= 5:

            score += 10

        # ======================================================
        # VOLUME SCORE
        # ======================================================

        if vol_ratio >= 10:

            score += 25

        elif vol_ratio >= 5:

            score += 20

        elif vol_ratio >= 3:

            score += 15

        elif vol_ratio >= 2:

            score += 10

        elif vol_ratio >= 1:

            score += 5

        # ======================================================
        # MOMENTUM SCORE
        # ======================================================

        if return_pct >= 15:

            score += 20

        elif return_pct >= 10:

            score += 15

        elif return_pct >= 5:

            score += 10

        elif return_pct >= 2:

            score += 5

        # ======================================================
        # BODY SCORE
        # ======================================================

        if body_pct >= 8:

            score += 15

        elif body_pct >= 5:

            score += 10

        elif body_pct >= 2:

            score += 5

        # ======================================================
        # CLOSE NEAR HIGH
        # ======================================================

        if close_near_high <= 0.5:

            score += 15

        elif close_near_high <= 1:

            score += 10

        elif close_near_high <= 2:

            score += 5

        # ======================================================
        # TREND BONUS
        # ======================================================

        if last_close > ma5_last:

            score += 5

        if last_close > ma20_last:

            score += 5

        if ma5_last > ma20_last:

            score += 5

        # ======================================================
        # HEALTHY POSITION BONUS
        # ======================================================

        if distance_ma20 <= 5:

            score += 10

        elif distance_ma20 <= 10:

            score += 5

        # ======================================================
        # EXTENDED PENALTY
        # ======================================================

        if distance_ma20 >= 30:

            score -= 25

        elif distance_ma20 >= 20:

            score -= 15

        elif distance_ma20 >= 15:

            score -= 8

        # ======================================================
        # RED CANDLE PENALTY
        # ======================================================

        if last_close < last_open:

            score -= 10

        # ======================================================
        # LOW VOLUME PENALTY
        # ======================================================

        if vol_last < 200_000:

            score -= 10

        # ======================================================
        # NORMALIZE
        # ======================================================

        score = int(
            max(
                0,
                min(score, 100)
            )
        )

        return score

    except Exception as e:

        print(f"BSJP SCORE ERROR: {e}")

        return 0