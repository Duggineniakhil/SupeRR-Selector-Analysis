"""Exploratory (T10 follow-up): which half-A estimator best predicts half-B pressure value?
Aggregate correlations only; no player names."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np, pandas as pd
import player_metrics as pm
from common import load_config, path
cfg = load_config(); I = path(cfg, "interim")
d = pd.read_parquet(I / "rating_balls.parquet")
d["rec"] = pm.recency(d.match_date, cfg["reference_date"], cfg["metrics"]["recency_half_life_years"])
kap = cfg["metrics"]["tier_credibility_fallback"]; rng = np.random.default_rng(1)
mids = d.match_id.unique()
res = {"bat": [], "bowl": []}
for _ in range(20):
    h = set(rng.choice(mids, len(mids)//2, replace=False)); m = d.match_id.isin(h)
    for kind, fn, v, n, extra in (("bat", pm.batting, "rv", "balls_P", ["rae_P", "dae_P"]),
                                  ("bowl", pm.bowling, "bv", "legal_P", ["rs_P", "wae_P"])):
        A, B = fn(d[m], kap, cfg), fn(d[~m], kap, cfg)
        ids = A.index[A[n] >= 60].intersection(B.index[B[n] >= 60])
        A, B = A.loc[ids], B.loc[ids]
        allv = (A[f"{v}_P"]*A.eff_n_P + A[f"{v}_N"]*A.eff_n_N.fillna(0)) / (A.eff_n_P + A.eff_n_N.fillna(0))
        y = B[f"{v}_P"]
        row = {"A_pressure_value": A[f"{v}_P"].corr(y), "A_nonpressure_value": A[f"{v}_N"].corr(y),
               "A_all_balls_value": allv.corr(y), "A_pressure_WPA": A.wpa_per100_P.corr(y)}
        for e in extra: row[f"{e}_halfA_vs_halfB"] = A[e].corr(B[e])
        row["n"] = len(ids); res[kind].append(row)
for k, r in res.items():
    print(k); print(pd.DataFrame(r).mean().round(3).to_string())
