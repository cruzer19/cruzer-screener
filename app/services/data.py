import yfinance as yf
import pandas as pd

def get_price_data(ticker):

    symbol = f"{ticker}.JK"

    df = yf.download(
        symbol,
        period="5d",
        interval="15m",
        progress=False,
        threads=False
    )

    if df is None or df.empty:
        return None

    # 🔥 FIX MULTIINDEX
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    df.columns = [str(c).upper().strip() for c in df.columns]

    # Optional rename
    if "ADJ CLOSE" in df.columns:
        df = df.rename(columns={"ADJ CLOSE": "CLOSE"})

    return df