"""T5 — Scoring environment, expected-remaining-runs (ERR) model and wicket run value.

* env_par  : tier × season mean first-innings total (complete 20-over innings), shrunk toward
             the tier mean with k pseudo-innings. Describes the scoring environment.
* ERR      : E[runs still to come in this innings | balls_rem, wickets_in_hand, env_par],
             fitted on complete first innings. Three candidates, compared by
             leave-one-season-out (LOSO) CV:
               - GLM : Poisson GLM, tensor-product cubic splines in (balls_rem, wickets_in_hand)
                       + log(env_par)
               - HGB : Poisson gradient boosting with monotonic constraints (challenger)
             Rule (planning/03 §3.1): keep the simpler GLM unless HGB is > 1% better.
* lambda   : run value of a wicket = ERR(b, w) − ERR(b, w−1)   (ERR(·, 0) = 0)

Outputs: data_interim/models/err.pkl, data_interim/env_par.parquet,
         outputs/validation/err_model.md, outputs/figures/err_curves.png
"""
from __future__ import annotations

import pickle

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.api as sm  # noqa: E402
import statsmodels.formula.api as smf  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402

from common import load_config, md_table, path  # noqa: E402

SEED = 20261117
GLM_FORMULA = ("runs_rem ~ te(cr(balls_rem, df=6), cr(wickets_in_hand, df=4), constraints='center')"
               " + np.log(env_par)")


# --------------------------------------------------------------------------- environment
def complete_first_innings(inn: pd.DataFrame) -> pd.DataFrame:
    return inn[(inn.innings == 1) & (inn.ball_limit == 120) & ~inn.is_dls & ~inn.is_no_result
               & ~inn.limit_inferred & ((inn.legal >= 119) | (inn.wkts == 10))]


def build_env_par(inn: pd.DataFrame, m: pd.DataFrame, k: float = 10.0) -> pd.DataFrame:
    i = complete_first_innings(inn).merge(m[["match_id", "year"]], on="match_id")
    tier_mean = i.groupby("tier").total.mean()
    g = i.groupby(["tier", "year"]).total.agg(["sum", "count"]).reset_index()
    g["env_par"] = (g["sum"] + k * g.tier.map(tier_mean)) / (g["count"] + k)
    # every tier-year present in the matches table (fallback = tier mean)
    allty = m[["tier", "year"]].drop_duplicates()
    out = allty.merge(g[["tier", "year", "env_par", "count"]], on=["tier", "year"], how="left")
    out["env_par"] = out["env_par"].fillna(out.tier.map(tier_mean))
    return out.rename(columns={"count": "n_innings"})


# --------------------------------------------------------------------------- ERR model
class ERRModel:
    """Wrapper so callers can use ERR without caring which model won."""

    def __init__(self, kind: str, model):
        self.kind, self.model = kind, model

    @staticmethod
    def _X(df: pd.DataFrame) -> np.ndarray:
        return df[["balls_rem", "wickets_in_hand", "env_par"]].to_numpy(dtype=float)

    def predict(self, balls_rem, wickets_in_hand, env_par) -> np.ndarray:
        b, w, e = (a.ravel() for a in np.broadcast_arrays(
            np.atleast_1d(np.asarray(balls_rem, float)),
            np.atleast_1d(np.asarray(wickets_in_hand, float)),
            np.atleast_1d(np.asarray(env_par, float))))
        df = pd.DataFrame({"balls_rem": b, "wickets_in_hand": w, "env_par": e})
        out = np.zeros(len(df))
        ok = (df.balls_rem > 0) & (df.wickets_in_hand > 0)
        if ok.any():
            d = df[ok]
            out[ok.to_numpy()] = (self.model.predict(self._X(d)) if self.kind == "HGB"
                                  else np.asarray(self.model.predict(d)))
        return out

    def wicket_value(self, balls_rem, wickets_in_hand, env_par) -> np.ndarray:
        w = np.asarray(wickets_in_hand, float)
        return self.predict(balls_rem, w, env_par) - self.predict(balls_rem, w - 1, env_par)


class DLSFit:
    """DLS-style resource curve per wickets-in-hand w, scaled by the scoring environment:

        ERR(b, w, env) = (env / REF) · Z_w · (1 − exp(−k_w · b))

    Increasing in balls by construction and bounded. Monotonicity in wickets is enforced by
    a cumulative max over w (more wickets in hand never means fewer expected runs).
    """
    REF = 160.0

    def __init__(self, Z: np.ndarray, k: np.ndarray):
        self.Z, self.k = Z, k            # index 0..9 ↔ w = 1..10

    def predict(self, d: pd.DataFrame) -> np.ndarray:
        b = d["balls_rem"].to_numpy(float)[:, None]
        curves = self.Z[None, :] * (1 - np.exp(-self.k[None, :] * b))     # n × 10
        curves = np.maximum.accumulate(curves, axis=1)
        w = d["wickets_in_hand"].to_numpy(int).clip(1, 10) - 1
        return curves[np.arange(len(d)), w] * d["env_par"].to_numpy(float) / self.REF


