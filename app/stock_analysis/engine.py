import pandas as pd


# ==========================================================
# 📉 GAP FILL RATE
# ==========================================================
def calculate_gap_fill_rate(df):

    if df is None or df.empty:
        return 0

    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]

    df.columns = [str(c).upper().strip() for c in df.columns]

    if not all(col in df.columns for col in ["OPEN", "HIGH", "LOW"]):
        return 0

    gaps = []

    for i in range(1, len(df)):
        prev_high = df.iloc[i - 1]["HIGH"]

        if df.iloc[i]["OPEN"] > prev_high:

            filled = False

            for j in range(i, min(i + 10, len(df))):
                if df.iloc[j]["LOW"] <= prev_high:
                    filled = True
                    break

            gaps.append(filled)

    if not gaps:
        return 0

    return round(sum(gaps) / len(gaps) * 100, 1)


# ==========================================================
# 📊 SUPPORT LEVELS
# ==========================================================
def get_support_levels(df_price, result):

    if df_price is None or df_price.empty:
        return [], pd.DataFrame()

    df = df_price.copy()

    df.columns = [str(c).upper().strip() for c in df.columns]

    last_price = result.get("last_price")

    major_support = result.get("support")

    # 🔹 minor support (20 hari)
    minor_support = df["LOW"].tail(20).min() if "LOW" in df.columns else None

    # 🔹 micro support (7 hari)
    micro_support = df["LOW"].tail(7).min() if "LOW" in df.columns else None

    supports = []

    if micro_support is not None:
        supports.append(("Micro", int(micro_support)))

    if minor_support is not None:
        supports.append(("Minor", int(minor_support)))

    if major_support is not None:
        supports.append(("Major", int(major_support)))

    # urutkan berdasarkan kedekatan ke harga sekarang
    supports_sorted = sorted(
        supports,
        key=lambda x: abs(last_price - x[1])
    )

    rows = []

    if len(supports_sorted) >= 1:
        rows.append(("Support (Near)", f"{supports_sorted[0][1]} ({supports_sorted[0][0]})"))

    if len(supports_sorted) >= 2:
        rows.append(("Support (Mid)", f"{supports_sorted[1][1]} ({supports_sorted[1][0]})"))

    if len(supports_sorted) >= 3:
        rows.append(("Support (Far)", f"{supports_sorted[2][1]} ({supports_sorted[2][0]})"))

    rows.append(("Resistance", str(int(result.get("resistance", 0)))))

    sr_df = pd.DataFrame(rows, columns=["Level", "Price"])

    return supports_sorted, sr_df


# ==========================================================
# 🎯 ENTRY PLAN
# ==========================================================
def get_entry_plan(supports_sorted, result):

    if not supports_sorted:
        return pd.DataFrame()

    near_support = supports_sorted[0][1]

    if len(supports_sorted) >= 2:
        deep_support = supports_sorted[1][1]
    else:
        deep_support = near_support

    # 🔹 ENTRY NEAR
    entry_near_low = int(near_support * 0.995)
    entry_near_high = int(near_support * 1.015)

    # 🔹 ENTRY DEEP
    entry_deep_low = int(deep_support * 0.99)
    entry_deep_high = int(deep_support * 1.02)

    entry_df = pd.DataFrame(
        {
            "Parameter": [
                "Entry Near (Pullback)",
                "Entry Deep (Discount)",
                "Risk",
            ],
            "Value": [
                f"{entry_near_low} – {entry_near_high}",
                f"{entry_deep_low} – {entry_deep_high}",
                f"{result.get('risk_pct', 0)} %",
            ],
        }
    )

    return entry_df