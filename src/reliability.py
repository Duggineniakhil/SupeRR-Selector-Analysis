"""T10 — Reliability of pressure metrics (planning/04 §8, §10.3; planning/08 §2.3).

1. Split-half reliability: matches are randomly split in two (R times); metrics are recomputed
   on each half with the same weights; Pearson r across players with enough pressure balls in
   both halves; full-sample reliability by Spearman-Brown, 2r / (1 + r).
2. Season-to-season stability: correlation of per-season pressure value for players with
   enough pressure balls in consecutive seasons (Fisher-z pooled).
3. Variance decomposition → stabilisation point n* = σ²_ball / τ² (balls at which the observed
   per-ball value is 50% signal), used for shrinkage (T11) and eligibility.
4. Applies the pre-registered weight and eligibility rules from config.yaml.

Outputs: data_interim/reliability.pkl, outputs/validation/reliability.md
"""
from __future__ import annotations

import pickle

import numpy as np
import pandas as pd

import player_metrics as pm
from common import load_config, md_table, path

BAT_COMP = {"performance": "rv_P", "wpa": "wpa_per100_P", "differential": "delta_rv", "consistency": "consistency"}
BOWL_COMP = {"performance": "bv_P", "wpa": "wpa_per100_P", "differential": "delta_bv", "consistency": "consistency"}
BAT_EXTRA = ["rv_N", "sr_P", "dot_pct_P", "bnd_pct_P"]
BOWL_EXTRA = ["bv_N", "econ_P", "dot_pct_P", "bnd_pct_P"]


def sb(r: float) -> float:
    return 2 * r / (1 + r) if r > -1 else np.nan


