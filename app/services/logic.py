import pandas as pd


# ================= PRICE ROUNDING =================
def round_price(price):

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


# ================= MARKET MOVERS FILTER =================
def detect_market_mover(df):

    """
    Filter saham yang sedang aktif seperti Top Gainer / Momentum
    """

    if df is None or len(df) < 30:
        return False

    close = df["CLOSE"]
    volume = df["VOLUME"]

    price = close.iloc[-1]
    prev = close.iloc[-2]

    change_pct = (price - prev) / prev * 100

    avg_vol = volume.iloc[-30:-10].mean()
    recent_vol = volume.iloc[-10:].mean()

    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1

    # Balanced rule (tidak terlalu ketat / tidak terlalu longgar)
    if change_pct > 3 and vol_ratio > 1.5:
        return True

    return False


# ================= EARLY BREAKOUT DETECTOR =================
def detect_early_breakout(df):

    """
    Detect compression near resistance before breakout
    """

    if df is None or len(df) < 20:
        return False

    close = df["CLOSE"]
    high = df["HIGH"]
    low = df["LOW"]
    volume = df["VOLUME"]

    price = close.iloc[-1]

    resistance = high.tail(15).max()

    # dekat resistance
    near_resistance = price >= resistance * 0.97

    # compression candle
    recent_range = (high - low).tail(3).mean()
    avg_range = (high - low).tail(15).mean()

    compression = recent_range < avg_range * 0.7

    # volume mulai naik
    avg_vol = volume.tail(20).mean()
    recent_vol = volume.tail(3).mean()

    vol_build = recent_vol > avg_vol * 1.2

    if near_resistance and compression and vol_build:
        return True

    return False


# ================= MAIN LOGIC =================
def detect_day_trade(df):

    if df is None or len(df) < 50:
        return None

    close = df["CLOSE"]
    high = df["HIGH"]
    low = df["LOW"]
    volume = df["VOLUME"]

    price = close.iloc[-1]

    # ================= LEVEL =================
    recent_high = high.tail(15).max()
    recent_low = low.tail(15).min()

    entry_high = round_price(recent_high * 1.01)
    entry_low = round_price(entry_high * 0.985)

    entry_ref = entry_high
    sl = round_price(max(recent_low, entry_ref * 0.95))

    # ================= MOVING AVERAGE =================
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1]

    # ================= VOLUME =================
    avg_vol = volume.iloc[-30:-10].mean()
    recent_vol = volume.iloc[-10:].mean()

    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1

    # ================= MOMENTUM =================
    momentum = (price - close.iloc[-5]) / close.iloc[-5] * 100
    up_count = (close.diff() > 0).tail(10).sum()

    # ================= EARLY BREAKOUT =================
    early_break = detect_early_breakout(df)

    # ================= ARB DETECTION =================
    prev_close = close.iloc[-2]
    lower_limit = prev_close * 0.93

    near_arb = price <= lower_limit * 1.03
    rebound = close.iloc[-1] > close.iloc[-2]
    vol_spike = vol_ratio > 2

    arb_signal = near_arb and rebound and vol_spike

    # ================= SCORE =================
    score = (
        min(vol_ratio * 35, 45) +
        up_count * 2 +
        max(0, momentum * 2)
    )

    # BOOSTS
    if price > ma20:
        score += 5

    if price > ma50:
        score += 5

    if momentum > 3:
        score += 5

    if early_break:
        score += 8

    if arb_signal:
        score += 10

    score = round(score, 1)

    # ================= STATUS =================
    if arb_signal:
        status = "🧲 Rebound ARB"

    elif price > recent_high * 1.003 and vol_ratio > 1.2:
        status = "🔥 Breakout"

    elif early_break:
        status = "🚀 Early Breakout"

    elif recent_high * 0.97 <= price < recent_high * 1.005:
        status = "⚡ Pre-Breakout"

    elif (
        price > ma20 and
        momentum > 1 and
        vol_ratio > 1.2
    ):
        status = "📈 Strong Trend"

    else:
        status = "⚠️ Mid"

    return {
        "price": round_price(price),
        "entry_low": entry_low,
        "entry_high": entry_high,
        "entry_ref": entry_ref,
        "sl": sl,
        "score": score,
        "status": status,
        "vol_ratio": round(vol_ratio, 2),
        "momentum": round(momentum, 2)
    }