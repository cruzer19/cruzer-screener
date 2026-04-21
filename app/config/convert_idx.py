import pandas as pd

# ===============================
# LOAD EXCEL
# ===============================
FILE_PATH = "Stock List.xlsx"

df = pd.read_excel(FILE_PATH)

# ===============================
# FILTER (BUANG WATCHLIST)
# ===============================
if "Watchlist" in df.columns:
    df = df[df["Watchlist"] != "Yes"]

# ===============================
# CLEAN DATA
# ===============================
df = df.dropna(subset=["Code"])
df["Code"] = df["Code"].astype(str).str.strip()

# ===============================
# HELPER: GET NAME
# ===============================
NAME_COLUMNS = ["Name", "Company Name", "Emiten", "Nama Perusahaan"]

def get_name(row):
    for col in NAME_COLUMNS:
        if col in row and pd.notna(row[col]):
            return str(row[col]).strip()
    return ""

# ===============================
# HELPER: GET SECTOR
# ===============================
def get_sector(row):
    if "Sector" in row and pd.notna(row["Sector"]):
        return str(row["Sector"]).strip().upper()
    return "OTHER"

# ===============================
# HELPER: GET DIVIDEND (DARI EXCEL)
# ===============================
def is_dividend(row):
    val = str(row.get("Dividend", "")).strip().upper()
    return val in ["YES", "TRUE", "1", "Y"]

# ===============================
# BUILD DATA
# ===============================
codes = sorted(set(df["Code"].tolist()))

profile_dict = {}
sector_dict = {}
dividend_list = []

for _, row in df.iterrows():
    code = row["Code"]

    name = get_name(row)
    sector = get_sector(row)

    if name:
        profile_dict[code] = name

    if sector:
        sector_dict[code] = sector

    if is_dividend(row):
        dividend_list.append(code)

# remove duplicate + sort
dividend_list = sorted(set(dividend_list))

# ===============================
# GENERATE FILES
# ===============================

def write_dict(filename, var_name, data_dict):
    with open(filename, "w") as f:
        f.write(f"{var_name} = {{\n\n")
        for k, v in sorted(data_dict.items()):
            f.write(f'    "{k}": "{v}",\n')
        f.write("\n}\n")


def write_list(filename, var_name, data_list):
    with open(filename, "w") as f:
        f.write(f"{var_name} = [\n\n")
        for i, val in enumerate(data_list):
            if i % 10 == 0:
                f.write("    ")
            f.write(f'"{val}", ')
            if i % 10 == 9:
                f.write("\n")
        f.write("\n]\n")


# ===============================
# OUTPUT
# ===============================
write_list("saham_list.py", "SAHAM_LIST", codes)
print(f"✅ saham_list.py created ({len(codes)} stocks)")

write_dict("saham_profile.py", "SAHAM_PROFILE", profile_dict)
print("✅ saham_profile.py created")

write_dict("saham_sector.py", "SAHAM_SECTOR", sector_dict)
print("✅ saham_sector.py created")

write_list("dividend_list.py", "DIVIDEND_LIST", dividend_list)
print(f"✅ dividend_list.py created ({len(dividend_list)} stocks)")

print("\n🚀 Semua file berhasil di-generate!")