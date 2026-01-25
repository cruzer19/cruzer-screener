import pandas as pd
import os
from datetime import date
from app.config.saham_list import SAHAM_LIST
from app.core.data_loader import load_daily_data

DATA_PATH = "data/trades.csv"

COLUMNS = [
    "kode",
    "buy_date",
    "buy_price",
    "buy_lot",
    "remaining_lot",
    "sell_date",
    "sell_price",
    "sell_lot",
    "note",
]

# ======================================================
# SAFE CAST
# ======================================================
def to_int_safe(val, default=0):
    try:
        if val == "" or pd.isna(val):
            return default
        return int(float(val))
    except:
        return default


# ======================================================
# LOAD / INIT
# ======================================================
def load_trades() -> pd.DataFrame:
    if not os.path.exists(DATA_PATH) or os.path.getsize(DATA_PATH) == 0:
        return pd.DataFrame(columns=COLUMNS)

    df = pd.read_csv(DATA_PATH)
    df.index.name = "trade_id"
    return df


# ======================================================
# DELETE TRADE
# ======================================================
def delete_trade(idx: int):
    df = load_trades()
    if idx not in df.index:
        return
    df = df.drop(index=idx)
    df.to_csv(DATA_PATH, index=False)


# ======================================================
# SAVE BUY
# ======================================================
def save_buy(
    kode: str,
    buy_date: date,
    buy_price: float,
    buy_lot: int,
    note: str = "",
):
    if kode not in SAHAM_LIST:
        raise ValueError("Kode saham tidak valid")

    df = load_trades()

    new_row = {
        "kode": kode,
        "buy_date": buy_date,
        "buy_price": buy_price,
        "buy_lot": buy_lot,
        "remaining_lot": buy_lot,
        "sell_date": "",
        "sell_price": "",
        "sell_lot": "",
        "note": note,
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(DATA_PATH, index=False)


# ======================================================
# PARTIAL / FULL SELL
# ======================================================
def save_sell(
    index: int,
    sell_date: date,
    sell_price: float,
    sell_lot: int,
):
    df = load_trades()

    remaining = to_int_safe(df.loc[index, "remaining_lot"])

    if sell_lot > remaining:
        raise ValueError("Lot jual melebihi sisa lot")

    df.loc[index, "sell_date"] = sell_date
    df.loc[index, "sell_price"] = sell_price
    df.loc[index, "sell_lot"] = sell_lot
    df.loc[index, "remaining_lot"] = remaining - sell_lot

    df.to_csv(DATA_PATH, index=False)


# ======================================================
# ENRICH (STATUS + LAST PRICE + PNL + HOLDING DAYS)
# ======================================================
def enrich_trades(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    rows = []
    today = date.today()

    for idx, row in df.iterrows():
        kode = row.get("kode", "")

        # ===== LAST PRICE =====
        last_price = 0
        df_price = load_daily_data(kode)
        if df_price is not None and not df_price.empty:
            last_price = to_int_safe(df_price["Close"].iloc[-1])

        # ===== SAFE VALUES =====
        buy_price = to_int_safe(row.get("buy_price"))
        buy_lot = to_int_safe(row.get("buy_lot"))
        remaining = to_int_safe(row.get("remaining_lot"))
        sell_price = to_int_safe(row.get("sell_price"))

        # ===== DATES =====
        buy_date_raw = row.get("buy_date")
        buy_date = (
            pd.to_datetime(buy_date_raw).date()
            if buy_date_raw not in ["", None] else None
        )

        sell_date_raw = row.get("sell_date")
        sell_date = (
            pd.to_datetime(sell_date_raw).date()
            if sell_date_raw not in ["", None] else None
        )

        sold_lot = max(buy_lot - remaining, 0)

        # ===== STATUS, PNL, HOLDING =====
        if sold_lot == 0:
            status = "OPEN"
            pnl_rp = 0
            pnl_pct = 0
            holding_days = (today - buy_date).days if buy_date else 0
        else:
            pnl_rp = (sell_price - buy_price) * sold_lot * 100
            pnl_pct = (
                (sell_price - buy_price) / buy_price * 100
                if buy_price > 0 else 0
            )

            end_date = sell_date if sell_date else today
            holding_days = (end_date - buy_date).days if buy_date else 0

            status = "CLOSED" if remaining == 0 else "PARTIAL"

        rows.append({
            # ===== INTERNAL =====
            "trade_id": idx,
            "kode": kode,
            "buy_date": buy_date,
            "sell_date": sell_date,
            "buy_price": buy_price,
            "last_price": last_price,
            "buy_lot": buy_lot,
            "remaining_lot": remaining,
            "sell_price": sell_price,
            "sell_lot": sold_lot,
            "note": row.get("note", ""),

            # ===== UI READY =====
            "Kode": kode,
            "Buy Date": buy_date,
            "Sell Date": sell_date if sold_lot > 0 else "",
            "Holding Days": holding_days,
            "Buy": buy_price,
            "Now": last_price,
            "Sell": sell_price if sold_lot > 0 else "",
            "Sisa Lot": remaining,
            "Status": status,
            "PnL (Rp)": int(pnl_rp),
            "PnL (%)": round(pnl_pct, 2),
        })

    return pd.DataFrame(rows)