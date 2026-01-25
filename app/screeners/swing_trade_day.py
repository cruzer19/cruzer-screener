from app.screeners.base import BaseScreener
from app.models.stock_result import StockResult
from app.core.data_loader import load_daily_data
from app.core.indicators import ema, rsi
from app.utils.helpers import round_down, round_up


class SwingTradeDayScreener(BaseScreener):
    """
    Swing Trade Day — Beli Pagi, Jual Sore (IDX Version)
    Fokus: momentum intraday TANPA chasing
    """
    screener_type = "swing_3d"

    def analyze(self, kode: str):
        df = load_daily_data(kode)

        if df is None or len(df) < 25:
            return None

        close = df["Close"]
        low = df["Low"]
        volume = df["Volume"]

        # ======================================================
        # INDICATORS
        # ======================================================
        ema20 = ema(close, 20)
        rsi14 = rsi(close, 14)
        vol_ma20 = volume.rolling(20).mean()

        # ======================================================
        # LAST VALUES
        # ======================================================
        last_close = float(close.iloc[-1])
        last_low = float(low.iloc[-1])

        ema20_last = float(ema20.iloc[-1])
        ema20_prev = float(ema20.iloc[-2])

        rsi_last = float(rsi14.iloc[-1])

        vol_last = float(volume.iloc[-1])
        vol_prev = float(volume.iloc[-2])
        vol_ma_last = float(vol_ma20.iloc[-1])

        score = 0
        score_breakdown = {}

        # ======================================================
        # 🟢 TREND (40) — + EMA DISTANCE GUARD
        # ======================================================
        ema_distance = (last_close - ema20_last) / ema20_last * 100

        if (
            last_close >= ema20_last
            and ema20_last >= ema20_prev
            and ema_distance <= 5    # 🔥 ANTI CHASING
        ):
            score += 40
            score_breakdown["Trend"] = 40
        else:
            score_breakdown["Trend"] = 0

        # ======================================================
        # 🟢 RSI (30) — MOMENTUM SEHAT
        # ======================================================
        if 55 <= rsi_last <= 75:
            score += 30
            score_breakdown["RSI"] = 30
        elif 50 <= rsi_last < 55:
            score += 20
            score_breakdown["RSI"] = 20
        elif 75 < rsi_last <= 80:
            score += 15
            score_breakdown["RSI"] = 15   # 🔥 extension masih boleh
        else:
            score_breakdown["RSI"] = 0
        # ======================================================
        # 🟢 VOLUME (30) — HARUS NAIK & ADA ACCELERATION
        # ======================================================
        if vol_last >= vol_ma_last and vol_last >= vol_prev:
            score += 30
            score_breakdown["Volume"] = 30
        elif vol_last >= vol_ma_last * 0.7:
            score += 20
            score_breakdown["Volume"] = 20
        else:
            score_breakdown["Volume"] = 0

        # ======================================================
        # 🔒 FINAL FILTER (INTRADAY FRIENDLY)
        # ======================================================
        if score < 45:
            return None

        # ======================================================
        # 🔥 IDX TICK ROUNDING (VALID ORDERBOOK)
        # ======================================================

        # === LAST PRICE ===
        last_price = round_down(last_close)

        # === ENTRY ZONE (LEBIH PRESISI UNTUK DAY TRADE) ===
        raw_entry_low = last_close * 0.997
        raw_entry_high = last_close * 1.003

        entry_low = round_down(raw_entry_low)
        entry_high = round_up(raw_entry_high)

        # === TARGET INTRADAY (REALISTIS) ===
        tp1 = round_up(last_close * 1.01)
        tp2 = round_up(last_close * 1.02)
        tp3 = round_up(last_close * 1.03)

        # === STOP LOSS KETAT ===
        raw_sl = last_low * 0.99
        sl = round_down(raw_sl)

        # === RR (PAKAI HARGA VALID) ===
        rr = round((tp2 - last_price) / max(last_price - sl, 1) * 100, 1)

        return StockResult(
            kode=kode,
            last_price=last_price,
            score=int(score),
            setup="Swing Trade Day",
            trend="Intraday Uptrend",
            entry_low=entry_low,
            entry_high=entry_high,
            tp=[tp1, tp2, tp3],
            sl=sl,
            rr=rr,
            recommendation="Buy on Intraday Strength",
            screener_type=self.screener_type,
            score_breakdown=score_breakdown
        )