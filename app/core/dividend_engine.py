import yfinance as yf
import pandas as pd


class DividendEngine:

    @staticmethod
    def get_summary(symbol: str):
        ticker = yf.Ticker(symbol)

        info = ticker.info
        dividends = ticker.dividends

        # =========================
        # DEFAULT VALUES
        # =========================
        years_paying = 0

        last_dividend_1 = 0
        last_dividend_2 = 0

        last_date_1 = None
        last_date_2 = None

        # =========================
        # PROCESS DIVIDENDS
        # =========================
        if not dividends.empty:

            # Hitung berapa tahun pernah bagi dividen
            years_paying = len(dividends.groupby(dividends.index.year))

            # Dividen terakhir (paling baru)
            last_dividend_1 = float(dividends.iloc[-1])
            last_date_1 = dividends.index[-1].date()

            # Dividen sebelumnya
            if len(dividends) > 1:
                last_dividend_2 = float(dividends.iloc[-2])
                last_date_2 = dividends.index[-2].date()

        # =========================
        # HARGA SEKARANG
        # =========================
        price = info.get("currentPrice")

        # Fallback kalau currentPrice None
        if not price:
            price = info.get("regularMarketPrice")

        return {
            "symbol": symbol,
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "price": price,

            "dividend_yield": info.get("dividendYield"),
            "payout_ratio": info.get("payoutRatio"),
            "years_paying": years_paying,

            # 2 last dividends
            "last_dividend_1": last_dividend_1,
            "last_dividend_2": last_dividend_2,

            # 2 last dates
            "last_dividend_date_1": last_date_1,
            "last_dividend_date_2": last_date_2,
        }

    @staticmethod
    def get_history(symbol: str):
        ticker = yf.Ticker(symbol)
        return ticker.dividends

    @staticmethod
    def scan(symbols):
        results = []

        for s in symbols:
            try:
                data = DividendEngine.get_summary(s)
                results.append(data)
            except:
                pass

        return pd.DataFrame(results)