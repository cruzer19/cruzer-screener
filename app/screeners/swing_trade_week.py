from app.screeners.base import BaseScreener
from app.models.stock_result import StockResult
from app.core.data_loader import load_daily_data
from app.core.indicators import ema
from app.utils.helpers import round_down, round_up

import pandas as pd


# ==========================================================
# 🔥 RSI TRADINGVIEW
# ==========================================================
def rsi_tradingview(series, period=14):

    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    avg_gain = avg_gain.combine_first(
        gain.ewm(alpha=1/period, adjust=False).mean()
    )
    avg_loss = avg_loss.combine_first(
        loss.ewm(alpha=1/period, adjust=False).mean()
    )

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ==========================================================
# 🔥 RSI SCORE
# ==========================================================
def get_rsi_score(rsi):

    if rsi <= 20:
        return 3
    elif rsi <= 30:
        return 4
    elif rsi <= 45:
        return 5
    elif rsi <= 60:
        return 4
    elif rsi <= 70:
        return 3
    else:
        return 2


# ==========================================================
# 🔥 BANDAR ACCUMULATION DETECTOR
# ==========================================================
def get_accumulation_score(df):

    volume = df["Volume"]
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    vol_ma5 = volume.rolling(5).mean()
    vol_ma20 = volume.rolling(20).mean()

    spread = high - low
    avg_range = spread.rolling(10).mean()

    last_vol = volume.iloc[-1]
    last_vol5 = vol_ma5.iloc[-1]
    last_vol20 = vol_ma20.iloc[-1]

    last_spread = spread.iloc[-1]
    last_avg_range = avg_range.iloc[-1]

    last_close = close.iloc[-1]
    last_low = low.iloc[-1]
    last_high = high.iloc[-1]

    score = 0

    # ================= VOLUME ACCUMULATION =================
    if last_vol5 > last_vol20:
        score += 10

    # ================= CLOSE NEAR HIGH =================
    if last_high - last_low > 0:
        close_pos = (last_close - last_low) / (last_high - last_low)

        if close_pos > 0.6:
            score += 8

    # ================= VOLATILITY CONTRACTION =================
    if last_spread < last_avg_range:
        score += 6

    # ================= CONSISTENT VOLUME =================
    recent_vol = volume.tail(5).mean()

    if recent_vol > vol_ma20.iloc[-1]:
        score += 6

    return score


