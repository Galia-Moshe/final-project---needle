"""
============================================================================
Q1  -  CRIME ZONE MAPPING & CLUSTERING  -  full pipeline (run once)
============================================================================
Reads a (filtered) NYPD complaint CSV and produces EVERYTHING Q1 needs:

    precinct_features.csv    one row per precinct, raw + the table Q2/Q3 reuse
    elbow_curve.png          KMeans inertia/silhouette for k = 2..8  (justify k)
    cluster_labels.csv       precinct -> cluster_id, cluster_name
    similarity_heatmap.png   internal validation (cohesive clusters = bright blocks)
    q1_metrics.csv           cohesion / separation / silhouette per cluster
    crime_zones_map.png      static choropleth of the 4 crime zones
    crime_zones_map.html     interactive folium map (the demo / shared base map)

The script does NOT filter dates or drop bad coordinates - that is the data
cleaning step (Person 1). It uses whatever rows are in the CSV you give it,
and only needs three columns: precinct, offense description, law category.
Column names are auto-detected (works with raw NYPD names like ADDR_PCT_CD
or the team's clean names like 'precinct').

USAGE
    python3 q1_pipeline.py --crime  path/to/your_filtered_complaints.csv
    # no --crime?  it falls back to pct_offense.csv + pct_lawcat.csv if present
    # (those are API aggregates produced by fetch_data.py)

REQUIREMENTS
    pip install pandas numpy scikit-learn matplotlib folium
    (folium is only needed for the .html map; the rest still runs without it)
============================================================================
"""
import argparse, json, os, sys, urllib.request
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPoly, Patch
from matplotlib.collections import PatchCollection
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, silhouette_samples

# ---- configuration ---------------------------------------------------------
RANDOM_STATE = 42
K            = 4                       # final #clusters (justified by the elbow)
SQFT_TO_KM2  = 9.290304e-8
GEOJSON_URL  = ("https://data.cityofnewyork.us/api/geospatial/"
                "y76i-bdw7?method=export&format=GeoJSON")

# The 5 crime families we track, mapped to substrings of the offense description.
# Substring matching is robust to NYPD's odd spellings (e.g. "HARRASSMENT").
# >>> To change the feature set, edit this dict (and FEATURES below). <<<
FAMILIES = {
    "theft":      ["LARCENY"],
    "assault":    ["ASSAULT"],
    "drug":       ["DRUG"],
    "fraud":      ["FRAUD", "FORGERY"],
    "harassment": ["HARRASSMENT", "HARASSMENT"],
}
FEATURES = ["total_crime", "crime_per_km2", "felony_pct", "misdemeanor_pct",
            "theft_pct", "assault_pct", "drug_pct", "fraud_pct", "harassment_pct"]

# candidate column names (lower-cased) for auto-detection
COLCANDS = {
    "precinct": ["addr_pct_cd", "precinct", "pct", "addr_pct"],
    "offense":  ["ofns_desc", "offense_desc", "offense", "ofns"],
    "lawcat":   ["law_cat_cd", "law_category", "law_cat", "lawcat"],
}


# ---- 1. read the crime data ------------------------------------------------
def family_of(offense_series):
    """Vectorised map: offense description -> crime family ('other' by default)."""
    fam = pd.Series("other", index=offense_series.index)
    s = offense_series.astype(str)
    for name, keys in FAMILIES.items():
        fam[s.str.contains("|".join(keys), case=False, na=False)] = name
    return fam


def detect_columns(header):
    low = {c.lower(): c for c in header}
    found = {}
    for role, cands in COLCANDS.items():
        hit = next((low[c] for c in cands if c in low), None)
        if hit is None:
            sys.exit(f"ERROR: could not find a '{role}' column. "
                     f"Looked for {cands}. Your columns: {list(header)}")
        found[role] = hit
    return found


