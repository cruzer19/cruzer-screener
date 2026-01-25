import yfinance as yf

def load_price_data(ticker, period="6mo", interval="1d"):
    symbol = f"{ticker}.JK"
    df = yf.download(symbol, period=period, interval=interval)
    df = df.dropna()
    return df