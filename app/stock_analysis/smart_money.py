import pandas as pd


# ==========================================================
# 💰 SMART MONEY FULL ENGINE
# ==========================================================
def calculate_smart_money(df):

    if df is None or df.empty:
        return None

    df = df.copy()

    # ================= NORMALIZE COLUMN =================
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]

    df.columns = [str(c).upper().strip() for c in df.columns]

    # ================= MAP COLUMN =================
    col_map = {}
    for col in df.columns:
        if "OPEN" in col: col_map["OPEN"] = col
        elif "CLOSE" in col: col_map["CLOSE"] = col
        elif "VOLUME" in col: col_map["VOLUME"] = col
        elif "HIGH" in col: col_map["HIGH"] = col
        elif "LOW" in col: col_map["LOW"] = col

    required = ["OPEN", "CLOSE", "VOLUME"]
    if not all(k in col_map for k in required):
        return None

    df = df.rename(columns={
        col_map["OPEN"]: "OPEN",
        col_map["CLOSE"]: "CLOSE",
        col_map["VOLUME"]: "VOLUME",
        **({col_map["HIGH"]: "HIGH"} if "HIGH" in col_map else {}),
        **({col_map["LOW"]: "LOW"} if "LOW" in col_map else {}),
    })

    for col in ["OPEN", "CLOSE", "VOLUME"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["OPEN", "CLOSE", "VOLUME"])

    if df.empty:
        return None

    # ================= CORE =================
    df["VALUE"] = df["CLOSE"] * df["VOLUME"]

    # ================= AVP =================
    if "HIGH" in df.columns and "LOW" in df.columns:
        df["AVP"] = (df["OPEN"] + df["HIGH"] + df["LOW"] + df["CLOSE"]) / 4
    else:
        df["AVP"] = (df["OPEN"] + df["CLOSE"]) / 2

    # ================= SMART MONEY (IMPROVED) =================
    if "HIGH" in df.columns and "LOW" in df.columns:
        spread = (df["HIGH"] - df["LOW"]).replace(0, 1)
        close_pos = (df["CLOSE"] - df["LOW"]) / spread
        close_pos = close_pos.clip(0.2, 0.8)
    else:
        close_pos = (df["CLOSE"] > df["OPEN"]).astype(float)

    df["SMART"] = df["VALUE"] * close_pos
    df["BAD"] = df["VALUE"] * (1 - close_pos)
    df["BAD"] = -df["BAD"]

    df["CLEAN"] = df["SMART"] + df["BAD"]

    df["GAIN (%)"] = df["CLOSE"].pct_change() * 100

    # ================= RCV =================
    df["RCV"] = (df["CLEAN"] / df["VALUE"]) * 100
    df["RCV"] = df["RCV"].fillna(0).clip(-100, 100).round(0)

    # ================= SIGNAL =================
    def get_signal(rcv):
        if rcv > 50:
            return "🚀"
        elif rcv > 20:
            return "🔥"
        elif rcv > 0:
            return "🟢"
        elif rcv > -20:
            return "⚠️"
        else:
            return "🔴"

    df["SIGNAL"] = df["RCV"].apply(get_signal)

    # ================= STREAK =================
    df["ACC"] = df["CLEAN"] > 0
    df["STREAK"] = df["ACC"].astype(int).groupby((~df["ACC"]).cumsum()).cumsum()

    sm_df = df.tail(10)

    # ================= SUMMARY =================
    total_value = sm_df["VALUE"].sum()
    total_smart = sm_df["SMART"].sum()
    total_clean = sm_df["CLEAN"].sum()

    power = (total_smart / total_value * 100) if total_value > 0 else 0
    status = "🟢 BUYER DOMINANT" if total_clean > 0 else "🔴 SELLER DOMINANT"

    # ================= INSIGHT =================
    avg_rcv = sm_df["RCV"].mean()
    positive_days = (sm_df["CLEAN"] > 0).sum()

    first_half = sm_df.head(5)["RCV"].mean()
    last_half = sm_df.tail(5)["RCV"].mean()
    trend_up = last_half > first_half

    # ================= TABLE FORMAT =================
    display_df = sm_df.copy()

    display_df["Date"] = display_df.index.strftime("%d-%m-%Y")
    display_df["Tx"] = display_df["VOLUME"]

    display_df = display_df.reset_index(drop=True)

    return {
        "summary": {
            "smart": total_smart,
            "clean": total_clean,
            "power": round(power, 1),
            "status": status,
            "avg_rcv": round(avg_rcv, 0),
            "win_rate": positive_days,
            "trend_up": trend_up,
        },
        "table": display_df
    }