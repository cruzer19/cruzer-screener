import yfinance as yf
import pandas as pd


def load_daily_data(kode: str, period="6mo"):
    ticker = f"{kode}.JK"

    try:
        df = yf.download(
            ticker,
            period=period,
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False
        )
    except Exception:
        return None

    if df is None or df.empty:
        return None

    # === FLATTEN MULTIINDEX (PENTING) ===
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # pastikan kolom wajib ada
    required_cols = {"Open", "High", "Low", "Close", "Volume"}
    if not required_cols.issubset(df.columns):
        return None

    # buang baris invalid
    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

    if df.empty:
        return None

    return df

def load_weekly_data(kode: str, period="2y"):
    ticker = f"{kode}.JK"

    try:
        df = yf.download(
            ticker,
            period=period,
            interval="1wk",   # 🔥 INI KUNCI UTAMA
            progress=False,
            auto_adjust=False,
            threads=False
        )
    except Exception:
        return None

    if df is None or df.empty:
        return None

    # === FLATTEN MULTIINDEX ===
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required_cols = {"Open", "High", "Low", "Close", "Volume"}
    if not required_cols.issubset(df.columns):
        return None

    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

    if df.empty:
        return None

    return df