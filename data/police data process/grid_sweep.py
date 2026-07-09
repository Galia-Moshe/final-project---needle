import os
import numpy as np
import pandas as pd
from sklearn.cluster import HDBSCAN

# טעינת הנתונים (מתוך הקובץ המעודכן שלך)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(SCRIPT_DIR, 'filtered_hotspots_nypd.csv')

if not os.path.exists(INPUT_CSV):
    raise FileNotFoundError(f"לא מצאתי את הקובץ {INPUT_CSV}. ודאי שהוא בתיקייה.")

df = pd.read_csv(INPUT_CSV).dropna(subset=['latitude', 'longitude'])

# הכנת הקואורדינטות (כולל התיקון הגיאוגרפי של ניו יורק מהקוד שלך)
lat = df['latitude'].to_numpy()
lon = df['longitude'].to_numpy()
mean_lat_rad = np.radians(lat.mean())
coords = np.column_stack([lat, lon * np.cos(mean_lat_rad)])

# ── הגדרת מרחב החיפוש (הערכים שנרצה לבדוק) ───────────────────
grid_min_cluster_size = [5, 8, 12, 15, 20]
grid_min_samples = [2, 5, 8, 12]

results = []

print("Running Grid Search over HDBSCAN parameters...")
print(f"Total input hotspot points to cluster: {len(df)}\n")

for m_size in grid_min_cluster_size:
    for m_samples in grid_min_samples:

        # הרצת האלגוריתם עבור השילוב הנוכחי
        clusterer = HDBSCAN(min_cluster_size=m_size, min_samples=m_samples)
        labels = clusterer.fit_predict(coords)

        # חישוב מדדים סטטיסטיים
        n_clusters = len(set(labels) - {-1})
        n_noise = int((labels == -1).sum())
        noise_percent = (n_noise / len(df)) * 100

        # חישוב גודל קלסטר ממוצע (כמה נקודות יש בכל קלסטר)
        if n_clusters > 0:
            cluster_sizes = pd.Series(labels)[labels != -1].value_counts()
            avg_cluster_size = cluster_sizes.mean()
            max_cluster_size = cluster_sizes.max()
        else:
            avg_cluster_size, max_cluster_size = 0, 0

        results.append({
            'MIN_CLUSTER_SIZE': m_size,
            'MIN_SAMPLES': m_samples,
            'Clusters Found': n_clusters,
            'Noise Points': n_noise,
            'Noise %': round(noise_percent, 1),
            'Avg Points/Cluster': round(avg_cluster_size, 1),
            'Max Points/Cluster': max_cluster_size
        })

# הצגת התוצאות בטבלה מסודרת
df_results = pd.DataFrame(results)
pd.set_option('display.max_rows', None)
pd.set_option('display.width', 1000)

print("\n=== HDBSCAN OPTIMIZATION REPORT ===")
print(df_results.to_string(index=False))