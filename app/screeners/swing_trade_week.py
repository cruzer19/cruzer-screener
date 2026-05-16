import pandas as pd

from app.screeners.base import BaseScreener
from app.models.stock_result import StockResult

from app.core.data_loader import load_daily_data
from app.utils.helpers import round_down, round_up


# ======================================================
# GET LAST VALID INDEX
# ======================================================

def get_last_valid_idx(volume_series):

    idx = -1

    # cek max 5 candle ke belakang
    for i in range(1, 6):

        current_idx = -i

        vol = float(
            volume_series.iloc[current_idx]
        )

        # ada transaksi
        if vol > 0:

            idx = current_idx

            break

    return idx


class SwingTradeWeekScreener(BaseScreener):

    """
    Swing Trade Week
    Healthy Pullback + Rebound Strategy

    Fokus:
    - Uptrend sehat
    - Koreksi sehat
    - Near support
    - Liquid
    - Rebound potential
    """

    screener_type = "swing_trade_week"

    def analyze(self, kode: str):

        # ======================================================
        # LOAD DATA
        # ======================================================

        df = load_daily_data(kode)

        if df is None or len(df) < 100:
            return None

        # ======================================================
        # DATA
        # ======================================================

        close = df["Close"]

        open_price = df["Open"]

        high = df["High"]

        low = df["Low"]

        volume = df["Volume"]

        idx = get_last_valid_idx(volume)

        # ======================================================
        # LAST VALUE
        # ======================================================

        last_close = float(close.iloc[idx])

        prev_close = float(close.iloc[idx - 1])

        last_open = float(open_price.iloc[idx])

        last_high = float(high.iloc[idx])

        last_low = float(low.iloc[idx])

        vol_last = float(volume.iloc[idx])

        # ======================================================
        # MOVING AVERAGE
        # ======================================================

        ma5 = close.rolling(5).mean()

        ma20 = close.rolling(20).mean()

        ma50 = close.rolling(50).mean()

        ma100 = close.rolling(100).mean()

        ma5_last = float(ma5.iloc[idx])

        ma20_last = float(ma20.iloc[idx])

        ma50_last = float(ma50.iloc[idx])

        ma100_last = float(ma100.iloc[idx])

        # ======================================================
        # VOLUME
        # ======================================================

        vol_ma20 = volume.rolling(20).mean()

        vol_ma20_last = float(vol_ma20.iloc[idx])

        vol_ratio = (
            vol_last / max(vol_ma20_last, 1)
        )

        # ======================================================
        # LIQUIDITY
        # ======================================================

        traded_value = (
            last_close * vol_last
        )

        # ======================================================
        # PRICE ACTION
        # ======================================================

        return_pct = (
            (last_close - prev_close)
            / max(prev_close, 1)
        ) * 100

        distance_ma20 = (
            (last_close - ma20_last)
            / max(ma20_last, 1)
        ) * 100

        distance_ma50 = (
            (last_close - ma50_last)
            / max(ma50_last, 1)
        ) * 100

        distance_ma100 = (
            (last_close - ma100_last)
            / max(ma100_last, 1)
        ) * 100

        # ======================================================
        # PULLBACK ANALYSIS
        # ======================================================

        recent_high_5 = float(
            high.tail(5).max()
        )

        recent_high_10 = float(
            high.tail(10).max()
        )

        pullback_pct = (
            (last_close - recent_high_5)
            / max(recent_high_5, 1)
        ) * 100

        recent_low_10 = float(
            low.tail(10).min()
        )

        rebound_zone = (
            (last_close - recent_low_10)
            / max(recent_low_10, 1)
        ) * 100

        near_ma20 = (
            abs(distance_ma20) <= 3
        )

        # ======================================================
        # CANDLE ANALYSIS
        # ======================================================

        body_pct = (
            abs(last_close - last_open)
            / max(last_open, 1)
        ) * 100

        upper_wick = (
            (last_high - max(last_open, last_close))
            / max(last_close, 1)
        ) * 100

        lower_wick = (
            (min(last_open, last_close) - last_low)
            / max(last_low, 1)
        ) * 100

        close_near_high = (
            (last_high - last_close)
            / max(last_close, 1)
        ) * 100

        # ======================================================
        # VOLATILITY
        # ======================================================

        atr_pct = (
            (high.tail(14).max() - low.tail(14).min())
            / max(last_close, 1)
        ) * 100

        # ======================================================
        # TREND STABILITY
        # ======================================================

        trend_stability = (
            close.tail(20).std()
            / max(close.tail(20).mean(), 1)
        ) * 100

        # ======================================================
        # TREND ANALYSIS
        # ======================================================

        bullish_alignment = (

            ma20_last > ma50_last and
            ma50_last > ma100_last

        )

        ma20_uptrend = (
            ma20.iloc[idx] > ma20.iloc[idx - 4]
        )

        ma50_uptrend = (
            ma50.iloc[idx] > ma50.iloc[idx - 4]
        )

        # ======================================================
        # FILTER
        # ======================================================

        failed = []

        # ======================================================
        # BASIC FILTER
        # ======================================================

        # minimum volume
        if vol_last < 500_000:
            failed.append("Low Volume")

        # minimum liquidity
        if traded_value < 3_000_000_000:
            failed.append("Low Liquidity")

        # trend besar bullish
        if not bullish_alignment:
            failed.append("Weak Alignment")

        # MA50 wajib naik
        if not ma50_uptrend:
            failed.append("MA50 Downtrend")

        # boleh sedikit di bawah MA20
        if distance_ma20 < -4:
            failed.append("Too Weak Below MA20")

        # ======================================================
        # HEALTHY PULLBACK FILTER
        # ======================================================

        if distance_ma20 >= 12:
            failed.append("Too Extended")

        if pullback_pct <= -18:
            failed.append("Too Deep Pullback")

        # ======================================================
        # REBOUND FILTER
        # ======================================================

        if rebound_zone >= 35:
            failed.append("Too Far From Support")

        # ======================================================
        # REJECT
        # ======================================================

        if failed:

            print(
                f"❌ {kode} -> {', '.join(failed)}"
            )

            return None

        # ======================================================
        # SCORE
        # ======================================================

        score = 40

        # ======================================================
        # TREND SCORE
        # ======================================================

        if bullish_alignment:
            score += 10

        if ma20_uptrend:
            score += 6
        else:
            score -= 4

        if ma50_uptrend:
            score += 6

        if last_close > ma20_last:
            score += 4

        # ======================================================
        # PULLBACK SCORE
        # ======================================================

        if near_ma20:
            score += 8

        if -12 <= pullback_pct <= -2:
            score += 10

        elif -18 <= pullback_pct <= -12:
            score += 4

        # ======================================================
        # REBOUND SCORE
        # ======================================================

        if lower_wick >= 4:
            score += 8

        elif lower_wick >= 2:
            score += 4

        # ======================================================
        # VOLUME SCORE
        # ======================================================

        if vol_ratio >= 5:
            score += 10

        elif vol_ratio >= 3:
            score += 7

        elif vol_ratio >= 2:
            score += 5

        elif vol_ratio >= 1.2:
            score += 2

        # ======================================================
        # LIQUIDITY SCORE
        # ======================================================

        if traded_value >= 100_000_000_000:
            score += 6

        elif traded_value >= 50_000_000_000:
            score += 4

        elif traded_value >= 20_000_000_000:
            score += 2

        # ======================================================
        # VOLATILITY SCORE
        # ======================================================

        # volatility sehat
        if 10 <= atr_pct <= 20:
            score += 5

        elif 8 <= atr_pct < 10:
            score += 3

        # terlalu liar jangan terlalu dibonusin
        elif atr_pct > 20:
            score += 2

        # ======================================================
        # MOMENTUM BONUS
        # ======================================================

        if 1 <= return_pct <= 5:
            score += 5

        elif 0 <= return_pct < 1:
            score += 2

        # ======================================================
        # HEALTHY CANDLE BONUS
        # ======================================================

        if body_pct >= 2:
            score += 3

        if close_near_high <= 1:
            score += 3

        # ======================================================
        # PENALTY
        # ======================================================

        # ======================================================
        # TOO EXTENDED
        # ======================================================

        if distance_ma20 >= 12:
            score -= 15

        elif distance_ma20 >= 10:
            score -= 10

        elif distance_ma20 >= 8:
            score -= 5

        # ======================================================
        # WEAK VOLUME
        # ======================================================

        if vol_ratio < 0.8:
            score -= 8

        elif vol_ratio < 1:
            score -= 5

        # ======================================================
        # UPPER WICK
        # ======================================================

        if upper_wick >= 7:
            score -= 12

        elif upper_wick >= 5:
            score -= 8

        elif upper_wick >= 3:
            score -= 4

        # ======================================================
        # SMALL BODY
        # ======================================================

        if body_pct < 0.3:
            score -= 8

        elif body_pct < 0.5:
            score -= 5

        # ======================================================
        # LOW LIQUIDITY
        # ======================================================

        if traded_value < 3_000_000_000:
            score -= 15

        elif traded_value < 5_000_000_000:
            score -= 10

        elif traded_value < 10_000_000_000:
            score -= 5

        # ======================================================
        # LOW VOLATILITY
        # ======================================================

        if atr_pct < 4:
            score -= 18

        elif atr_pct < 5:
            score -= 15

        elif atr_pct < 8:
            score -= 8

        # ======================================================
        # TREND STABILITY
        # ======================================================

        if trend_stability >= 25:
            score -= 20

        elif trend_stability >= 20:
            score -= 12

        elif trend_stability >= 15:
            score -= 6

        # ======================================================
        # TOO CLOSE TO RESISTANCE
        # ======================================================

        distance_high_10 = (
            (recent_high_10 - last_close)
            / max(last_close, 1)
        ) * 100

        if distance_high_10 <= 1:
            score -= 10

        elif distance_high_10 <= 2:
            score -= 5

        # ======================================================
        # WEAK REBOUND STRUCTURE
        # ======================================================

        if lower_wick < 1 and return_pct <= 0:
            score -= 5

        # ======================================================
        # SIDEWAYS / DEAD STOCK
        # ======================================================

        if abs(return_pct) < 0.3 and atr_pct < 6:
            score -= 8

        # ======================================================
        # NORMALIZE
        # ======================================================

        score = int(
            max(
                0,
                min(score, 99)
            )
        )

        # ======================================================
        # STATUS
        # ======================================================

        if score >= 88:

            status = "🔥 Elite Rebound"

        elif score >= 80:

            status = "🚀 Strong Pullback"

        elif score >= 72:

            status = "⚡ Healthy Setup"

        elif score >= 64:

            status = "👀 Watchlist"

        else:

            status = "❌ Weak Setup"

        # ======================================================
        # TREND TYPE
        # ======================================================

        if distance_ma20 <= 3:

            trend = "Support"

        elif distance_ma20 <= 7:

            trend = "Healthy"

        else:

            trend = "Extended"

        # ======================================================
        # ENTRY
        # ======================================================

        entry_low = round_down(
            min(last_close, ma5_last)
        )

        entry_high = round_up(
            ma20_last * 1.03
        )

        # ======================================================
        # TAKE PROFIT
        # ======================================================

        tp1 = round_up(
            last_close * 1.05
        )

        tp2 = round_up(
            last_close * 1.10
        )

        tp3 = round_up(
            recent_high_10
        )

        # ======================================================
        # STOP LOSS
        # ======================================================

        sl = round_down(
            recent_low_10 * 0.97
        )

        # ======================================================
        # RISK REWARD
        # ======================================================

        risk = max(last_close - sl, 1)

        reward = max(tp2 - last_close, 1)

        rr = round(
            reward / risk,
            2
        )

        # ======================================================
        # DISPLAY
        # ======================================================

        if vol_last >= 1_000_000_000:

            volume_display = (
                f"{round(vol_last / 1_000_000_000, 2)}B"
            )

        elif vol_last >= 1_000_000:

            volume_display = (
                f"{round(vol_last / 1_000_000, 2)}M"
            )

        else:

            volume_display = (
                f"{round(vol_last / 1000, 0)}K"
            )

        traded_value_display = (
            f"{round(traded_value / 1_000_000_000, 2)}B"
        )

        # ======================================================
        # DEBUG
        # ======================================================

        print("\n" + "=" * 80)

        print(f"📈 {kode}")

        print("-" * 80)

        print(
            f"Harga         : {round_down(last_close)} "
            f"({round(return_pct,2)}%)"
        )

        print(
            f"Volume        : {volume_display} "
            f"(x{round(vol_ratio,2)})"
        )

        print(
            f"Liquidity     : {traded_value_display}"
        )

        print(
            f"ATR           : {round(atr_pct,2)}%"
        )

        print(
            f"Status        : {status}"
        )

        print(
            f"Trend         : {trend}"
        )

        print(
            f"Pullback      : {round(pullback_pct,2)}%"
        )

        print(
            f"Distance MA20 : {round(distance_ma20,2)}%"
        )

        print(
            f"Distance MA50 : {round(distance_ma50,2)}%"
        )

        print(
            f"Lower Wick    : {round(lower_wick,2)}%"
        )

        print(
            f"Upper Wick    : {round(upper_wick,2)}%"
        )

        print("-" * 80)

        print(
            f"Entry         : {entry_low} - {entry_high}"
        )

        print(
            f"TP            : {tp1} / {tp2} / {tp3}"
        )

        print(
            f"SL            : {sl}"
        )

        print(
            f"RR            : {rr}"
        )

        print("-" * 80)

        print(
            f"🔥 FINAL SCORE : {score}/100"
        )

        print("=" * 80)

        # ======================================================
        # RESULT
        # ======================================================

        return StockResult(

            kode=kode,

            last_price=round_down(last_close),

            score=score,

            setup=status,

            trend=trend,

            entry_low=entry_low,

            entry_high=entry_high,

            tp=[tp1, tp2, tp3],

            sl=sl,

            rr=rr,

            recommendation=status,

            screener_type=self.screener_type,

            score_breakdown={

                "Volume": volume_display,

                "Volume Ratio": round(vol_ratio, 2),

                "Liquidity": traded_value_display,

                "ATR %": round(atr_pct, 2),

                "Return %": round(return_pct, 2),

                "Pullback %": round(pullback_pct, 2),

                "Distance MA20": round(distance_ma20, 2),

                "Distance MA50": round(distance_ma50, 2),

                "Distance MA100": round(distance_ma100, 2),

                "Lower Wick": round(lower_wick, 2),

                "Upper Wick": round(upper_wick, 2),

                "Close Near High": round(close_near_high, 2),

                "Body %": round(body_pct, 2),

                "RR": rr
            }
        )