def aggregate_from_raw(path):
    """Stream a (possibly huge) crime CSV in chunks -> family/lawcat counts."""
    header = pd.read_csv(path, nrows=0).columns
    col = detect_columns(header)
    print(f"Detected columns: {col}")
    use = [col["precinct"], col["offense"], col["lawcat"]]
    off_acc = law_acc = None
    n_rows = n_dropped = 0
    for chunk in pd.read_csv(path, usecols=use, dtype=str, chunksize=500_000):
        n_rows += len(chunk)
        chunk["_p"] = pd.to_numeric(chunk[col["precinct"]], errors="coerce")
        bad = chunk["_p"].isna(); n_dropped += int(bad.sum())
        chunk = chunk[~bad]; chunk["_p"] = chunk["_p"].astype(int)
        chunk["_fam"] = family_of(chunk[col["offense"]])
        o = chunk.groupby(["_p", "_fam"]).size()
        l = chunk.groupby(["_p", chunk[col["lawcat"]].str.upper()]).size()
        off_acc = o if off_acc is None else off_acc.add(o, fill_value=0)
        law_acc = l if law_acc is None else law_acc.add(l, fill_value=0)
    print(f"Rows read: {n_rows:,} | dropped (bad precinct): {n_dropped:,}")
    off = off_acc.rename("n").reset_index().rename(columns={"_p": "precinct", "_fam": "family"})
    law = law_acc.rename("n").reset_index()
    law.columns = ["precinct", "law_cat", "n"]
    return off, law


def aggregate_from_api_files():
    """Fallback: use pct_offense.csv + pct_lawcat.csv (from fetch_data.py)."""
    o = pd.read_csv("pct_offense.csv"); o["precinct"] = o.addr_pct_cd.astype(int)
    o["family"] = family_of(o.ofns_desc)
    off = o.groupby(["precinct", "family"])["n"].sum().reset_index()
    l = pd.read_csv("pct_lawcat.csv"); l["precinct"] = l.addr_pct_cd.astype(int)
    law = l.rename(columns={"law_cat_cd": "law_cat"})[["precinct", "law_cat", "n"]]
    print("Using API aggregates (pct_offense.csv, pct_lawcat.csv)")
    return off, law


# ---- 2. precinct boundaries + feature table --------------------------------
def ensure_geojson(path="precincts.geojson"):
    if not os.path.exists(path):
        print("Downloading precinct boundaries ...")
        try:
            urllib.request.urlretrieve(GEOJSON_URL, path)
        except Exception as e:
            sys.exit(f"ERROR downloading GeoJSON ({e}). Download it manually from "
                     f"NYC Open Data ('Police Precincts', y76i-bdw7) as {path}.")
    return json.load(open(path))


def build_features(off, law, geo):
    area = {int(f["properties"]["precinct"]): float(f["properties"]["shape_area"]) * SQFT_TO_KM2
            for f in geo["features"]}
    total = off.groupby("precinct")["n"].sum().rename("total_crime")
    fam = off.pivot_table(index="precinct", columns="family", values="n",
                          aggfunc="sum", fill_value=0)
    pct = fam.div(total, axis=0) * 100
    for f in FAMILIES:                       # ensure all family columns exist
        if f not in pct: pct[f] = 0.0
    lp = law.pivot_table(index="precinct", columns="law_cat", values="n",
                         aggfunc="sum", fill_value=0)
    lp_pct = lp.div(lp.sum(axis=1), axis=0) * 100
    feats = pd.DataFrame({
        "total_crime":     total,
        "crime_per_km2":   pd.Series({p: total[p] / area[p] for p in total.index if p in area}),
        "felony_pct":      lp_pct.get("FELONY", 0),
        "misdemeanor_pct": lp_pct.get("MISDEMEANOR", 0),
        "theft_pct":       pct["theft"], "assault_pct": pct["assault"],
        "drug_pct":        pct["drug"],  "fraud_pct":   pct["fraud"],
        "harassment_pct":  pct["harassment"],
    }).dropna()
    feats.index.name = "precinct"
    feats.to_csv("precinct_features.csv")
    print(f"\nprecinct_features.csv: {len(feats)} precincts, {len(FEATURES)} features")
    print("QA - look at your data:")
    print(f"  total complaints aggregated: {int(total.sum()):,}")
    print(f"  busiest precinct: {int(total.idxmax())} ({int(total.max()):,})  |  "
          f"quietest: {int(total.idxmin())} ({int(total.min()):,})")
    return feats


