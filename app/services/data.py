import yfinance as yf
import pandas as pd


# ================= NORMALIZE TICKER =================
def normalize_ticker(ticker: str) -> str:

    if not ticker:
        return ticker

    ticker = ticker.strip().upper()

    # ✅ INDEX (IHSG, dll)
    if ticker.startswith("^"):
        return ticker

    # ✅ SUDAH ADA SUFFIX (misal .JK, .US, dll)
    if "." in ticker:
        return ticker

    # ✅ DEFAULT: saham Indonesia
    return f"{ticker}.JK"


# ================= MAIN FUNCTION =================
def get_price_data(ticker):

    symbol = normalize_ticker(ticker)

    try:
        df = yf.download(
            symbol,
            period="10d",
            interval="15m",
            progress=False,
            threads=False
        )
    except Exception as e:
        print("YF ERROR:", symbol, e)
        return None

    if df is None or df.empty:
        print("EMPTY DATA:", symbol)
        return None

    # ================= FIX MULTIINDEX =================
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    df.columns = [str(c).upper().strip() for c in df.columns]

    # ================= CLEAN COLUMN =================
    if "ADJ CLOSE" in df.columns:
        df = df.rename(columns={"ADJ CLOSE": "CLOSE"})

    return df