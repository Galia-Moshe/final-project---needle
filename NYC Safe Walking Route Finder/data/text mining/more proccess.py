import pandas as pd

INPUT_FILE = "processed_safety_reviews.csv"
OUTPUT_FILE = "high_risk_safety_coordinates.csv"

print("--- Extracting Coordinates Only ---")

# 1. Load the dataset
print(f"Loading '{INPUT_FILE}'...")
df = pd.read_csv(INPUT_FILE)
initial_rows = len(df)

# 2. Filter for unsafe reviews only (is_unsafe == 1)
df_unsafe = df[df["is_unsafe"] == 1]
print(f"Found {len(df_unsafe)} unsafe reviews.")

# 3. Keep ONLY latitude and longitude
df_coords = df_unsafe[["latitude", "longitude"]].copy()

# 4. Drop duplicates to get unique geographic points
df_unique_coords = df_coords.drop_duplicates()
final_points_count = len(df_unique_coords)

# 5. Export to CSV
df_unique_coords.to_csv(OUTPUT_FILE, index=False)

# Print Summary Statistics
print("\n" + "="*50)
print("EXTRACTION COMPLETE - SUMMARY STATISTICS")
print("="*50)
print(f"Total Unsafe Reviews:         {len(df_unsafe):,}")
print(f"Unique Coordinates Extracted: {final_points_count:,}")
print(f"Saved clean coordinates to:   '{OUTPUT_FILE}'")
print("="*50)