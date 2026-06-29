"""
STEP 1 — Filter & Clean NYPD Dataset
Safety in Urban Tourism Project
=====================================
Run this first. Output: clean_nypd.csv
"""

import pandas as pd
import time

FILE_PATH = r"C:\Users\peleg\Data Science\data bases project\NYPD_Complaint_Data_Historic_20260602.csv"
OUTPUT_PATH = "clean_nypd.csv"

print("=" * 55)
print("  STEP 1: Loading & filtering NYPD data")
print("=" * 55)

# ── Load ──────────────────────────────────────────────────────
print("\n[1/6] Loading file... (this may take 5-10 min for large Excel files)")
t0 = time.time()

df = pd.read_excel(
    FILE_PATH,
    usecols=[
        "CMPLNT_FR_DT",   # date
        "CMPLNT_FR_TM",   # time
        "Latitude",
        "Longitude",
        "ADDR_PCT_CD",    # precinct
        "OFNS_DESC",      # offense description
        "LAW_CAT_CD",     # felony / misdemeanor / violation
        "PREM_TYP_DESC",  # premise type (street, subway, etc.)
        "BORO_NM",        # borough
    ]
)

print(f"    Loaded {len(df):,} rows in {time.time()-t0:.0f}s")
print(f"    Columns: {list(df.columns)}")

# ── Parse dates ───────────────────────────────────────────────
print("\n[2/6] Parsing dates...")
df["CMPLNT_FR_DT"] = pd.to_datetime(df["CMPLNT_FR_DT"], errors="coerce")
df["year"] = df["CMPLNT_FR_DT"].dt.year

# Extract hour from time field
df["hour"] = pd.to_datetime(df["CMPLNT_FR_TM"], format="%H:%M:%S", errors="coerce").dt.hour

total_before = len(df)
print(f"    Year range in data: {df['year'].min()} – {df['year'].max()}")

# ── Filter years (exclude COVID 2020-2021) ────────────────────
print("\n[3/6] Filtering to 2018-2019 + 2022-2023 (excluding COVID years)...")
df = df[df["year"].isin([2018, 2019, 2022, 2023])]
after_year_filter = len(df)
dropped_years = total_before - after_year_filter
print(f"    Kept:    {after_year_filter:,} rows")
print(f"    Dropped: {dropped_years:,} rows (wrong years or COVID period)")
print(f"    Year counts:\n{df['year'].value_counts().sort_index().to_string()}")

# ── Drop null / zero coordinates ──────────────────────────────
print("\n[4/6] Dropping null or zero coordinates...")
before_coord = len(df)

# null lat/lon
null_coords = df["Latitude"].isna() | df["Longitude"].isna()
# zero lat/lon (placeholder for missing)
zero_coords = (df["Latitude"] == 0) | (df["Longitude"] == 0)
# out-of-NYC bounds sanity check (NYC is roughly 40.4–40.95 lat, -74.3 – -73.7 lon)
out_of_bounds = (
    (df["Latitude"]  < 40.4) | (df["Latitude"]  > 40.95) |
    (df["Longitude"] < -74.3) | (df["Longitude"] > -73.7)
)

bad_coords = null_coords | zero_coords | out_of_bounds
df = df[~bad_coords]
after_coord = len(df)
dropped_coords = before_coord - after_coord

print(f"    Null coordinates:      {null_coords.sum():,}")
print(f"    Zero coordinates:      {zero_coords.sum():,}")
print(f"    Out-of-NYC bounds:     {out_of_bounds.sum():,}")
print(f"    Total dropped:         {dropped_coords:,} ({dropped_coords/before_coord*100:.1f}%)")
print(f"    Remaining:             {after_coord:,} rows")

# ── Drop rows missing key fields ──────────────────────────────
print("\n[5/6] Dropping rows missing precinct or offense type...")
before_key = len(df)
df = df.dropna(subset=["ADDR_PCT_CD", "OFNS_DESC", "LAW_CAT_CD"])
dropped_key = before_key - len(df)
print(f"    Dropped: {dropped_key:,} rows with missing precinct/offense")
print(f"    Remaining: {len(df):,} rows")

# ── Rename & clean up columns ─────────────────────────────────
print("\n[6/6] Renaming columns and saving...")
df = df.rename(columns={
    "CMPLNT_FR_DT": "date",
    "Latitude":     "lat",
    "Longitude":    "lon",
    "ADDR_PCT_CD":  "precinct",
    "OFNS_DESC":    "offense_desc",
    "LAW_CAT_CD":   "law_category",
    "PREM_TYP_DESC":"premise_type",
    "BORO_NM":      "borough",
})

# Standardize text fields
df["offense_desc"]  = df["offense_desc"].str.strip().str.upper()
df["law_category"]  = df["law_category"].str.strip().str.upper()
df["premise_type"]  = df["premise_type"].str.strip().str.upper()
df["borough"]       = df["borough"].str.strip().str.upper()
df["precinct"]      = df["precinct"].astype(int)

# Final column selection
df = df[["date", "year", "hour", "lat", "lon",
         "precinct", "borough", "offense_desc",
         "law_category", "premise_type"]]

df.to_csv(OUTPUT_PATH, index=False)

# ── Summary report ────────────────────────────────────────────
print("\n" + "=" * 55)
print("  DONE — Summary report (copy into writeup!)")
print("=" * 55)
print(f"\n  Original rows:          {total_before:,}")
print(f"  After year filter:      {after_year_filter:,}")
print(f"  After coord filter:     {after_coord:,}")
print(f"  Final clean rows:       {len(df):,}")
print(f"\n  Dropped (total):        {total_before - len(df):,} ({(total_before-len(df))/total_before*100:.1f}%)")
print(f"    - Wrong years:        {dropped_years:,}")
print(f"    - Bad coordinates:    {dropped_coords:,}")
print(f"    - Missing key fields: {dropped_key:,}")
print(f"\n  Years in clean data:    {sorted(df['year'].unique().tolist())}")
print(f"  Boroughs:               {sorted(df['borough'].dropna().unique().tolist())}")
print(f"  Unique precincts:       {df['precinct'].nunique()}")
print(f"  Unique offense types:   {df['offense_desc'].nunique()}")
print(f"  Law categories:         {df['law_category'].value_counts().to_dict()}")
print(f"\n  Output saved to:        {OUTPUT_PATH}")
print("\n  Top 10 offense types:")
print(df["offense_desc"].value_counts().head(10).to_string())