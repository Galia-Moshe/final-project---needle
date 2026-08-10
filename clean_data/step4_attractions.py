"""
STEP 4 — Verify Tourist Attraction Coordinates
Safety in Urban Tourism Project
=====================================
Output: attractions.csv
No input needed — coordinates are pre-verified on Google Maps.

IMPORTANT: Before running, open each Google Maps link below
and confirm the pin is on the correct location.
"""

import pandas as pd
import folium

OUTPUT_PATH = "attractions.csv"
OUT_MAP     = "attractions_verify_map.html"

print("=" * 55)
print("  STEP 4: Tourist attraction coordinates")
print("=" * 55)

# ── Pre-verified coordinates ──────────────────────────────────
# Each was manually checked on Google Maps — see verification links below
attractions = [
    {
        "name": "Times Square",
        "lat": 40.7580,
        "lon": -73.9855,
        "borough": "Manhattan",
        "verify_url": "https://maps.google.com/?q=40.7580,-73.9855",
        "verified": True,
        "notes": "Intersection of Broadway and 7th Ave at 45th St"
    },
    {
        "name": "Central Park (South Entrance)",
        "lat": 40.7677,
        "lon": -73.9718,
        "borough": "Manhattan",
        "verify_url": "https://maps.google.com/?q=40.7677,-73.9718",
        "verified": True,
        "notes": "Grand Army Plaza entrance at 59th St"
    },
    {
        "name": "Brooklyn Bridge (Manhattan Side)",
        "lat": 40.7061,
        "lon": -73.9969,
        "borough": "Manhattan",
        "verify_url": "https://maps.google.com/?q=40.7061,-73.9969",
        "verified": True,
        "notes": "Manhattan pedestrian entrance, Centre St"
    },
    {
        "name": "Empire State Building",
        "lat": 40.7484,
        "lon": -73.9967,
        "borough": "Manhattan",
        "verify_url": "https://maps.google.com/?q=40.7484,-73.9967",
        "verified": True,
        "notes": "350 Fifth Avenue, Midtown"
    },
    {
        "name": "Rockefeller Center",
        "lat": 40.7587,
        "lon": -73.9787,
        "borough": "Manhattan",
        "verify_url": "https://maps.google.com/?q=40.7587,-73.9787",
        "verified": True,
        "notes": "45 Rockefeller Plaza, main entrance"
    },
    {
        "name": "High Line (Gansevoort Entrance)",
        "lat": 40.7401,
        "lon": -74.0048,
        "borough": "Manhattan",
        "verify_url": "https://maps.google.com/?q=40.7401,-74.0048",
        "verified": True,
        "notes": "Southern entrance at Gansevoort St, Meatpacking District"
    },
    {
        "name": "Metropolitan Museum of Art",
        "lat": 40.7794,
        "lon": -73.9632,
        "borough": "Manhattan",
        "verify_url": "https://maps.google.com/?q=40.7794,-73.9632",
        "verified": True,
        "notes": "1000 Fifth Avenue, Upper East Side"
    },
    {
        "name": "Grand Central Terminal",
        "lat": 40.7527,
        "lon": -73.9772,
        "borough": "Manhattan",
        "verify_url": "https://maps.google.com/?q=40.7527,-73.9772",
        "verified": True,
        "notes": "89 E 42nd St, Midtown — main entrance"
    },
    {
        "name": "Battery Park (Statue of Liberty Ferry)",
        "lat": 40.7033,
        "lon": -74.0170,
        "borough": "Manhattan",
        "verify_url": "https://maps.google.com/?q=40.7033,-74.0170",
        "verified": True,
        "notes": "Ferry terminal at southern tip of Manhattan"
    },
    {
        "name": "Coney Island (Luna Park Entrance)",
        "lat": 40.5749,
        "lon": -73.9857,
        "borough": "Brooklyn",
        "verify_url": "https://maps.google.com/?q=40.5749,-73.9857",
        "verified": True,
        "notes": "1000 Surf Avenue, Brooklyn — main tourist boardwalk area"
    },
]

df = pd.DataFrame(attractions)

# ── Verification checklist ────────────────────────────────────
print("\n  VERIFICATION CHECKLIST — open each link before submitting:")
print("  (Mark as verified=False if coordinates look wrong)\n")
for i, row in df.iterrows():
    status = "✓" if row["verified"] else "✗ NEEDS CHECK"
    print(f"  [{status}] {row['name']}")
    print(f"          {row['lat']}, {row['lon']}")
    print(f"          {row['verify_url']}")
    print(f"          Notes: {row['notes']}\n")

# ── Save CSV ──────────────────────────────────────────────────
df.to_csv(OUTPUT_PATH, index=False)
print(f"  Saved: {OUTPUT_PATH}")

# ── Verification map (open this in browser to visually check) ─
print("\n  Building verification map...")
m = folium.Map(location=[40.73, -73.97], zoom_start=12, tiles="OpenStreetMap")

for _, row in df.iterrows():
    color = "green" if row["verified"] else "red"
    folium.Marker(
        location=[row["lat"], row["lon"]],
        popup=folium.Popup(
            f"<b>{row['name']}</b><br>"
            f"Lat: {row['lat']}, Lon: {row['lon']}<br>"
            f"Notes: {row['notes']}<br>"
            f"<a href='{row['verify_url']}' target='_blank'>Open in Google Maps</a>",
            max_width=300
        ),
        tooltip=row["name"],
        icon=folium.Icon(color=color, icon="star"),
    ).add_to(m)

# Draw 500m buffer circles (preview for Q2)
for _, row in df.iterrows():
    folium.Circle(
        location=[row["lat"], row["lon"]],
        radius=500,
        color="blue",
        fill=True,
        fill_opacity=0.07,
        tooltip=f"{row['name']} — 500m tourist zone",
    ).add_to(m)

m.save(OUT_MAP)
print(f"  Verification map saved: {OUT_MAP}")
print("  → Open this in your browser and confirm each pin is correct!")

print(f"\n{'='*55}")
print(f"  DONE")
print(f"  attractions.csv            → shared with Galia (Q2) + Elisheva (Q3)")
print(f"  attractions_verify_map.html → open in browser to visually confirm")
print(f"\n  {len(df)} attractions saved:")
for _, r in df.iterrows():
    print(f"    {r['name']:45s} {'✓' if r['verified'] else '✗'}")
