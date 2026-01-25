import numpy as np
import pandas as pd

def round_to_tick(price):
    price = int(round(price))

    if price < 200:
        tick = 1
    elif price < 500:
        tick = 2
    elif price < 2000:
        tick = 5
    elif price < 5000:
        tick = 10
    else:
        tick = 25

    return int(round(price / tick) * tick)

def analyze_single_stock(df):
    close = df["Close"]

    if hasattr(close, "columns"):
        close = close.iloc[:, 0]

    close = close.astype(float)

    # === MOVING AVERAGE (BIARKAN FLOAT) ===
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()

    ma20_last = float(ma20.iloc[-1])
    ma50_last = float(ma50.iloc[-1])

    # === PRICE (BULAT) ===
    support = round_to_tick(close.tail(30).min())
    resistance = round_to_tick(close.tail(30).max())
    last_price = round_to_tick(close.iloc[-1])

    price = last_price

    ma_gap_pct = abs(ma20_last - ma50_last) / ma50_last * 100

    if ma20_last > ma50_last and price > ma20_last:
        trend = "⬆️ Bullish (Strong)" if ma_gap_pct >= 2 else "⬆️ Bullish (Weak)"
    elif ma20_last < ma50_last and price < ma20_last:
        trend = "⬇️ Bearish (Strong)" if ma_gap_pct >= 2 else "⬇️ Bearish (Weak)"
    else:
        trend = "➡️ Sideways / Transition"

    entry_low = round_to_tick(support * 1.01)
    entry_high = round_to_tick(support * 1.03)

    risk_pct = round((last_price - support) / last_price * 100, 2)

    return {
        "trend": trend,
        "last_price": last_price,
        "support": support,
        "resistance": resistance,
        "entry_zone": (entry_low, entry_high),
        "risk_pct": risk_pct
    }
