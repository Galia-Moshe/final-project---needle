import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(SCRIPT_DIR, 'aggregated.csv')

# Check if the input file exists in the directory

print("Step 1: Loading weighted dataset...")
df = pd.read_csv(INPUT_CSV)

# Assuming your DataFrame is named 'df' with a column representing crime count (weight)
# Change 'crime_count' to match your actual column name
column_name = 'crime_count'

# 1. Calculate and print percentiles
print("--- Crime Distribution per Coordinate Analysis ---")
percentiles = [0.5, 0.75, 0.80, 0.90, 0.95, 0.99]
quantiles = df[column_name].quantile(percentiles)

for p, val in zip(percentiles, quantiles):
    print(f"{int(p*100)}th Percentile: {val} crimes "
          f"({int(p*100)}% of coordinates have {val} or fewer crimes over 4 years)")

# 2. Setup plots
sns.set_theme(style="whitegrid")
plt.figure(figsize=(14, 6))

# Cap the plot at the 99th percentile so extreme outliers (like Times Square) don't distort the scale
max_val_for_plot = df[column_name].quantile(0.99)

# Plot 1: Histogram (to see the long tail)
plt.subplot(1, 2, 1)
sns.histplot(df[df[column_name] <= max_val_for_plot][column_name], bins=30, kde=False, color='purple')
plt.title('Crime Count Distribution (Histogram)')
plt.xlabel('Crime Count per Coordinate (Weight)')
plt.ylabel('Number of Coordinates')

# Plot 2: Empirical Cumulative Distribution Function (ECDF)
plt.subplot(1, 2, 2)
sns.ecdfplot(data=df[df[column_name] <= max_val_for_plot], x=column_name, color='red', linewidth=2)
plt.title('Empirical Cumulative Distribution Function (ECDF)')
plt.xlabel('Crime Count per Coordinate (Weight)')
plt.ylabel('Cumulative Percentage of Coordinates')

# Add reference lines for key percentiles
p90_val = df[column_name].quantile(0.90)
p95_val = df[column_name].quantile(0.95)

plt.axhline(0.90, color='gray', linestyle='--', alpha=0.7)
plt.axvline(p90_val, color='gray', linestyle='--', alpha=0.7, label=f'90th Percentile ({p90_val})')

plt.axhline(0.95, color='black', linestyle=':', alpha=0.7)
plt.axvline(p95_val, color='black', linestyle=':', alpha=0.7, label=f'95th Percentile ({p95_val})')

plt.legend()
plt.tight_layout()
plt.show()