# ======================================================
# 📊 SWING TRADE SCORE ONLY
# ======================================================

def calculate_swing_trade_score(df):

    try:

        if df is None or len(df) < 100:
            return 0

        df = df.copy()

        df.columns = [
            str(c).strip().lower()
            for c in df.columns
        ]

        close = df["close"]

        high = df["high"]

        low = df["low"]

        volume = df["volume"]

        idx = get_last_valid_idx(volume)

        last_close = float(close.iloc[idx])

        prev_close = float(close.iloc[idx - 1])

        # ======================================================
        # MOVING AVERAGE
        # ======================================================

        ma20 = close.rolling(20).mean()

        ma50 = close.rolling(50).mean()

        ma100 = close.rolling(100).mean()

        ma20_last = float(ma20.iloc[idx])

        ma50_last = float(ma50.iloc[idx])

        ma100_last = float(ma100.iloc[idx])

        # ======================================================
        # VOLUME
        # ======================================================

        vol_ma20 = volume.rolling(20).mean()

        vol_ratio = (
            volume.iloc[idx]
            / max(vol_ma20.iloc[idx], 1)
        )

        traded_value = (
            last_close * volume.iloc[idx]
        )

        # ======================================================
        # PRICE ACTION
        # ======================================================

        distance_ma20 = (
            (last_close - ma20_last)
            / max(ma20_last, 1)
        ) * 100

        recent_high_5 = float(
            high.tail(5).max()
        )

        pullback_pct = (
            (last_close - recent_high_5)
            / max(recent_high_5, 1)
        ) * 100

        # ======================================================
        # VOLATILITY
        # ======================================================

        atr_pct = (
            (high.tail(14).max() - low.tail(14).min())
            / max(last_close, 1)
        ) * 100

        # ======================================================
        # RETURN %
        # ======================================================

        return_pct = (
            (last_close - prev_close)
            / max(prev_close, 1)
        ) * 100

        # ======================================================
        # TREND STABILITY
        # ======================================================

        trend_stability = (
            close.tail(20).std()
            / max(close.tail(20).mean(), 1)
        ) * 100

        # ======================================================
        # TREND
        # ======================================================

        bullish_alignment = (

            ma20_last > ma50_last and
            ma50_last > ma100_last

        )

        # ======================================================
        # SCORE
        # ======================================================

        score = 45

        # trend
        if bullish_alignment:
            score += 10

        if last_close > ma20_last:
            score += 5

        # pullback sehat
        if abs(distance_ma20) <= 3:
            score += 8

        if -12 <= pullback_pct <= -2:
            score += 10

        # volume
        if vol_ratio >= 5:
            score += 10

        elif vol_ratio >= 3:
            score += 7

        elif vol_ratio >= 2:
            score += 5

        # liquidity
        if traded_value >= 100_000_000_000:
            score += 10

        elif traded_value >= 50_000_000_000:
            score += 7

        elif traded_value >= 20_000_000_000:
            score += 4

        # ======================================================
        # VOLATILITY SCORE
        # ======================================================

        # volatility sehat
        if 12 <= atr_pct <= 20:
            score += 4

        elif 8 <= atr_pct < 12:
            score += 2

        # terlalu liar jangan terlalu dibonusin
        elif atr_pct > 20:
            score += 1

        # ======================================================
        # PENALTY
        # ======================================================

        # terlalu extended dari MA20
        if distance_ma20 >= 12:
            score -= 15

        elif distance_ma20 >= 10:
            score -= 10

        elif distance_ma20 >= 8:
            score -= 5

        # volatility terlalu kecil
        if atr_pct < 4:
            score -= 18

        elif atr_pct < 5:
            score -= 15

        elif atr_pct < 8:
            score -= 8

        # trend terlalu liar
        if trend_stability >= 25:
            score -= 20

        elif trend_stability >= 20:
            score -= 12

        elif trend_stability >= 15:
            score -= 6

        # saham terlalu sideways
        if abs(return_pct) < 0.3 and atr_pct < 6:
            score -= 8

        score = int(
            max(
                0,
                min(score, 99)
            )
        )

        return score

    except Exception as e:

        print(f"SWING SCORE ERROR: {e}")

        return 0