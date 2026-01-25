from app.screeners.base import BaseScreener
from app.models.stock_result import StockResult
from app.core.data_loader import load_daily_data
from app.core.indicators import ema, rsi
from app.utils.helpers import round_down, round_up


class SwingTradeWeekScreener(BaseScreener):
    screener_type = "Swing Trade (Week)"

    def analyze(self, kode: str):
        # === LOAD DATA ===
        df = load_daily_data(kode)

        # safety check
        if df is None or df.empty or len(df) < 60:
            return None

        close = df["Close"]
        volume = df["Volume"]

        # === INDICATORS ===
        ema20 = ema(close, 20)
        ema50 = ema(close, 50)
        rsi14 = rsi(close, 14)
        vol_ma20 = volume.rolling(20).mean()

        # ambil nilai TERAKHIR (scalar, bukan Series)
        last_close = float(close.iloc[-1])
        last_ema20 = float(ema20.iloc[-1])
        last_ema50 = float(ema50.iloc[-1])
        last_rsi = float(rsi14.iloc[-1])
        last_volume = float(volume.iloc[-1])
        last_vol_ma20 = float(vol_ma20.iloc[-1])

        score = 0
        breakdown = {
        "Trend": 0,
        "RSI": 0,
        "Volume": 0
        }

        # ==================================================
        # TREND (MAX 40)
        # ==================================================
        if last_ema20 > last_ema50:
            score += 20
            breakdown["Trend"] += 20

        if last_close > last_ema20:
            score += 20
            breakdown["Trend"] += 20

        # ==================================================
        # RSI / MOMENTUM (MAX 30)
        # ==================================================
        if 55 <= last_rsi <= 70:
            score += 30
            breakdown["RSI"] += 30
        elif 50 <= last_rsi < 55:
            score += 15
            breakdown["RSI"] += 15
        elif 70 < last_rsi <= 75:
            score += 10
            breakdown["RSI"] += 10

        # ==================================================
        # VOLUME CONFIRMATION (MAX 20)
        # ==================================================
        if last_volume > last_vol_ma20:
            score += 20
            breakdown["Volume"] += 20

        # ==================================================
        # EARLY EXIT
        # ==================================================
        if score < 60:
            return None

        # ==================================================
        # ENTRY / TP / SL (REALISTIC SWING)
        # ==================================================
        entry_low = round_down(last_ema20 * 0.98)
        entry_high = round_up(last_ema20 * 1.02)


        tp1 = round_up(last_close * 1.04)
        tp2 = round_up(last_close * 1.08)
        tp3 = round_up(last_close * 1.12)

        sl = round_down(last_ema50 * 0.98)


        # RR calculation (aman dari zero division)
        risk = last_close - sl
        reward = tp2 - last_close
        rr = round((reward / risk) * 100, 1) if risk > 0 else 0.0

        return StockResult(
            kode=kode,
            last_price=int(last_close),
            score=score,
            setup="Swing Setup (1–2 Weeks)",
            trend="Bullish (EMA20 > EMA50)",
            entry_low=entry_low,
            entry_high=entry_high,
            tp=[tp1, tp2, tp3],
            sl=sl,
            rr=rr,
            recommendation="Buy on Pullback / Hold",
            screener_type=self.screener_type,
            score_breakdown=breakdown
        )