def fit_dls(d: pd.DataFrame) -> DLSFit:
    from scipy.optimize import curve_fit

    y = d["runs_rem"] * DLSFit.REF / d["env_par"]
    agg = pd.DataFrame({"b": d.balls_rem, "w": d.wickets_in_hand, "y": y}).groupby(["w", "b"]).y.agg(["mean", "count"])
    Z, k = np.zeros(10), np.zeros(10)
    f = lambda b, z, kk: z * (1 - np.exp(-kk * b))  # noqa: E731
    for w in range(1, 11):
        a = agg.loc[w].reset_index() if w in agg.index.get_level_values(0) else None
        if a is None or len(a) < 5:
            Z[w - 1], k[w - 1] = (Z[w - 2], k[w - 2]) if w > 1 else (20.0, 0.1)
            continue
        (Z[w - 1], k[w - 1]), _ = curve_fit(f, a.b.to_numpy(float), a["mean"].to_numpy(float),
                                            p0=(a["mean"].max() * 1.5, 0.02),
                                            sigma=1 / np.sqrt(a["count"].to_numpy(float)),
                                            bounds=([0, 1e-4], [600, 1.0]), maxfev=20000)
    return DLSFit(Z, k)


def fit_glm(d: pd.DataFrame):
    return smf.glm(GLM_FORMULA, data=d, family=sm.families.Poisson()).fit()


def fit_hgb(d: pd.DataFrame):
    m = HistGradientBoostingRegressor(loss="poisson", max_iter=400, learning_rate=0.05,
                                      max_leaf_nodes=31, min_samples_leaf=200,
                                      monotonic_cst=[1, 1, 1], random_state=SEED)
    return m.fit(ERRModel._X(d), d["runs_rem"].to_numpy())


def training_rows(bs: pd.DataFrame, inn: pd.DataFrame, env: pd.DataFrame) -> pd.DataFrame:
    ok = complete_first_innings(inn)[["match_id", "total"]]
    d = bs[(bs.innings == 1) & bs.is_legal].merge(ok, on="match_id")
    d = d.merge(env[["tier", "year", "env_par"]], on=["tier", "year"], how="left")
    d["runs_rem"] = d["total"] - d["score_before"]
    d = d.rename(columns={"balls_rem_before": "balls_rem"})
    return d[["match_id", "year", "tier", "balls_rem", "wickets_in_hand", "env_par", "runs_rem"]]


