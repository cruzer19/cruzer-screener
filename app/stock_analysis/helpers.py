import pandas as pd


# ==========================================================
# 📉 MINOR SUPPORT
# ==========================================================
def calc_minor_support(df, lookback=12):
    """
    Minor support = lowest low dari N candle terakhir
    Aman untuk:
    - low / Low / LOW
    - MultiIndex column
    - selalu return float atau None
    """
    if df is None or df.empty:
        return None

    recent = df.tail(lookback)

    # ===== CASE NORMAL COLUMN =====
    for col in ["low", "Low", "LOW"]:
        if col in recent.columns:
            series = recent[col].dropna()
            if series.empty:
                return None
            return float(series.min())

    # ===== CASE MULTI INDEX =====
    if isinstance(recent.columns, pd.MultiIndex):
        for col in recent.columns:
            if str(col[-1]).lower() == "low":
                series = recent[col].dropna()
                if series.empty:
                    return None
                return float(series.min())

    return None


# ==========================================================
# 🧼 CLEAN PRICE DATA
# ==========================================================
def clean_price_df(df):

    if df is None:
        return None

    df = df.copy()

    # ===== FLATTEN MULTI INDEX =====
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join(col).upper() for col in df.columns]
    else:
        df.columns = [str(c).upper().strip() for c in df.columns]

    # ===== NORMALIZE OHLC =====
    col_map = {}

    for col in df.columns:
        c = col.upper()

        if "OPEN" in c:
            col_map[col] = "OPEN"
        elif "HIGH" in c:
            col_map[col] = "HIGH"
        elif "LOW" in c:
            col_map[col] = "LOW"
        elif "CLOSE" in c:
            col_map[col] = "CLOSE"

    df = df.rename(columns=col_map)

    # ===== VALIDATE =====
    if "CLOSE" not in df.columns:
        return None

    # ===== NUMERIC =====
    for col in ["OPEN", "HIGH", "LOW", "CLOSE"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["CLOSE"])
    df = df.sort_index()

    return df

# ==========================================================
# 💰 FORMAT MONEY
# ==========================================================
def format_money(x):
    """
    Convert number → human readable:
    1,000,000 → 1.00 M
    """
    if pd.isna(x):
        return "-"

    x = float(x)
    sign = "-" if x < 0 else ""
    x = abs(x)

    if x >= 1_000_000_000_000:
        return f"{sign}{x/1_000_000_000_000:.2f} T"
    elif x >= 1_000_000_000:
        return f"{sign}{x/1_000_000_000:.2f} B"
    elif x >= 1_000_000:
        return f"{sign}{x/1_000_000:.2f} M"
    else:
        return f"{sign}{int(x):,}".replace(",", ".")


# ==========================================================
# 🔢 FORMAT NUMBER
# ==========================================================
def format_number(x):
    """
    Format angka biasa:
    1000000 → 1.000.000
    """
    try:
        return f"{int(x):,}".replace(",", ".")
    except:
        return "-"