def split_half(d, kappa, cfg, kind):
    rc = cfg["reliability"]
    rng = np.random.default_rng(cfg["pressure"]["seed"])
    mids = d.match_id.unique()
    comp = BAT_COMP if kind == "bat" else BOWL_COMP
    cols = list(comp.values()) + (BAT_EXTRA if kind == "bat" else BOWL_EXTRA)
    nmin = rc["min_half_bat_pressure_balls"] if kind == "bat" else rc["min_half_bowl_pressure_legal"]
    ncol = "balls_P" if kind == "bat" else "legal_P"
    fn = pm.batting if kind == "bat" else pm.bowling
    rs, ns = {c: [] for c in cols}, []
    for _ in range(rc["random_splits"]):
        half = set(rng.choice(mids, len(mids) // 2, replace=False))
        m = d.match_id.isin(half)
        a, b = fn(d[m], kappa, cfg), fn(d[~m], kappa, cfg)
        ok = (a[ncol] >= nmin).reindex(a.index.union(b.index), fill_value=False) & \
             (b[ncol] >= nmin).reindex(a.index.union(b.index), fill_value=False)
        ids = ok[ok].index
        ns.append(len(ids))
        for c in cols:
            x, y = a.loc[ids, c], b.loc[ids, c]
            v = x.notna() & y.notna()
            rs[c].append(np.corrcoef(x[v], y[v])[0, 1] if v.sum() > 5 else np.nan)
    out = pd.DataFrame({"metric": cols, "half_r_mean": [np.nanmean(rs[c]) for c in cols],
                        "half_r_sd": [np.nanstd(rs[c]) for c in cols]})
    out["full_sample_reliability"] = out.half_r_mean.apply(sb)
    out["players_per_split"] = int(np.mean(ns))
    out["component"] = out.metric.map({v: k for k, v in comp.items()}).fillna("(reference)")
    return out


def season_stability(d, kappa, cfg, kind):
    rc = cfg["reliability"]
    fn = pm.batting if kind == "bat" else pm.bowling
    col = "rv_P" if kind == "bat" else "bv_P"
    ncol = "balls_P" if kind == "bat" else "legal_P"
    nmin = rc["min_season_bat_pressure_balls"] if kind == "bat" else rc["min_season_bowl_pressure_legal"]
    per = {y: fn(d[d.year == y], kappa, cfg) for y in sorted(d.year.unique())}
    rows = []
    for y in sorted(per)[:-1]:
        a, b = per[y], per[y + 1]
        ids = a.index[(a[ncol] >= nmin)].intersection(b.index[(b[ncol] >= nmin)])
        if len(ids) > 5:
            rows.append({"seasons": f"{y}→{y+1}", "players": len(ids),
                         "r": np.corrcoef(a.loc[ids, col], b.loc[ids, col])[0, 1]})
    t = pd.DataFrame(rows)
    z = np.average(np.arctanh(t.r), weights=t.players - 3)
    return t, float(np.tanh(z))


def variance_decomposition(d, kind, pressure: bool, kappa):
    """Per-ball value: τ² (true between-player variance) and σ²_ball; n* = σ²/τ²."""
    if kind == "bat":
        x = d[d.is_ball_faced]
        v = (x.runs - x.e_runs) - x.lam * (x.out_striker - x.e_out)
        pid = x.striker_id
    else:
        x = d
        v = (x.e_conc - x.bowler_runs) + x.lam * (x.is_bowler_wicket - x.e_wkt)
        pid = x.bowler_id
    m = (x.is_pressure if pressure else ~x.is_pressure).to_numpy()
    g = pd.DataFrame({"pid": pid[m], "v": v[m]}).groupby("pid").v.agg(["mean", "var", "size"])
    g = g[g["size"] >= 50]
    sigma2 = float(np.average(g["var"], weights=g["size"]))
    tau2 = float(g["mean"].var() - np.mean(g["var"] / g["size"]))
    return {"players": len(g), "sigma2_ball": sigma2, "tau2": tau2,
            "n_star": sigma2 / tau2 if tau2 > 0 else np.inf}


def apply_weight_rule(weights: dict, rel: dict, thr: float) -> tuple[dict, list[str]]:
    r = {k: max(rel[k], 0.0) for k in weights}
    mean_r = np.mean(list(r.values()))
    new, notes = {}, []
    for k, w in weights.items():
        if rel[k] < thr:
            new[k] = w * r[k] / mean_r if mean_r > 0 else 0.0
            notes.append(f"{k}: reliability {rel[k]:.2f} < {thr} → weight {w:.2f} × {r[k]:.2f}/{mean_r:.2f}")
        else:
            new[k] = w
    s = sum(new.values())
    return {k: v / s for k, v in new.items()}, notes


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    interim, out = path(cfg, "interim"), path(cfg, "outputs")
    d = pd.read_parquet(interim / "rating_balls.parquet")
    d["rec"] = pm.recency(d.match_date, cfg["reference_date"], cfg["metrics"]["recency_half_life_years"])
    kappa = cfg["metrics"]["tier_credibility_fallback"]
    rc, el = cfg["reliability"], cfg["eligibility_provisional"]

    L = ["# T10 — Reliability of pressure metrics", "",
         "Generated by `src/reliability.py`. Decision rules were written into `config.yaml` (section "
         "`reliability`) **before** these results were computed. No player names are shown.", ""]
    result = {}
    for kind, comp in (("bat", BAT_COMP), ("bowl", BOWL_COMP)):
        sh = split_half(d, kappa, cfg, kind)
        seas, seas_r = season_stability(d, kappa, cfg, kind)
        vdP = variance_decomposition(d, kind, True, kappa)
        vdN = variance_decomposition(d, kind, False, kappa)
        rel = {k: float(sh.set_index("metric").loc[v, "full_sample_reliability"]) for k, v in comp.items()}
        new_w, notes = apply_weight_rule(cfg["composite_weights"], rel, rc["weight_rule_threshold"])

        # eligibility rule
        tbl = pd.read_parquet(interim / f"player_{kind}.parquet")
        ncol, mcol = ("balls_P", "pressure_innings_any") if kind == "bat" else ("legal_P", "pressure_matches_any")
        prov_n = el["bat_min_pressure_balls"] if kind == "bat" else el["bowl_min_pressure_balls"]
        prov_m = el["bat_min_pressure_innings"] if kind == "bat" else el["bowl_min_pressure_matches"]
        n_star = vdP["n_star"]
        pool_at_nstar = int(((tbl[ncol] >= n_star) & (tbl[mcol] >= prov_m) & tbl.active_since_2025).sum()) \
            if np.isfinite(n_star) else 0
        if np.isfinite(n_star) and pool_at_nstar >= rc["min_pool_size"]:
            min_n, how = int(np.ceil(max(n_star, prov_n))), f"n* rule (pool {pool_at_nstar})"
        else:
            min_n, how = prov_n, (f"provisional kept: pool at n* = {pool_at_nstar} < {rc['min_pool_size']}"
                                  if np.isfinite(n_star) else "provisional kept: τ² ≤ 0")
        exp_rel = min_n / (min_n + n_star) if np.isfinite(n_star) else 0.0
        pool = int(((tbl[ncol] >= min_n) & (tbl[mcol] >= prov_m) & tbl.active_since_2025).sum())
        result[kind] = {"split_half": sh, "season": seas, "season_r": seas_r, "vd_P": vdP, "vd_N": vdN,
                        "reliability": rel, "weights": new_w, "weight_notes": notes,
                        "min_pressure_n": min_n, "min_pressure_units": prov_m, "eligibility_rule": how,
                        "expected_reliability_at_min": exp_rel, "pool": pool}

        name = "Batting" if kind == "bat" else "Bowling"
        L += [f"## {name}", "",
              f"### Split-half reliability ({rc['random_splits']} random match splits)", "",
              md_table(sh[["component", "metric", "half_r_mean", "half_r_sd", "full_sample_reliability",
                           "players_per_split"]], index=False, floatfmt="{:.3f}"), "",
              "### Season-to-season stability of pressure value", "",
              md_table(seas, index=False, floatfmt="{:.3f}"), "", f"Pooled r = **{seas_r:.3f}**", "",
              "### Variance decomposition (per-ball value, players with ≥ 50 balls)", "",
              md_table(pd.DataFrame({"pressure balls": vdP, "non-pressure balls": vdN}), floatfmt="{:.4f}"), "",
              f"Stabilisation point n* (pressure) = **{n_star:.0f} balls**: an observed pressure value from n "
              f"balls is n/(n+n*) signal.", "",
              "### Decisions (pre-registered rules)", "",
              f"- Eligibility: min pressure balls = **{min_n}** ({how}); expected reliability at the minimum ≈ "
              f"{exp_rel:.2f}; eligible pool = **{pool}**.",
              f"- Weight rule: {'; '.join(notes) if notes else 'no component below threshold'}",
              f"- Final composite weights: {', '.join(f'{k} {v:.3f}' for k, v in new_w.items())}", ""]

    with open(interim / "reliability.pkl", "wb") as fh:
        pickle.dump(result, fh)
    (out / "validation" / "reliability.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return result, L


if __name__ == "__main__":
    run()