def loso(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for yr in sorted(d.year.unique()):
        tr, te = d[d.year != yr], d[d.year == yr]
        y = te.runs_rem.to_numpy()
        # naive baseline: cell mean by (balls_rem, wickets_in_hand) from training years
        cell = tr.groupby(["balls_rem", "wickets_in_hand"]).runs_rem.mean()
        naive = te.set_index(["balls_rem", "wickets_in_hand"]).index.map(cell).to_numpy(dtype=float)
        naive = np.where(np.isnan(naive), tr.runs_rem.mean(), naive)
        preds = {"naive_cell_mean": naive,
                 "GLM": np.asarray(fit_glm(tr).predict(te)),
                 "HGB": fit_hgb(tr).predict(ERRModel._X(te)),
                 "DLS": fit_dls(tr).predict(te)}
        for k, p in preds.items():
            rows.append({"held_out_year": yr, "model": k, "n": len(te),
                         "MAE": np.mean(np.abs(y - p)), "bias": np.mean(p - y)})
    return pd.DataFrame(rows)


def monotonic_violations(model: ERRModel, env_par: float) -> dict:
    b, w = np.meshgrid(np.arange(1, 121), np.arange(1, 11))
    grid = model.predict(b.ravel(), w.ravel(), np.full(b.size, env_par)).reshape(w.shape)
    return {"balls_dir_violations": int((np.diff(grid, axis=1) < -0.5).sum()),
            "wkts_dir_violations": int((np.diff(grid, axis=0) < -0.5).sum()),
            "cells": int(grid.size), "grid": grid}


# --------------------------------------------------------------------------- run
def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    interim, out = path(cfg, "interim"), path(cfg, "outputs")
    (interim / "models").mkdir(exist_ok=True)
    (out / "validation").mkdir(exist_ok=True)
    (out / "figures").mkdir(exist_ok=True)

    bs = pd.read_parquet(interim / "ball_state.parquet")
    inn = pd.read_parquet(interim / "innings.parquet")
    m = pd.read_parquet(interim / "matches.parquet")

    env = build_env_par(inn, m)
    env.to_parquet(interim / "env_par.parquet", index=False)

    d = training_rows(bs, inn, env)
    cv = loso(d)
    summ = cv.groupby("model").apply(lambda g: pd.Series({
        "MAE_weighted": np.average(g.MAE, weights=g.n), "mean_bias": np.average(g.bias, weights=g.n)}),
        include_groups=False)
    ref_env = float(env.loc[(env.tier == "T1_IPL") & (env.year == 2026), "env_par"].iloc[0])

    # Selection rule: (1) must be monotone on the full state grid (validity gate, planning/07 T5);
    # (2) among passing models, lowest LOSO MAE; within 1% prefer the simpler one (DLS < GLM < HGB).
    fitters = {"DLS": fit_dls, "GLM": fit_glm, "HGB": fit_hgb}
    cands, mono_tbl = {}, []
    for k, f in fitters.items():
        mdl = ERRModel(k, f(d))
        mv = monotonic_violations(mdl, ref_env); mv.pop("grid")
        lam_min = float(np.min(mdl.wicket_value(*np.meshgrid(np.arange(1, 121), np.arange(1, 11)),
                                                ref_env)))
        cands[k] = mdl
        mono_tbl.append({"model": k, **mv, "min_wicket_value": lam_min,
                         "LOSO_MAE": summ.loc[k, "MAE_weighted"],
                         "passes": mv["balls_dir_violations"] == 0 and mv["wkts_dir_violations"] == 0
                                   and lam_min > -0.5})
    mono_df = pd.DataFrame(mono_tbl).set_index("model")
    passing = mono_df[mono_df.passes]
    if passing.empty:
        raise RuntimeError("No ERR candidate passes the monotonicity gate")
    best = passing.LOSO_MAE.min()
    kind = next(k for k in ["DLS", "GLM", "HGB"] if k in passing.index
                and passing.loc[k, "LOSO_MAE"] <= best * 1.01)
    final = cands[kind]
    with open(interim / "models" / "err.pkl", "wb") as fh:
        pickle.dump(final, fh)

    mono = monotonic_violations(final, ref_env)
    grid = mono.pop("grid")

    # Figure: ERR curves and wicket value
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for w in [10, 8, 6, 4, 2]:
        ax[0].plot(np.arange(1, 121), grid[w - 1], label=f"{w} wkts in hand")
        lam = final.wicket_value(np.arange(1, 121), np.full(120, w), np.full(120, ref_env))
        ax[1].plot(np.arange(1, 121), lam, label=f"{w} in hand → {w - 1}")
    ax[0].set(xlabel="Legal balls remaining", ylabel="Expected remaining runs",
              title=f"ERR ({kind}), IPL 2026 environment")
    ax[1].set(xlabel="Legal balls remaining", ylabel="Runs lost by a wicket (λ)",
              title="Run value of a wicket")
    for a in ax:
        a.legend(fontsize=7); a.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(out / "figures" / "err_curves.png", dpi=130); plt.close(fig)

    lam_tbl = pd.DataFrame({f"{w} wkts": [final.wicket_value(b, w, ref_env)[0] for b in (120, 90, 60, 30, 12, 6)]
                            for w in (10, 7, 5, 3, 1)}, index=[f"{b} balls left" for b in (120, 90, 60, 30, 12, 6)])
    err_tbl = pd.DataFrame({f"{w} wkts": [final.predict(b, w, ref_env)[0] for b in (120, 90, 60, 30, 12, 6)]
                            for w in (10, 7, 5, 3, 1)}, index=lam_tbl.index)

    L = ["# T5 — Scoring environment & expected-remaining-runs model", "",
         "Generated by `src/models_par.py`. Training rows = legal balls of complete, non-reduced first innings "
         f"(n = {len(d):,} balls, {d.match_id.nunique()} innings).", "",
         "## Scoring environment (env_par: shrunk tier × season mean first-innings total)", "",
         md_table(env.sort_values(["tier", "year"]).round(1), index=False, floatfmt="{:.1f}"), "",
         "## Leave-one-season-out validation (MAE of remaining runs)", "",
         md_table(cv.pivot(index="held_out_year", columns="model", values="MAE")), "",
         md_table(summ, floatfmt="{:.3f}"), "",
         "## Candidate validity gate (fitted on all training rows)", "",
         "A candidate must be non-decreasing in balls remaining and in wickets in hand on the full "
         "120 × 10 state grid (tolerance 0.5 run) and never give a negative wicket value. "
         "Among passing candidates the lowest LOSO MAE wins; within 1% the simpler model is preferred "
         "(DLS < GLM < HGB).", "",
         md_table(mono_df), "",
         f"**Selected model: {kind}**.", "",
         f"Monotonicity on a 120 × 10 grid (IPL 2026 env, tolerance 0.5 run): {mono}", "",
         "## Expected remaining runs, IPL 2026 environment (env_par = %.1f)" % ref_env, "",
         md_table(err_tbl, floatfmt="{:.1f}"), "",
         "## Run value of losing a wicket (λ), IPL 2026 environment", "",
         "Column = wickets in hand *before* the wicket falls.", "",
         md_table(lam_tbl, floatfmt="{:.1f}"), "",
         "![ERR curves](../figures/err_curves.png)"]
    (out / "validation" / "err_model.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return final, env, L


if __name__ == "__main__":
    run()
