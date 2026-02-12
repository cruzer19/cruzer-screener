import numpy as np
import pandas as pd


# ==========================================================
# =================== HELPER: TICK ROUND ===================
# ==========================================================
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


# ==========================================================
# =================== CYCLE ANALYSIS ENGINE ================
# ==========================================================
def analyze_cycle(df):
    """
    Deteksi ritme bottom-to-bottom historis

    Output:
    - Last Low
    - Near Low (tanggal tunggal)
    - Next Low (tanggal tunggal)
    - Near High
    - Next High

    + VERSI RANGE:
    - next_low_start / end
    - second_low_start / end
    - next_high_start / end
    - second_high_start / end
    """

    if df is None or len(df) < 200:
        return None

    close = df["Close"]

    if hasattr(close, "columns"):
        close = close.iloc[:, 0]

    close = close.astype(float)

    # ===============================
    # Cari swing low besar
    # ===============================
    window = 50
    rolling_min = close.rolling(window, center=True).min()
    low_points = close[(close == rolling_min)].dropna()

    if len(low_points) < 4:
        return None

    dates = low_points.index.sort_values()

    # ===============================
    # Hitung jarak antar low (hari)
    # ===============================
    diffs = np.diff(dates.values).astype('timedelta64[D]').astype(int)

    if len(diffs) == 0:
        return None

    avg_cycle_days = int(np.mean(diffs))
    half_cycle = int(avg_cycle_days / 2)

    # 🔹 RANGE BUFFER (BIAR GA TERLALU PRESISI)
    if avg_cycle_days < 70:
        range_days = 3
    else:
        range_days = 4


    last_low_date = dates[-1]
    today = pd.Timestamp.today()

    # ===============================
    # PROYEKSI LOW
    # ===============================
    projected_next_low = last_low_date + pd.Timedelta(days=avg_cycle_days)

    while projected_next_low < today:
        projected_next_low += pd.Timedelta(days=avg_cycle_days)

    second_next_low = projected_next_low + pd.Timedelta(days=avg_cycle_days)

    days_to_next_low = (projected_next_low - today).days
    days_to_second_low = (second_next_low - today).days

    # LOW RANGE
    next_low_start = projected_next_low - pd.Timedelta(days=range_days)
    next_low_end   = projected_next_low + pd.Timedelta(days=range_days)

    second_low_start = second_next_low - pd.Timedelta(days=range_days)
    second_low_end   = second_next_low + pd.Timedelta(days=range_days)

    # ===============================
    # PROYEKSI HIGH (MID CYCLE)
    # ===============================
    projected_next_high = projected_next_low - pd.Timedelta(days=half_cycle)
    second_next_high = second_next_low - pd.Timedelta(days=half_cycle)

    days_to_next_high = (projected_next_high - today).days
    days_to_second_high = (second_next_high - today).days

    # HIGH RANGE
    next_high_start = projected_next_high - pd.Timedelta(days=range_days)
    next_high_end   = projected_next_high + pd.Timedelta(days=range_days)

    second_high_start = second_next_high - pd.Timedelta(days=range_days)
    second_high_end   = second_next_high + pd.Timedelta(days=range_days)

    # ===============================
    # CONFIDENCE (stability)
    # ===============================
    std_cycle = np.std(diffs)

    if std_cycle <= 15:
        confidence = "High"
    elif std_cycle <= 35:
        confidence = "Medium"
    else:
        confidence = "Low"

    return {
        "last_low": str(last_low_date.date()),

        # === TANGGAL TUNGGAL (BACKWARD COMPATIBLE) ===
        "next_low": str(projected_next_low.date()),
        "days_to_next_low": int(days_to_next_low),

        "second_low": str(second_next_low.date()),
        "days_to_second_low": int(days_to_second_low),

        "next_high": str(projected_next_high.date()),
        "days_to_next_high": int(days_to_next_high),

        "second_high": str(second_next_high.date()),
        "days_to_second_high": int(days_to_second_high),

        # === RANGE BARU (VERSI LEBIH AKURAT) ===
        "next_low_start": str(next_low_start.date()),
        "next_low_end": str(next_low_end.date()),

        "second_low_start": str(second_low_start.date()),
        "second_low_end": str(second_low_end.date()),

        "next_high_start": str(next_high_start.date()),
        "next_high_end": str(next_high_end.date()),

        "second_high_start": str(second_high_start.date()),
        "second_high_end": str(second_high_end.date()),

        "confidence": confidence
    }


# ==========================================================
# =================== MAIN ANALYSIS ENGINE =================
# ==========================================================
def analyze_single_stock(df):
    close = df["Close"]

    if hasattr(close, "columns"):
        close = close.iloc[:, 0]

    close = close.astype(float)

    # === MOVING AVERAGE ===
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()

    ma20_last = float(ma20.iloc[-1])
    ma50_last = float(ma50.iloc[-1])

    # === PRICE STRUCTURE ===
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

    # === ENTRY ZONE ===
    entry_low = round_to_tick(support * 1.01)
    entry_high = round_to_tick(support * 1.03)

    risk_pct = round((last_price - support) / last_price * 100, 2)

    # === CYCLE ANALYSIS ===
    cycle = analyze_cycle(df)

    return {
        "trend": trend,
        "last_price": last_price,
        "support": support,
        "resistance": resistance,
        "entry_zone": (entry_low, entry_high),
        "risk_pct": risk_pct,
        "cycle": cycle
    }