import pandas as pd

from app.screeners.base import BaseScreener
from app.models.stock_result import StockResult
from app.core.data_loader import load_daily_data
from app.utils.helpers import round_down, round_up


# ==========================================================
# 🟢 ACCUMULATION SCORE
# ==========================================================
def get_accumulation_score(df):

    volume = df["Volume"]
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    vol_ma5 = volume.rolling(5).mean()
    vol_ma10 = volume.rolling(10).mean()
    vol_ma20 = volume.rolling(20).mean()

    spread = (high - low).replace(0, 1)
    avg_range = spread.rolling(10).mean()

    score = 0

    # Volume acceleration (lebih smooth)
    if vol_ma5.iloc[-1] > vol_ma20.iloc[-1] * 1.3:
        score += 20

    if vol_ma10.iloc[-1] > vol_ma20.iloc[-1] * 1.2:
        score += 15

    # Close position (buyer dominance)
    close_pos = (close.iloc[-1] - low.iloc[-1]) / spread.iloc[-1]
    if close_pos > 0.7:
        score += 20

    # Volatility contraction
    if spread.iloc[-1] < avg_range.iloc[-1] * 0.8:
        score += 20

    # Volume consistency (bukan spike doang)
    if volume.tail(5).mean() > vol_ma20.iloc[-1] * 1.2:
        score += 15

    # Higher low (structure)
    if low.iloc[-1] > low.iloc[-3]:
        score += 10

    # 🔥 slow accumulation (big cap friendly)
    if vol_ma5.iloc[-1] > vol_ma20.iloc[-1] * 1.05:
        score += 10

    if close.iloc[-1] > close.iloc[-5]:
        score += 10

    return score


# ==========================================================
# 📈 UPTREND SCORE (REPLACEMENT MOMENTUM 🔥)
# ==========================================================
def get_uptrend_score(df):

    close = df["Close"]

    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()

    # 🔥 slope (WAJIB ADA SEBELUM DIPAKAI)
    if len(ma20) < 6:
        return 0

    ma20_slope = ma20.iloc[-1] - ma20.iloc[-5]

    score = 0

    # MA alignment
    if ma5.iloc[-1] > ma20.iloc[-1]:
        score += 30

    # price above MA20
    if close.iloc[-1] > ma20.iloc[-1]:
        score += 25

    # higher close
    if close.iloc[-1] > close.iloc[-3]:
        score += 25

    # 🔥 slope trend (INI YANG TADI ERROR)
    if ma20_slope > 0:
        score += 20

    return score

# ==========================================================
# 📍 TREND POSITION (EARLY / MID / LATE)
# ==========================================================
def get_trend_position(df):

    close = df["Close"]
    ma20 = close.rolling(20).mean()

    distance = (close.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1]

    if distance < 0.08:
        return "🟢 Early"
    elif distance < 0.15:
        return "🟡 Mid"
    else:
        return "🔴 Late"


# ==========================================================
# 📉 STRUCTURE
# ==========================================================
def get_structure(df):

    close = df["Close"]
    low = df["Low"]

    support = low.tail(30).min()
    last_close = close.iloc[-1]

    distance = abs(last_close - support) / support

    return distance, support

# ==========================================================
# ⚡ PRICE MOVEMENT FILTER (ANTI SAHAM LEMOT)
# ==========================================================
def is_active_stock(df):

    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    # 🔥 range harian
    spread = (high - low).replace(0, 1)

    # 🔥 ATR sederhana
    avg_range = spread.rolling(10).mean()

    last_range = spread.iloc[-1]
    last_price = close.iloc[-1]

    # 🔥 persentase gerakan
    move_pct = last_range / last_price

    # ================= RULE =================
    # minimal gerakan 1.5% - 2%
    return move_pct >= 0.007


# ==========================================================
# 🔥 MAIN SCREENER (UPTREND VERSION)
# ==========================================================
class SwingTradeWeekScreener(BaseScreener):

    screener_type = "Swing Trade (Week) v8 - Acc + Trend"

    def analyze(self, kode: str):

        df = load_daily_data(kode)

        if df is None or df.empty or len(df) < 50:
            return None

        df = df.copy()
        df.columns = [c.capitalize() for c in df.columns]

        if "Close" not in df.columns:
            return None

        df = df.sort_index().dropna()
        df = df[df["Close"] > 0]

        if not is_active_stock(df):
            return None

        # ================= LIQUIDITY =================
        avg_vol = df["Volume"].tail(20).mean()
        if avg_vol < 500_000:
            return None

        last_close = float(df["Close"].iloc[-1])

        # ================= SCORES =================
        acc_score = get_accumulation_score(df)
        trend_score = get_uptrend_score(df)
        distance, support = get_structure(df)
        trend_position = get_trend_position(df)

        # ================= TREND STRENGTH FILTER =================
        close = df["Close"]

        if close.iloc[-1] < close.iloc[-3] * 0.995:
            return None

        # ================= DISTANCE FILTER =================
        if distance > 0.16:
            return None

        # ================= LEADER FILTER =================
        price_change_5d = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5]

        if price_change_5d < 0.01:
            return None

        # ================= CLASSIFICATION =================

        # 🔥 ACC + UPTREND (BEST)
        if acc_score >= 75 and trend_score >= 60:

            setup = "🔥 Accumulation + Uptrend"

            pullback_zone = df["Close"].tail(5).min()

            entry_low = round_down(pullback_zone)
            entry_high = round_up(last_close * 1.02)

            sl = round_down(support * 0.97)

            tp1 = round_up(last_close * 1.08)
            tp2 = round_up(last_close * 1.15)

            main_score = acc_score * 0.6 + trend_score * 0.4

        # 🟢 SMART ACCUMULATION
        elif acc_score >= 60 and trend_score < 70 and distance <= 0.10:

            setup = "🟢 Smart Accumulation"

            entry_low = round_down(support * 0.98)
            entry_high = round_up(support * 1.04)

            sl = round_down(support * 0.95)

            tp1 = round_up(last_close * 1.05)
            tp2 = round_up(last_close * 1.10)

            main_score = acc_score * 0.8 + trend_score * 0.2

        else:
            return None

        # ================= RR =================
        risk = last_close - sl
        reward = tp2 - last_close
        rr = (reward / risk) * 100 if risk > 0 else 0

        # ================= DEBUG =================
        print(
            kode,
            "| setup:", setup,
            "| acc:", acc_score,
            "| trend:", trend_score
        )

        # ================= NORMALIZE SCORE =================
        MAX_SCORE = 120  # asumsi max internal

        normalized_score = (main_score / MAX_SCORE) * 100

        # clamp biar gak lewat 100
        normalized_score = max(0, min(100, normalized_score))

        score = int(round(normalized_score / 5) * 5)

        # ================= RETURN =================
        return StockResult(
            kode=kode,
            last_price=int(last_close),

            score = score,
            rank=float(main_score),

            setup=setup,
            trend=trend_position,  # 🔥 INI BARU

            entry_low=int(entry_low),
            entry_high=int(entry_high),

            tp=[int(tp1), int(tp2)],
            sl=int(sl),

            rr=round(rr, 1),

            recommendation="Swing v8",
            screener_type=self.screener_type,

            score_breakdown={
                "Accumulation": acc_score,
                "Trend": trend_score
            }
        )