# ==========================================================
# 🔥 MAIN SCREENER
# ==========================================================
class SwingTradeWeekScreener(BaseScreener):

    screener_type = "Swing Trade (Week)"

    def analyze(self, kode: str):

        # ================= LOAD DATA =================
        df_daily = load_daily_data(kode)

        if df_daily is None or df_daily.empty:
            return None

        df_daily = df_daily.copy()
        df_daily.index = pd.to_datetime(df_daily.index)
        df_daily = df_daily.sort_index()

        df_daily = df_daily[~df_daily.index.duplicated(keep="last")]
        df_daily = df_daily.dropna()

        df_daily = df_daily[df_daily["Close"] > 0]

        if len(df_daily) < 50:
            return None

        # ==================================================
        # 🔥 BANDAR ACCUMULATION (DAILY BASE)
        # ==================================================
        accumulation_score = get_accumulation_score(df_daily)

        # ================= WEEKLY =================
        df_weekly = df_daily.resample("W-FRI").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum"
        }).dropna()

        if df_weekly.empty or len(df_weekly) < 15:
            return None

        # ==================================================
        # 🔥 RSI DAILY
        # ==================================================
        if "Adj Close" in df_daily.columns:
            close_daily = df_daily["Adj Close"]
        else:
            close_daily = df_daily["Close"]

        rsi_daily = rsi_tradingview(close_daily, 14)

        last_rsi = (
            float(rsi_daily.iloc[-1])
            if not pd.isna(rsi_daily.iloc[-1])
            else 50
        )

        # ==================================================
        # 🔥 WEEKLY TREND
        # ==================================================
        close = df_weekly["Close"]
        volume = df_weekly["Volume"]

        ema20 = ema(close, 20)
        ema50 = ema(close, 50)

        vol_ma10 = volume.rolling(10).mean()

        # ==================================================
        # 🔥 BAND ACCUMULATION DETECTOR
        # ==================================================
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()

        bb_upper = bb_mid + (bb_std * 2)
        bb_lower = bb_mid - (bb_std * 2)

        bandwidth = (bb_upper - bb_lower) / bb_mid

        last_bandwidth = (
            float(bandwidth.iloc[-1])
            if not pd.isna(bandwidth.iloc[-1])
            else 1
        )

        band_accumulation = 1 if last_bandwidth < 0.12 else 0

        last_close = float(close.iloc[-1])

        last_ema20 = float(ema20.iloc[-1]) if not pd.isna(ema20.iloc[-1]) else last_close
        last_ema50 = float(ema50.iloc[-1]) if not pd.isna(ema50.iloc[-1]) else last_close

        last_volume = float(volume.iloc[-1])
        last_vol_ma = float(vol_ma10.iloc[-1]) if not pd.isna(vol_ma10.iloc[-1]) else last_volume

        # ==================================================
        # 🔥 RSI WEEKLY
        # ==================================================
        rsi_weekly = rsi_tradingview(close, 14)

        last_rsi_weekly = (
            float(rsi_weekly.iloc[-1])
            if not pd.isna(rsi_weekly.iloc[-1])
            else 50
        )

        # ==================================================
        # ❌ OVERBOUGHT FILTER
        # ==================================================
        distance_from_ema = (last_close - last_ema20) / last_ema20 * 100

        if last_rsi_weekly >= 70 or distance_from_ema > 10:
            return None

        # ==================================================
        # 🔥 SCORING
        # ==================================================
        score = 0

        breakdown = {
            "Trend": 0,
            "RSI": 0,
            "Volume": 0,
            "Accumulation": accumulation_score
        }

        # ===== TREND =====
        if last_ema20 > last_ema50:
            score += 20
            breakdown["Trend"] += 20

        if last_close > last_ema20:
            score += 20
            breakdown["Trend"] += 20

        # ===== RSI STATUS =====
        if last_rsi <= 30:
            rsi_status = "🟢 Oversold"
        elif last_rsi >= 70:
            rsi_status = "🔴 Overbought"
        else:
            rsi_status = "⚪ Normal"

        # ===== RSI SCORE =====
        if last_rsi <= 20:
            score += 25
            breakdown["RSI"] += 25

        elif last_rsi <= 30:
            score += 15
            breakdown["RSI"] += 15

        elif 30 < last_rsi <= 45:
            score += 5
            breakdown["RSI"] += 5

        elif 55 <= last_rsi <= 70:
            score += 20
            breakdown["RSI"] += 20

        # ===== VOLUME =====
        if last_volume > last_vol_ma:
            score += 20
            breakdown["Volume"] += 20

        # ==================================================
        # 🔥 FINAL RANK (ACCUMULATION MASUK)
        # ==================================================
        rsi_score = get_rsi_score(last_rsi)

        rank = (
            rsi_score * 10 +
            breakdown["Trend"] * 0.5 +
            breakdown["Volume"] * 0.5 +
            accumulation_score * 1.2 +
            score * 0.3
        )

        # ================= ENTRY =================
        entry_low = round_down(last_ema20 * 0.97)
        entry_high = round_up(last_ema20 * 1.03)

        tp1 = round_up(last_close * 1.04)
        tp2 = round_up(last_close * 1.08)

        sl = round_down(last_ema50 * 0.97)

        # ================= RR =================
        risk = last_close - sl
        reward = tp2 - last_close

        rr = round((reward / risk) * 100, 1) if risk > 0 else 0

        # ================= RETURN =================
        return StockResult(

            kode=kode,
            last_price=int(last_close),

            score=int(score),
            rank=round(rank, 2),

            setup="Swing Weekly",
            trend="Bullish" if last_ema20 > last_ema50 else "Bearish",

            entry_low=int(entry_low),
            entry_high=int(entry_high),

            tp=[int(tp1), int(tp2)],
            sl=int(sl),

            rr=float(rr),

            recommendation="Wait / Buy Pullback",
            screener_type=self.screener_type,

            score_breakdown=breakdown,

            rsi_value=round(last_rsi, 2),
            rsi_status=rsi_status
        )