# ---- 3. clustering + internal validation -----------------------------------
def cluster_and_validate(feats):
    X = StandardScaler().fit_transform(feats[FEATURES].values)

    # elbow + silhouette over k = 2..8
    ks, inertia, sil = range(2, 9), [], []
    for k in ks:
        km = KMeans(n_clusters=k, init="k-means++", n_init=10, random_state=RANDOM_STATE).fit(X)
        inertia.append(km.inertia_); sil.append(silhouette_score(X, km.labels_))
    fig, a1 = plt.subplots(figsize=(7, 4.3))
    a1.plot(ks, inertia, "o-", color="#1f77b4"); a1.set_xlabel("k"); a1.set_ylabel("inertia (SSE)", color="#1f77b4")
    a1.axvline(K, color="red", ls="--", alpha=.6); a1.set_title("Elbow & silhouette (KMeans, k=2..8)")
    a2 = a1.twinx(); a2.plot(ks, sil, "s--", color="green", alpha=.7); a2.set_ylabel("silhouette", color="green")
    fig.tight_layout(); fig.savefig("elbow_curve.png", dpi=140); plt.close()

    # final model
    km = KMeans(n_clusters=K, init="k-means++", n_init=10, random_state=RANDOM_STATE).fit(X)
    lab, cen = km.labels_, km.cluster_centers_

    # cohesion / separation / silhouette
    sse = {c: float(((X[lab == c] - cen[c]) ** 2).sum()) for c in range(K)}
    cd = np.sqrt(((cen[:, None] - cen[None]) ** 2).sum(-1))
    sil_s = silhouette_samples(X, lab)

    # similarity-matrix heatmap (ordered by cluster) + r_AD
    D = np.sqrt(((X[:, None] - X[None]) ** 2).sum(-1)); sigma = np.median(D[D > 0])
    S = np.exp(-(D ** 2) / (2 * sigma ** 2)); order = np.argsort(lab)
    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    im = ax.imshow(S[np.ix_(order, order)], cmap="viridis")
    for b in np.cumsum([np.sum(lab == c) for c in range(K)])[:-1]:
        ax.axhline(b - .5, color="white", lw=.8); ax.axvline(b - .5, color="white", lw=.8)
    ax.set_title("Similarity matrix (ordered by cluster)\nbright diagonal blocks = cohesive clusters")
    plt.colorbar(im, label="similarity"); plt.tight_layout()
    plt.savefig("similarity_heatmap.png", dpi=140); plt.close()
    ideal = (lab[:, None] == lab[None]).astype(float); iu = np.triu_indices(len(X), 1)
    r_AD = float(np.corrcoef(S[iu], ideal[iu])[0, 1])

    # name clusters by density, refine the two densest by theft-vs-assault
    feats = feats.copy(); feats["cluster"] = lab
    means = feats.groupby("cluster")[FEATURES].mean()
    by_dens = means["crime_per_km2"].sort_values().index.tolist()
    name = {by_dens[0]: "Low-risk residential", by_dens[1]: "Moderate mixed"}
    city = feats[FEATURES].mean()
    for c in by_dens[2:]:
        over = means.loc[c, ["theft_pct", "assault_pct"]] - city[["theft_pct", "assault_pct"]]
        name[c] = ("High-density (theft / tourist core)"
                   if over["theft_pct"] >= over["assault_pct"] else "High-density (violence-leaning)")
    feats["cluster_name"] = feats.cluster.map(name)

    feats.reset_index()[["precinct", "cluster", "cluster_name"]] \
        .rename(columns={"cluster": "cluster_id"}).to_csv("cluster_labels.csv", index=False)
    pd.DataFrame([{"cluster_id": c, "name": name[c], "n_precincts": int((lab == c).sum()),
                   "SSE_cohesion": round(sse[c], 1),
                   "mean_silhouette": round(float(sil_s[lab == c].mean()), 3),
                   "mean_crime_per_km2": round(float(means.loc[c, "crime_per_km2"]))}
                  for c in range(K)]).to_csv("q1_metrics.csv", index=False)

    print("\n===== Q1 internal validation (k=4) =====")
    print(f"total SSE (cohesion): {sum(sse.values()):.1f} | "
          f"mean centroid separation: {cd[np.triu_indices(K,1)].mean():.2f} | "
          f"overall silhouette: {silhouette_score(X, lab):.3f} | r_AD: {r_AD:.3f}")
    print("\nPer-cluster mean features  (VERIFY & RENAME the auto-labels!):")
    print(means.round(1).assign(name=[name[c] for c in means.index]).to_string())
    return feats, name


