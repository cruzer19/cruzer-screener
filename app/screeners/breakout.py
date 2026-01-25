from app.screeners.base import BaseScreener
from app.models.stock_result import StockResult
from app.core.data_loader import load_daily_data
from app.core.indicators import ema, rsi
from app.utils.helpers import round_down, round_up


class BreakoutScreener(BaseScreener):
    """
    Breakout — Beli Sore, Jual Pagi (Relaxed IDX Version)
    Mode A: Anticipative Breakout (High Quality, Jarang)
    """
    screener_type = "breakout"

    def analyze(self, kode: str):
        df = load_daily_data(kode)

        if df is None or len(df) < 25:
            return None

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        # === INDICATORS ===
        ema20 = ema(close, 20)
        rsi14 = rsi(close, 14)
        vol_ma20 = volume.rolling(20).mean()

        # === LAST VALUES ===
        last_close = float(close.iloc[-1])
        last_low = float(low.iloc[-1])

        ema20_last = float(ema20.iloc[-1])
        ema20_prev = float(ema20.iloc[-2])

        rsi_last = float(rsi14.iloc[-1])

        vol_last = float(volume.iloc[-1])
        vol_prev = float(volume.iloc[-2])
        vol_ma_last = float(vol_ma20.iloc[-1])

        # === RESISTANCE (10 HARI, TANPA HARI INI) ===
        resistance = float(high.iloc[-11:-1].max())

        score = 0
        score_breakdown = {}

        # ======================================================
        # 🔥 1️⃣ BREAKOUT / NEAR BREAKOUT (40)
        # + EMA DISTANCE PROTECTION
        # ======================================================
        ema_distance = (last_close - ema20_last) / ema20_last * 100

        if last_close >= resistance * 0.998 and ema_distance <= 4:
            score += 40
            score_breakdown["Breakout"] = 40
        elif last_close >= resistance * 0.985 and ema_distance <= 3:
            score += 25
            score_breakdown["Breakout"] = 25
        else:
            score_breakdown["Breakout"] = 0

        # ======================================================
        # 🔹 TREND (20)
        # ======================================================
        if ema20_last >= ema20_prev:
            score += 20
            score_breakdown["Trend"] = 20
        else:
            score_breakdown["Trend"] = 0

        # ======================================================
        # 🔥 2️⃣ VOLUME (25) — HARUS NAIK & ADA ACCELERATION
        # ======================================================
        if vol_last > vol_ma_last and vol_last > vol_prev:
            score += 25
            score_breakdown["Volume"] = 25
        elif vol_last > vol_ma_last * 0.8:
            score += 15
            score_breakdown["Volume"] = 15
        else:
            score_breakdown["Volume"] = 0

        # ======================================================
        # 🔹 RSI (15)
        # ======================================================
        if rsi_last >= 55:
            score += 15
            score_breakdown["RSI"] = 15
        elif rsi_last >= 50:
            score += 8
            score_breakdown["RSI"] = 8
        else:
            score_breakdown["RSI"] = 0

        # ======================================================
        # 🔒 FINAL FILTER (MODE A — KETAT)
        # ======================================================
        if rsi_last >= 70:
            return None

        if score < 60:
            return None

        # ======================================================
        # 🔥 3️⃣ IDX TICK ROUNDING (VALID PRICE)
        # + ENTRY ZONE DIPERSEMPIT
        # ======================================================

        # === LAST PRICE ===
        last_price = round_down(last_close)

        # === ENTRY ZONE (LEBIH PRESISI UNTUK BSJP) ===
        raw_entry_low = last_close * 0.997
        raw_entry_high = last_close * 1.005

        entry_low = round_down(raw_entry_low)
        entry_high = round_up(raw_entry_high)

        # === TARGET (FAST MOVE) ===
        tp1 = round_up(last_close * 1.02)
        tp2 = round_up(last_close * 1.04)
        tp3 = round_up(last_close * 1.06)

        # === STOP LOSS (DI BAWAH BASE / LOW) ===
        raw_sl = min(resistance, last_low) * 0.985
        sl = round_down(raw_sl)

        # === RR (REAL PRICE) ===
        rr = round((tp2 - last_price) / max(last_price - sl, 1) * 100, 1)

        return StockResult(
            kode=kode,
            last_price=last_price,
            score=int(score),
            setup="Breakout (Beli Sore)",
            trend="Bullish / Near Breakout",
            entry_low=entry_low,
            entry_high=entry_high,
            tp=[tp1, tp2, tp3],
            sl=sl,
            rr=rr,
            recommendation="Buy Breakout / Anticipate",
            screener_type=self.screener_type,
            score_breakdown=score_breakdown
        )