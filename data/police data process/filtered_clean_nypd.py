import os
import pandas as pd

# -- Path Configurations --------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(SCRIPT_DIR, 'clean_nypd.csv')
OUTPUT_CSV = os.path.join(SCRIPT_DIR, 'aggregated.csv')

# -- Years to Include -----------------------------------------------------
TARGET_YEARS = [2018, 2019, 2022, 2023]

# -- Tourist Relevant Crime Types (Pickpocketing, assaults, robberies) ----
TOURIST_CRIMES = [
    'HARRASSMENT 2',
    'ROBBERY',
    'FELONY ASSAULT',
    'ASSAULT 3 & RELATED OFFENSES',
    'DANGEROUS WEAPONS',
    'SEX CRIMES',
    'RAPE',
    'MURDER & NON-NEGL. MANSLAUGHTER',
    'GRAND LARCENY',
    'FELONY SEX CRIMES',
]

# -- Tourist-Relevant / Public Space Location Types to Keep -------------
INCLUDED_PREMISES = [
    # Transit, Infrastructure & Streets (High tourist movement)
    'STREET', 'HIGHWAY/PARKWAY', 'TRANSIT - NYC SUBWAY', 'TRANSIT FACILITY (OTHER)',
    'BUS (NYC TRANSIT)', 'BUS (OTHER)', 'BUS STOP', 'BUS TERMINAL',
    'AIRPORT TERMINAL', 'FERRY/FERRY TERMINAL', 'BRIDGE', 'TUNNEL', 'TRAMWAY',
    'TAXI (YELLOW LICENSED)', 'TAXI (LIVERY LICENSED)', 'TAXI/LIVERY (UNLICENSED)',
    'PARKING LOT/GARAGE (PUBLIC)',

    # Public Spaces, Entertainment & Leisure
    'PARK/PLAYGROUND', 'MARINA/PIER', 'PUBLIC BUILDING',
    'BAR/NIGHT CLUB', 'RESTAURANT/DINER', 'FAST FOOD', 'HOTEL/MOTEL',

    # Shopping & Retail (Common targets for pickpocketing/street crimes)
    'CHAIN STORE', 'DEPARTMENT STORE', 'CLOTHING/BOUTIQUE', 'SHOE', 'SHOE STORE',
    'GROCERY/BODEGA', 'SUPERMARKET', 'FOOD SUPERMARKET', 'DRUG STORE', 'SMOKE SHOP',
    'TELECOMM. STORE', 'SMALL MERCHANT', 'MOBILE FOOD', 'BOOK/CARD', 'STORE UNCLASSIFIED',

    # Financial Interaction Points
    'ATM'
]


def main():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: The file '{INPUT_CSV}' was not found.")
        print("Please place this script in the same folder as your 'clean_nypd.csv' file.")
        return

    print("Step 1: Loading original dataset (this might take a few moments)...")
    df = pd.read_csv(INPUT_CSV)
    total_original = len(df)

    print("Step 2: Removing rows with missing coordinates (lat/lon)...")
    df = df.dropna(subset=['lat', 'lon'])
    total_after_geo = len(df)

    print(f"Step 3: Filtering for years {TARGET_YEARS}...")
    df['year'] = df['year'].astype(int)
    df = df[df['year'].isin(TARGET_YEARS)]
    total_after_years = len(df)

    print("Step 4: Filtering for tourist-relevant crime types...")
    df = df[df['offense_desc'].isin(TOURIST_CRIMES)]
    total_after_crimes = len(df)

    print("Step 5: Filtering for location types...")
    # Normalize text to upper case and strip whitespace to ensure precise matching
    df_filtered = df[df['premise_type'].isin(INCLUDED_PREMISES)]
    total_final = len(df_filtered)

    print("Step 5: Aggregating unique coordinates and counting crime density...")
    # Group by lat/lon, count occurrences, and reset index to create a dataframe
    df_aggregated = df_filtered.groupby(['lat', 'lon']).size().reset_index(name='crime_count')

    # Rename columns to standard mapping format
    df_aggregated = df_aggregated.rename(columns={'lat': 'latitude', 'lon': 'longitude'})
    total_final_points = len(df_aggregated)

    print("\n" + "=" * 50)
    print("                FILTERING SUMMARY")
    print("=" * 50)
    print(f"Original Dataset Rows:   {total_original:,}")
    print(f"1. After Geo Cleaning:   {total_after_geo:,}  (Dropped {total_original - total_after_geo:,} empty coordinates)")
    print(f"2. After Year Filter:    {total_after_years:,}  (Dropped {total_after_geo - total_after_years:,} rows not from 2022/2023)")
    print(f"3. After Crime Filter:   {total_after_crimes:,}  (Dropped {total_after_years - total_after_crimes:,} irrelevant crime types)")
    print(f"4. After Premise Filter: {total_final:,}  (Dropped {total_after_crimes - total_final:,} domestic/local premises)")
    print("-" * 50)
    print(f"Final Filtered Rows:     {total_final:,}")
    reduction = ((total_original - total_final) / total_original) * 100
    print(f"Total Dataset Reduced By: {reduction:.2f}%")
    print("=" * 50 + "\n")

    print(f"Step 6: Saving new filtered dataset to:\n-> {OUTPUT_CSV}")
    df_aggregated.to_csv(OUTPUT_CSV, index=False)
    print("\nDone! Your clean, tourist-centric spatial data is ready for analysis.")


if __name__ == '__main__':
    main()