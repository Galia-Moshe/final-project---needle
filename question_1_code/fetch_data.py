import requests, pandas as pd

BASE = "https://data.cityofnewyork.us/resource/qgea-i56i.json"
# Recent window so clusters reflect current crime patterns (justified parameter choice)
WHERE = "cmplnt_fr_dt >= '2021-01-01T00:00:00' AND addr_pct_cd IS NOT NULL"

def soql(select, group):
    params = {"$select": select, "$where": WHERE, "$group": group, "$limit": 100000}
    r = requests.get(BASE, params=params, timeout=120)
    r.raise_for_status()
    return pd.DataFrame(r.json())

# A) precinct x offense-type counts
a = soql("addr_pct_cd, ofns_desc, count(1) AS n", "addr_pct_cd, ofns_desc")
a["n"] = a["n"].astype(int)
a.to_csv("pct_offense.csv", index=False)
print("offense rows:", len(a), "| precincts:", a.addr_pct_cd.nunique(), "| offense types:", a.ofns_desc.nunique())

# B) precinct x law category (felony/misdemeanor/violation)
b = soql("addr_pct_cd, law_cat_cd, count(1) AS n", "addr_pct_cd, law_cat_cd")
b["n"] = b["n"].astype(int)
b.to_csv("pct_lawcat.csv", index=False)
print("lawcat rows:", len(b))

print("total complaints in window:", a.n.sum())
