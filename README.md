# Safety in Urban Tourism — NYC

A data-science project analyzing NYC crime data to help tourists move through the
city more safely. The work is split into modules: a shared data-cleaning
foundation, a crime-zone clustering analysis, a safety-aware walking-route
finder, and a crime–tourism correlation analysis.

---

## 1. clean_data

This folder is the project's **data-foundation module**. It takes the raw NYPD
Complaint Data Historic dataset — a very large record of NYC crime complaints —
and transforms it into the clean, structured tables that every other part of the
project relies on. It runs as a four-step pipeline; the outputs (cleaned crime
records, per-precinct features, and verified attraction coordinates) are the
common input for the routing, clustering, and correlation analyses in the other
modules.

**Files**

- **`step1_filter.py`** — Loads and cleans the raw NYPD dataset. Keeps only the
  relevant columns; filters to pre- and post-COVID years (2018–2019 and
  2022–2023, excluding the 2020–2021 COVID period); parses dates and extracts the
  hour of each complaint; drops records with null, zero, or out-of-NYC
  coordinates (bounded to NYC's lat/lon range); removes rows missing a precinct,
  offense type, or law category; and standardizes column names and text fields.
  Prints a full before/after summary report. **Output:** `clean_nypd.csv`.

- **`step2_precinct_features.py`** — Aggregates the cleaned data into a
  per-precinct feature table. Computes total crime counts, law-category
  percentages (felony / misdemeanor / violation), offense-type percentages
  (theft, assault, drug, fraud, harassment via keyword flags), a night-crime
  ratio (10pm–6am), and crime density per km². Saves raw values for
  interpretation and normalizes the feature columns with a `StandardScaler` so
  they are ready for downstream clustering. **Input:** `clean_nypd.csv`.
  **Output:** `precinct_features.csv`.

- **`step3_base_map.py`** — Joins the precinct features to real NYC
  police-precinct boundaries (downloaded as GeoJSON) to compute accurate precinct
  areas and recomputed crime density per km². Renders a static choropleth of
  crime density and an interactive hover-enabled map. **Input:**
  `precinct_features.csv`. **Outputs:** `base_map.png`, `base_map.html`,
  `precinct_areas_real.csv`.

- **`step4_attractions.py`** — Compiles the coordinates of ten major NYC tourist
  attractions (Times Square, Central Park, Brooklyn Bridge, Empire State
  Building, and others), each manually verified on Google Maps, and builds a
  verification map with 500m tourist-zone buffer previews. **Outputs:**
  `attractions.csv`, `attractions_verify_map.html`.

- **`base_map.png` / `base_map.html`** — Generated choropleth maps of NYC crime
  density by police precinct (2018–2019 + 2022–2023); the `.html` version is
  interactive (hover a precinct for its stats).

- **`attractions_verify_map.html`** — Generated interactive map used to visually
  confirm each attraction pin and preview its 500m tourist zone.

- **`data_section.docx`** — Write-up of the data-cleaning section.

---

## 2. question_1_code

This folder contains the project's **crime-zone clustering module (Research
Question 1)**. It groups NYC police precincts into a small number of interpretable
"crime zones" based on their crime profile, so the rest of the project can reason
about areas by risk type rather than raw counts. It takes precinct-level crime
features, clusters them with KMeans, validates the result, and renders the zones
as maps. It is designed to run on the cleaned data from module 1, but can also
pull its own data directly from the NYC Open Data API.

**Files**

- **`fetch_data.py`** — Optional data source. Queries the NYC Open Data (Socrata)
  API for NYPD complaints in a recent window (2021 onward, so clusters reflect
  current patterns) and returns two aggregate tables: complaint counts by
  precinct × offense type, and by precinct × law category (felony / misdemeanor /
  violation). **Outputs:** `pct_offense.csv`, `pct_lawcat.csv` — used as a
  fallback input when a cleaned CSV isn't supplied.

- **`q1_pipeline.py`** — The full Q1 pipeline, run in one command. It auto-detects
  the crime columns (working with either the raw NYPD names or the team's cleaned
  names), streams the crime CSV in chunks, and builds a per-precinct feature table
  (total crime, crime per km² using real precinct areas from NYC Open Data
  boundaries, felony/misdemeanor percentages, and theft/assault/drug/fraud/
  harassment shares). It then normalizes the features with a `StandardScaler` and
  runs KMeans clustering into four crime zones, choosing k with an elbow +
  silhouette analysis. It validates the clusters internally (cohesion/SSE,
  centroid separation, silhouette scores, and a similarity-matrix heatmap),
  auto-names each zone by density and theft-vs-assault tilt (e.g. "Low-risk
  residential," "High-density theft / tourist core"), and produces both static and
  interactive choropleth maps of the zones. **Inputs:** a filtered NYPD complaint
  CSV via `--crime` (or the `fetch_data.py` API aggregates as a fallback).
  **Outputs:** `precinct_features.csv`, `elbow_curve.png`, `cluster_labels.csv`,
  `similarity_heatmap.png`, `q1_metrics.csv`, `crime_zones_map.png`, and
  `crime_zones_map.html`.

---

## 3. tourism-crime-corolation

This code analyzes crime patterns around tourist attractions in New York City by
creating geographic tourist zones and comparing crimes inside and outside these
areas. It uses GeoPandas to create 500-meter buffers around attractions and
spatially joins NYPD crime records to determine whether each incident occurred
within a tourist zone. The analysis compares crime rates per km² across different
crime categories, calculates Lift scores to identify offense types that are
disproportionately common near tourist areas, and applies a chi-squared test to
determine whether crime distributions differ significantly between tourist and
non-tourist zones. Finally, a sensitivity analysis compares Lift results across
250m, 500m, and 1000m radii to evaluate the robustness of the findings across
different spatial scales.

---

## 4. NYC Safe Walking Route Finder

This folder contains the project's routing and safety-analysis module, featuring
a Flask web app that provides NYC tourists with safety-optimized walking routes.
It allows users to instantly compare the standard shortest path against two
alternatives: an objective route avoiding NYPD crime hotspots (identified via
HDBSCAN clustering) and a subjective route bypassing areas flagged by
NLP-analyzed Airbnb reviews. The module integrates these precomputed hazard zones
into a routing layer (OpenRouteService/OSRM) to generate safe detours, and
includes a built-in evaluation suite to benchmark the models across tourist areas
based on distance overhead, hazard-avoidance rates, and latency.