# ---- 4. choropleth maps ----------------------------------------------------
def make_maps(feats, geo):
    RAMP = {"Low-risk residential": "#1a9850", "Moderate mixed": "#fee08b",
            "High-density (violence-leaning)": "#fc8d59",
            "High-density (theft / tourist core)": "#d73027"}
    cname = feats.set_index(feats.index)["cluster_name"].to_dict()

    # static PNG
    def rings(g):
        if g["type"] == "Polygon": yield g["coordinates"][0]
        else:
            for poly in g["coordinates"]: yield poly[0]
    fig, ax = plt.subplots(figsize=(8, 9)); patches, colors = [], []
    for f in geo["features"]:
        p = int(f["properties"]["precinct"])
        for ring in rings(f["geometry"]):
            patches.append(MplPoly(np.array(ring)[:, :2]))
            colors.append(RAMP.get(cname.get(p), "#cccccc"))
    ax.add_collection(PatchCollection(patches, facecolor=colors, edgecolor="white", linewidth=.4))
    ax.autoscale(); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title("NYC Crime Zones by Precinct (KMeans, k=4)")
    ax.legend(handles=[Patch(facecolor=c, label=n) for n, c in RAMP.items()],
              loc="upper left", fontsize=8)
    plt.tight_layout(); plt.savefig("crime_zones_map.png", dpi=140, bbox_inches="tight"); plt.close()

    # interactive HTML
    try:
        import folium
    except ImportError:
        print("\n(folium not installed -> skipped crime_zones_map.html; `pip install folium`)")
        return
    m = folium.Map(location=[40.73, -73.95], zoom_start=11, tiles="cartodbpositron")
    fd = feats.to_dict("index")
    for f in geo["features"]:
        p = int(f["properties"]["precinct"])
        if p in fd:
            r = fd[p]
            folium.GeoJson(
                f, style_function=lambda x, col=RAMP.get(cname.get(p), "#ccc"):
                    {"fillColor": col, "color": "white", "weight": 1, "fillOpacity": .7},
                tooltip=folium.Tooltip(
                    f"<b>Precinct {p}</b><br>{r['cluster_name']}<br>"
                    f"Density: {r['crime_per_km2']:,.0f}/km²<br>Theft: {r['theft_pct']:.0f}%")
            ).add_to(m)
    m.save("crime_zones_map.html")
    print("Saved crime_zones_map.html")


# ---- main ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crime", help="path to the filtered NYPD complaint CSV")
    ap.add_argument("--geojson", default="precincts.geojson")
    args = ap.parse_args()

    if args.crime:
        off, law = aggregate_from_raw(args.crime)
    elif os.path.exists("pct_offense.csv") and os.path.exists("pct_lawcat.csv"):
        off, law = aggregate_from_api_files()
    else:
        sys.exit("Provide --crime path/to/filtered.csv  (or run fetch_data.py first).")

    geo = ensure_geojson(args.geojson)
    feats = build_features(off, law, geo)
    feats, _ = cluster_and_validate(feats)
    make_maps(feats, geo)
    print("\nDONE. Outputs: precinct_features.csv, elbow_curve.png, cluster_labels.csv,"
          " similarity_heatmap.png, q1_metrics.csv, crime_zones_map.png/.html")


if __name__ == "__main__":
    main()
