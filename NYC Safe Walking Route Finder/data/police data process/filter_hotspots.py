
import os
import pandas as pd

# -- Path Configurations --------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Input is the weighted file from the previous step
INPUT_CSV = os.path.join(SCRIPT_DIR, 'aggregated.csv')
OUTPUT_CSV = os.path.join(SCRIPT_DIR, 'filtered_hotspots_nypd.csv')


def main():
    # Check if the input file exists in the directory
    if not os.path.exists(INPUT_CSV):
        print(f"Error: The file '{INPUT_CSV}' was not found.")
        print("Please ensure the script is in the same folder as your weighted data file.")
        return

    print("Step 1: Loading weighted dataset...")
    df = pd.read_csv(INPUT_CSV)
    total_original_points = len(df)

    print("Step 2: Filtering out coordinates with a weight of 1...")
    # Keep only rows where the crime count (weight) is strictly greater than 1
    df_filtered = df[df['crime_count'] > 15].reset_index(drop=True)
    total_filtered_points = len(df_filtered)

    # -- Print Summary Statistics --------------------------------------------
    print("\n" + "=" * 50)
    print("                FILTERING SUMMARY")
    print("=" * 50)
    print(f"Total Unique Points (Before):     {total_original_points:,}")
    print(f"Points with Weight = 1 (Dropped):  {total_original_points - total_filtered_points:,}")
    print(f"Final Hotspot Points (After):     {total_filtered_points:,}")
    print("-" * 50)

    # Calculate point reduction percentage
    if total_original_points > 0:
        reduction = ((total_original_points - total_filtered_points) / total_original_points) * 100
        print(f"Total Coordinate Points Reduced By: {reduction:.2f}%")
    print("=" * 50 + "\n")

    print(f"Step 3: Saving filtered hotspots to:\n-> {OUTPUT_CSV}")
    # Save the cleaned file
    df_filtered.to_csv(OUTPUT_CSV, index=False)
    print("\nDone! All single-occurrence coordinates have been removed.")


if __name__ == '__main__':
    main()




INPUT_FILE = "filtered_hotspots_nypd.csv"
OUTPUT_FILE = "raw_crime_coordinates.csv"

print("--- Extracting and Renaming Crime Coordinates ---")

# 1. Load the dataset
print(f"Loading '{INPUT_FILE}'...")
df = pd.read_csv(INPUT_FILE)
initial_rows = len(df)
print(f"Total rows loaded: {initial_rows:,}")

# 2. Extract the original coordinate columns
df_coords = df[["latitude", "longitude"]].copy()

# 3. Rename the columns here (Change these strings to whatever names you want!)
df_coords.columns = ["latitude", "longitude"]

# 4. Save to a new CSV file
print(f"Saving renamed coordinates to '{OUTPUT_FILE}'...")
df_coords.to_csv(OUTPUT_FILE, index=False)

print("\n" + "=" * 40)
print("SUCCESS: Columns successfully renamed!")
print(f"New column names: {list(df_coords.columns)}")
print(f"Saved {len(df_coords)} rows to '{OUTPUT_FILE}'")
print("=" * 40)