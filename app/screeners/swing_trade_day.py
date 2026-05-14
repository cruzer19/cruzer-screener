from app.screeners.base import BaseScreener
from app.models.stock_result import StockResult

from app.core.data_loader import load_daily_data
from app.core.indicators import ema, macd

from app.utils.helpers import round_down, round_up


class SwingTradeDayScreener(BaseScreener):

    """
    ARA Hunter — Hybrid Smart Momentum

    Filosofi:
    - Filter tetap simple & cepat
    - Bisa nangkep reversal awal
    - Bisa nangkep saham baru mulai naik
    - Ranking pakai bonus score
    - Tidak terlalu telat seperti screener indikator berat
    """

    screener_type = "ara_hunter"

    def analyze(self, kode: str):

        # ======================================================
        # LOAD DATA
        # ======================================================

        df = load_daily_data(kode)

        if df is None or len(df) < 30:
            return None

        # ======================================================
        # PRICE DATA
        # ======================================================

        close = df["Close"]

        open_price = df["Open"]

        high = df["High"]

        low = df["Low"]

        volume = df["Volume"]

        # ======================================================
        # LAST VALUES
        # ======================================================

        last_close = float(close.iloc[-1])

        prev_close = float(close.iloc[-2])

        last_open = float(open_price.iloc[-1])

        last_high = float(high.iloc[-1])

        last_low = float(low.iloc[-1])

        vol_last = float(volume.iloc[-1])

        vol_prev = float(volume.iloc[-2])

        # ======================================================
        # MA5
        # ======================================================

        ma5 = close.rolling(5).mean()

        ma5_last = float(ma5.iloc[-1])

        ma5_prev = float(ma5.iloc[-2])

        # ======================================================
        # EMA20
        # ======================================================

        ema20 = ema(close, 20)

        ema20_last = float(ema20.iloc[-1])

        ema20_prev = float(ema20.iloc[-2])

        # ======================================================
        # MACD
        # ======================================================

        macd_line, signal_line, hist = macd(close)

        macd_last = float(macd_line.iloc[-1])

        signal_last = float(signal_line.iloc[-1])

        macd_prev = float(macd_line.iloc[-2])

        signal_prev = float(signal_line.iloc[-2])

        # ======================================================
        # VOLUME MA20
        # ======================================================

        vol_ma20 = volume.rolling(20).mean()

        vol_ma_last = float(vol_ma20.iloc[-1])

        # ======================================================
        # BASIC CALCULATION
        # ======================================================

        return_pct = (
            (last_close - prev_close)
            / prev_close
        ) * 100

        gap_pct = (
            (last_open - prev_close)
            / prev_close
        ) * 100

        body_pct = (
            abs(last_close - last_open)
            / max(last_open, 1)
        ) * 100

        close_near_high = (
            (last_high - last_close)
            / max(last_high, 1)
        ) * 100

        vol_ratio = vol_last / max(vol_ma_last, 1)

        distance_from_ma5 = (
            (last_close - ma5_last)
            / ma5_last
        ) * 100

        # ======================================================
        # FILTER UTAMA (JANGAN TERLALU KETAT)
        # ======================================================

        conditions = [

            # volume minimal
            vol_last >= 1_000_000,

            # ada momentum
            return_pct >= 1,

            # breakout MA5
            last_close > ma5_last,

            # candle hijau
            last_close > last_open,

            # naik dari yesterday
            last_close > prev_close,

            # sebelumnya masih dekat MA5
            prev_close <= ma5_prev * 1.02,

            # gap tidak terlalu tinggi
            last_open <= (prev_close * 1.05),
        ]

        if not all(conditions):
            return None

        # ======================================================
        # SCORING SYSTEM
        # ======================================================

        score = 50

        score_breakdown = {}

        # ======================================================
        # 🟢 VOLUME EXPLOSION
        # ======================================================

        if vol_ratio >= 10:

            score += 25
            score_breakdown["Volume"] = 25

        elif vol_ratio >= 5:

            score += 20
            score_breakdown["Volume"] = 20

        elif vol_ratio >= 3:

            score += 15
            score_breakdown["Volume"] = 15

        elif vol_ratio >= 2:

            score += 10
            score_breakdown["Volume"] = 10

        else:

            score_breakdown["Volume"] = 0

        # ======================================================
        # 🟢 BODY EXPANSION
        # ======================================================

        if body_pct >= 20:

            score += 20
            score_breakdown["Body"] = 20

        elif body_pct >= 10:

            score += 15
            score_breakdown["Body"] = 15

        elif body_pct >= 5:

            score += 10
            score_breakdown["Body"] = 10

        elif body_pct >= 2:

            score += 5
            score_breakdown["Body"] = 5

        else:

            score_breakdown["Body"] = 0

        # ======================================================
        # 🟢 CLOSE NEAR HIGH
        # ======================================================

        if close_near_high <= 0.3:

            score += 20
            score_breakdown["Close Near High"] = 20

        elif close_near_high <= 1:

            score += 15
            score_breakdown["Close Near High"] = 15

        elif close_near_high <= 2:

            score += 8
            score_breakdown["Close Near High"] = 8

        else:

            score_breakdown["Close Near High"] = 0

        # ======================================================
        # 🟢 MOMENTUM
        # ======================================================

        if return_pct >= 25:

            score += 15
            score_breakdown["Momentum"] = 15

        elif return_pct >= 15:

            score += 12
            score_breakdown["Momentum"] = 12

        elif return_pct >= 10:

            score += 10
            score_breakdown["Momentum"] = 10

        elif return_pct >= 5:

            score += 7
            score_breakdown["Momentum"] = 7

        else:

            score_breakdown["Momentum"] = 0

        # ======================================================
        # 🟢 GAP SAFE
        # ======================================================

        if 0 <= gap_pct <= 2:

            score += 10
            score_breakdown["Gap Safe"] = 10

        elif gap_pct <= 5:

            score += 5
            score_breakdown["Gap Safe"] = 5

        else:

            score_breakdown["Gap Safe"] = 0

        # ======================================================
        # 🟢 EMA20 BONUS
        # ======================================================

        if (
            last_close >= ema20_last
            and ema20_last >= ema20_prev
        ):

            score += 5
            score_breakdown["EMA20"] = 5

        else:

            score_breakdown["EMA20"] = 0

        # ======================================================
        # 🟢 MACD BONUS
        # ======================================================

        if (
            macd_prev <= signal_prev
            and macd_last > signal_last
        ):

            score += 5
            score_breakdown["MACD"] = 5

        elif macd_last > signal_last:

            score += 3
            score_breakdown["MACD"] = 3

        else:

            score_breakdown["MACD"] = 0

        # ======================================================
        # 🔴 OVEREXTENDED PENALTY
        # ======================================================

        if distance_from_ma5 >= 30:

            score -= 15
            score_breakdown["Overextended"] = -15

        elif distance_from_ma5 >= 20:

            score -= 8
            score_breakdown["Overextended"] = -8

        else:

            score_breakdown["Overextended"] = 0

        # ======================================================
        # 🔴 CLIMAX PENALTY
        # ======================================================

        if return_pct >= 35:

            score -= 10
            score_breakdown["Climax"] = -10

        else:

            score_breakdown["Climax"] = 0

        # ======================================================
        # PRICE ROUNDING
        # ======================================================

        last_price = round_down(last_close)

        # ======================================================
        # ENTRY AREA
        # ======================================================

        entry_low = round_down(
            max(last_open, ma5_last)
        )

        entry_high = round_up(last_close)

        # ======================================================
        # TAKE PROFIT
        # ======================================================

        tp1 = round_up(last_close * 1.03)

        tp2 = round_up(last_close * 1.06)

        tp3 = round_up(last_close * 1.10)

        # ======================================================
        # STOP LOSS
        # ======================================================

        sl = round_down(
            min(
                last_low * 0.99,
                ma5_last * 0.98
            )
        )

        # ======================================================
        # RR
        # ======================================================

        risk = max(last_price - sl, 1)

        reward = tp2 - last_price

        rr = round(reward / risk, 2)

        # ======================================================
        # RECOMMENDATION
        # ======================================================

        if score >= 100:

            recommendation = "🔥 TOP MOMENTUM"

        elif score >= 85:

            recommendation = "🚀 STRONG MOMENTUM"

        elif score >= 70:

            recommendation = "⚡ PRE-BREAKOUT"

        else:

            recommendation = "✅ WATCHLIST"

        # ======================================================
        # RESULT
        # ======================================================

        return StockResult(
            kode=kode,

            last_price=last_price,

            score=int(score),

            setup="ARA Hunter",

            trend="Early Momentum",

            entry_low=entry_low,

            entry_high=entry_high,

            tp=[tp1, tp2, tp3],

            sl=sl,

            rr=rr,

            recommendation=recommendation,

            screener_type=self.screener_type,

            score_breakdown=score_breakdown
        )

# ======================================================
# 📊 FAST TRADE SCORE ONLY
# ======================================================

def calculate_fast_trade_score(df):

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

        vol_ma_last = float(
            vol_ma20.iloc[-1]
        )

        vol_ratio = (
            vol_last /
            max(vol_ma_last, 1)
        )

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

        distance_ma5 = (
            (last_close - ma5_last)
            / max(ma5_last, 1)
        ) * 100

        # ======================================================
        # BASE SCORE
        # ======================================================

        score = 50

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

        if return_pct >= 20:

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

        if body_pct >= 10:

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

        # ======================================================
        # OVEREXTENDED PENALTY
        # ======================================================

        if distance_ma5 >= 30:

            score -= 20

        elif distance_ma5 >= 20:

            score -= 10

        # ======================================================
        # RED CANDLE PENALTY
        # ======================================================

        if last_close < last_open:

            score -= 10

        # ======================================================
        # LOW VOLUME PENALTY
        # ======================================================

        if vol_last < 1_000_000:

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

        print(f"FAST SCORE ERROR: {e}")

        return 0