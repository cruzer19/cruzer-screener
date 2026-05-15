import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# =========================================
# CONFIG
# =========================================

import os

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

FILE_PATH = os.path.join(
    BASE_DIR,
    "Stock List.xlsx"
)


TOP_GAINER_COUNT = 70
TOP_LOSER_COUNT = 50
TOP_VOLUME_COUNT = 70

MIN_PRICE = 50
MIN_AVG_VOLUME = 2_000_000

OUTPUT_FILE = "hot_saham_list.py"

# =========================================
# LOAD STOCK LIST
# =========================================
df = pd.read_excel(FILE_PATH)

# remove watchlist if exists
if "Watchlist" in df.columns:
    df = df[df["Watchlist"] != "Yes"]

# clean
df = df.dropna(subset=["Code"])
df["Code"] = df["Code"].astype(str).str.strip().str.upper()

codes = sorted(set(df["Code"].tolist()))

# =========================================
# DOWNLOAD MARKET DATA
# =========================================
results = []

for code in codes:

    try:
        symbol = f"{code}.JK"

        stock = yf.Ticker(symbol)

        hist = stock.history(period="1mo")

        if len(hist) < 5:
            continue

        first_close = hist["Close"].iloc[0]
        last_close = hist["Close"].iloc[-1]

        monthly_change = (
            (last_close - first_close) / first_close
        ) * 100

        avg_volume = hist["Volume"].mean()

        latest_price = last_close

        results.append({
            "code": code,
            "monthly_change": monthly_change,
            "avg_volume": avg_volume,
            "price": latest_price
        })

    except Exception as e:
        print(f"❌ {code} error: {e}")

# =========================================
# CREATE DATAFRAME
# =========================================
market_df = pd.DataFrame(results)

if market_df.empty:
    print("❌ No market data")
    exit()

# =========================================
# FILTER LOW QUALITY STOCKS
# =========================================
market_df = market_df[
    (market_df["price"] >= MIN_PRICE)
    &
    (market_df["avg_volume"] >= MIN_AVG_VOLUME)
]

# =========================================
# TOP GAINERS
# =========================================
top_gainers = market_df.sort_values(
    by="monthly_change",
    ascending=False
).head(TOP_GAINER_COUNT)

# =========================================
# TOP LOSERS
# =========================================
top_losers = market_df.sort_values(
    by="monthly_change",
    ascending=True
).head(TOP_LOSER_COUNT)

# =========================================
# TOP VOLUME
# =========================================
top_volume = market_df.sort_values(
    by="avg_volume",
    ascending=False
).head(TOP_VOLUME_COUNT)

# =========================================
# COMBINE HOT LIST
# =========================================
hot_codes = set()

hot_codes.update(top_gainers["code"].tolist())
hot_codes.update(top_losers["code"].tolist())
hot_codes.update(top_volume["code"].tolist())

hot_codes = sorted(list(hot_codes))

# =========================================
# SAVE PY FILE
# =========================================
with open(OUTPUT_FILE, "w") as f:

    f.write("HOT_SAHAM_LIST = [\n\n")

    for i, code in enumerate(hot_codes):

        if i % 10 == 0:
            f.write("    ")

        f.write(f'"{code}", ')

        if i % 10 == 9:
            f.write("\n")

    f.write("\n]\n")

print(f"\n🔥 HOT_SAHAM_LIST created ({len(hot_codes)} stocks)")