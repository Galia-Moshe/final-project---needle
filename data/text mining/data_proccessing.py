import pandas as pd

# 1. Define file paths (Change these to your actual file names)
hotels_file = "listings.csv"
reviews_file = "reviews_detailed.csv"
output_file = "merged_dataset.csv"

print("Step 1: Loading the files...")
df_hotels = pd.read_csv(hotels_file)
df_reviews = pd.read_csv(reviews_file)

print("Step 2: Merging the tables with different ID column names...")
# df_reviews (left table) uses 'listing_id'
# df_hotels (right table) uses 'id'
df_merged = pd.merge(
    df_reviews,
    df_hotels,
    left_on="listing_id",
    right_on="id",
    how="inner"
)

print("Step 3: Filtering the dataset to keep only the requested columns...")
# List of columns you specified to keep
columns_to_keep = [
    "listing_id",
    "date",
    "reviewer_id",
    "comments",
    "name",
    "neighbourhood_group",
    "neighbourhood",
    "latitude",
    "longitude"
]

# Keep only the specified columns from the merged dataframe
df_final = df_merged[columns_to_keep]

print(f"Step 4: Saving the filtered dataset to '{output_file}'...")
# Save the final dataset to a new CSV file
df_final.to_csv(output_file, index=False, encoding="utf-8")

print("Success! The dataset has been merged and filtered to your exact columns.")