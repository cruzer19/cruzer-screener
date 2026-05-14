import pandas as pd


# ======================================================
# EMA
# ======================================================

def ema(series: pd.Series, period: int):

    return series.ewm(
        span=period,
        adjust=False
    ).mean()


# ======================================================
# RSI (TradingView Style / Wilder Smoothing)
# ======================================================

def rsi(series: pd.Series, period=14):

    delta = series.diff()

    gain = delta.clip(lower=0)

    loss = -delta.clip(upper=0)

    # Wilder smoothing
    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi


# ======================================================
# MACD
# ======================================================

def macd(
    series: pd.Series,
    fast=12,
    slow=26,
    signal=9
):
    """
    MACD Indicator

    Returns:
    - macd_line
    - signal_line
    - histogram
    """

    ema_fast = series.ewm(
        span=fast,
        adjust=False
    ).mean()

    ema_slow = series.ewm(
        span=slow,
        adjust=False
    ).mean()

    macd_line = ema_fast - ema_slow

    signal_line = macd_line.ewm(
        span=signal,
        adjust=False
    ).mean()

    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram