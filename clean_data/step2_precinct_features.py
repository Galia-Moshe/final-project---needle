"""
STEP 2 — Build Precinct Feature Table
Safety in Urban Tourism Project
=====================================
Input:  clean_nypd.csv  (from step1)
Output: precinct_features.csv
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler

INPUT_PATH  = "clean_nypd.csv"
OUTPUT_PATH = "precinct_features.csv"

print("=" * 55)
print("  STEP 2: Building precinct feature table")
print("=" * 55)

# ── Load clean data ───────────────────────────────────────────
print("\n[1/5] Loading clean_nypd.csv...")
df = pd.read_csv(INPUT_PATH, low_memory=False)

# Fix: drop (NULL) borough rows
df = df[df["borough"] != "(NULL)"]

print(f"    Loaded {len(df):,} rows, {df['precinct'].nunique()} precincts")
print(f"    Columns: {list(df.columns)}")

# ── Total crime count per precinct ────────────────────────────
print("\n[2/5] Computing crime counts per precinct...")
features = pd.DataFrame()
features["total_crimes"] = df.groupby("precinct").size()

# ── Law category percentages ──────────────────────────────────
law = df.groupby(["precinct", "law_category"]).size().unstack(fill_value=0)
law = law.div(law.sum(axis=1), axis=0) * 100

for cat in ["FELONY", "MISDEMEANOR", "VIOLATION"]:
    features[f"pct_{cat.lower()}"] = law[cat] if cat in law.columns else 0.0

# ── Crime type percentages ────────────────────────────────────
print("\n[3/5] Computing crime type percentages per precinct...")

# Note: data spells it "HARRASSMENT" with double R
THEFT_KEYWORDS      = ["LARCENY", "ROBBERY", "BURGLARY"]
ASSAULT_KEYWORDS    = ["ASSAULT", "MURDER", "RAPE", "SEX CRIMES", "FELONY ASSAULT"]
DRUG_KEYWORDS       = ["DRUG", "NARCOTIC", "CONTROLLED SUBSTANCE"]
FRAUD_KEYWORDS      = ["FRAUD", "FORGERY", "IDENTITY THEFT", "FRAUDULENT"]
HARASSMENT_KEYWORDS = ["HARRASSMENT", "HARASSMENT", "STALK", "MENACING"]

def flag(desc, keywords):
    desc = str(desc).upper()
    return any(k in desc for k in keywords)

df["is_theft"]      = df["offense_desc"].apply(lambda x: flag(x, THEFT_KEYWORDS))
df["is_assault"]    = df["offense_desc"].apply(lambda x: flag(x, ASSAULT_KEYWORDS))
df["is_drug"]       = df["offense_desc"].apply(lambda x: flag(x, DRUG_KEYWORDS))
df["is_fraud"]      = df["offense_desc"].apply(lambda x: flag(x, FRAUD_KEYWORDS))
df["is_harassment"] = df["offense_desc"].apply(lambda x: flag(x, HARASSMENT_KEYWORDS))

for col in ["is_theft", "is_assault", "is_drug", "is_fraud", "is_harassment"]:
    cat_name = col.replace("is_", "pct_")
    counts = df.groupby("precinct")[col].sum()
    features[cat_name] = (counts / features["total_crimes"] * 100).fillna(0)

print(f"    Theft crimes flagged:      {df['is_theft'].sum():,}")
print(f"    Assault crimes flagged:    {df['is_assault'].sum():,}")
print(f"    Drug crimes flagged:       {df['is_drug'].sum():,}")
print(f"    Fraud crimes flagged:      {df['is_fraud'].sum():,}")
print(f"    Harassment crimes flagged: {df['is_harassment'].sum():,}")

# ── Night crime ratio (10pm–6am) ──────────────────────────────
df["is_night"] = df["hour"].apply(
    lambda h: 1 if pd.notna(h) and (h >= 22 or h <= 6) else 0
)
features["pct_night"] = df.groupby("precinct")["is_night"].mean() * 100

# ── Borough (reference only) ──────────────────────────────────
features["borough"] = df.groupby("precinct")["borough"].agg(
    lambda x: x.mode()[0] if len(x) > 0 else "UNKNOWN"
)

features = features.reset_index()
print(f"\n    Feature table shape: {features.shape}")

# ── Approximate precinct areas (km²) ─────────────────────────
print("\n[4/5] Computing approximate crime per km²...")
PRECINCT_AREA_KM2 = {
    1:4.0, 5:3.2, 6:3.1, 7:2.8, 9:3.5, 10:3.0, 13:2.9, 14:3.4,
    17:2.6, 18:3.8, 19:4.2, 20:3.9, 22:33.5, 23:3.1, 24:3.0, 25:2.8,
    26:2.7, 28:3.2, 30:3.0, 32:3.1, 33:3.4, 34:3.3, 40:4.0, 41:4.5,
    42:5.1, 43:4.8, 44:4.2, 45:11.2, 46:4.9, 47:8.6, 48:5.2, 49:7.8,
    50:14.2, 52:4.6, 60:7.2, 61:9.1, 62:8.8, 63:9.3, 66:6.9, 67:6.1,
    68:10.3, 69:7.4, 70:7.8, 71:6.3, 72:7.1, 73:8.4, 75:11.5, 76:5.9,
    77:5.7, 78:5.5, 79:5.8, 81:6.7, 83:6.2, 84:4.1, 88:5.0, 90:7.3,
    94:11.8, 100:15.2, 101:18.4, 102:14.9, 103:12.1, 104:18.6, 105:28.1,
    106:16.3, 107:18.7, 108:12.4, 109:20.1, 110:14.8, 111:19.2, 112:12.9,
    113:14.7, 114:12.3, 115:17.5, 120:58.7, 121:35.2, 122:30.4, 123:22.1
}
features["area_km2"] = features["precinct"].map(PRECINCT_AREA_KM2).fillna(5.0)
features["crimes_per_km2"] = features["total_crimes"] / features["area_km2"]

# ── Normalize with StandardScaler ────────────────────────────
print("\n[5/5] Normalizing with StandardScaler...")

FEATURE_COLS = [
    "crimes_per_km2",
    "pct_felony", "pct_misdemeanor",
    "pct_theft", "pct_assault", "pct_drug", "pct_fraud", "pct_harassment",
    "pct_night"
]

# Save raw values for human interpretation
for col in FEATURE_COLS:
    features[f"raw_{col}"] = features[col]

scaler = StandardScaler()
features[FEATURE_COLS] = scaler.fit_transform(features[FEATURE_COLS])

print("\n  StandardScaler params (paste into writeup):")
for i, col in enumerate(FEATURE_COLS):
    print(f"    {col:25s}  mean={scaler.mean_[i]:.2f}  std={scaler.scale_[i]:.2f}")

features.to_csv(OUTPUT_PATH, index=False)

print(f"\n{'='*55}")
print(f"  DONE — precinct_features.csv saved")
print(f"  Shape: {features.shape}")
print(f"\n  Top 5 precincts by crime rate (crimes/km²):")
top = features.nlargest(5, "raw_crimes_per_km2")[
    ["precinct", "borough", "raw_crimes_per_km2", "raw_pct_felony", "raw_pct_theft"]
]
print(top.to_string(index=False))
print(f"\n  Bottom 5 (safest precincts):")
bot = features.nsmallest(5, "raw_crimes_per_km2")[
    ["precinct", "borough", "raw_crimes_per_km2", "raw_pct_felony", "raw_pct_theft"]
]
print(bot.to_string(index=False))
print(f"\n  → Share precinct_features.csv with Peleg (Q1 clustering)")
print(f"  → Run step3_base_map.py next for real shapefile areas")