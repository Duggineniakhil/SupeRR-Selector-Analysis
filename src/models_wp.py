"""T6 — Win-probability (WP) models: P(batting side wins | state before the delivery).

Two separate models (planning/03 §3.1):
  * Chase (innings 2): runs needed, balls remaining, wickets in hand, ERR resource (T5).
  * First innings   : score, balls remaining, wickets in hand, par for this innings length.

Candidates per innings (fitted on legal balls with wp_usable = True):
  * GLM : logistic GLM with a centred tensor-product spline of one "equation" feature and
          the fraction of the innings left (interpretable).
  * HGB : gradient-boosted classifier with monotonic constraints (challenger).
Validation: leave-one-season-out (LOSO) log-loss / Brier / AUC / calibration vs a
phase-only baseline. Selection rule (same as T5): a candidate must pass a monotonicity gate
on a full state grid; among passing models lowest LOSO log-loss wins, preferring the
simpler GLM when within 1%.

Outputs: data_interim/models/wp.pkl, data_interim/wp.parquet (wp_before / wp_after per
delivery, batting-side perspective), outputs/validation/wp_model.md, outputs/figures/wp_*.png
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
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score  # noqa: E402

import models_par  # noqa: E402,F401  (needed to unpickle the ERR model)
from common import load_config, md_table, path  # noqa: E402

SEED = 20261117
EPS = 1e-4
FEASIBILITY_CAP = 0.01
GLM_FORMULA = {
    2: "y ~ te(cr(z, df=6), cr(frac, df=4), constraints='center') + wih",
    1: "y ~ te(cr(z, df=6), cr(frac, df=4), constraints='center') + wih",
}
HGB_FEATURES = {
    2: (["runs_needed", "balls_rem", "wih", "err"], [-1, 1, 1, 1]),
    1: (["score", "balls_rem", "wih", "par_limit"], [1, 1, 1, -1]),
}


# --------------------------------------------------------------------------- features
def add_features(df: pd.DataFrame, err_model, innings: int) -> pd.DataFrame:
    """df needs: balls_rem, wih, env_par, ball_limit and runs_needed (inn 2) or score (inn 1)."""
    d = df.copy()
    d["err"] = err_model.predict(d.balls_rem, d.wih, d.env_par)
    d["frac"] = d.balls_rem / 120.0
    if innings == 2:
        # equation feature: resources left vs runs required, scaled by remaining uncertainty
        d["z"] = ((d.err - d.runs_needed) / np.sqrt(d.err + 10)).clip(-6, 6)
    else:
        d["par_limit"] = err_model.predict(d.ball_limit, 10, d.env_par)
        d["z"] = ((d.score + d.err - d.par_limit) / np.sqrt(d.err + 100)).clip(-6, 6)
    return d


class WPModel:
    def __init__(self, kind: str, model, innings: int):
        self.kind, self.model, self.innings = kind, model, innings

    def predict(self, d: pd.DataFrame) -> np.ndarray:
        if self.kind == "GLM":
            p = np.asarray(self.model.predict(d))
        else:
            cols, _ = HGB_FEATURES[self.innings]
            p = self.model.predict_proba(d[cols].to_numpy(float))[:, 1]
        if self.innings == 2:
            # Feasibility cap: needing more than 6 per remaining legal ball is only possible
            # through extras, so the smooth model's tail is overridden (e.g. 8 off 1 ball).
            infeasible = d["runs_needed"].to_numpy(float) > 6 * d["balls_rem"].to_numpy(float)
            p = np.where(infeasible, np.minimum(p, FEASIBILITY_CAP), p)
        return np.clip(p, EPS, 1 - EPS)


def fit(kind: str, d: pd.DataFrame, innings: int) -> WPModel:
    if kind == "GLM":
        mdl = smf.glm(GLM_FORMULA[innings], data=d, family=sm.families.Binomial()).fit()
    else:
        cols, mono = HGB_FEATURES[innings]
        mdl = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                             min_samples_leaf=500, l2_regularization=1.0,
                                             monotonic_cst=mono, early_stopping=False,
                                             random_state=SEED)
        mdl.fit(d[cols].to_numpy(float), d.y.to_numpy())
    return WPModel(kind, mdl, innings)


# --------------------------------------------------------------------------- data
def model_frame(bs: pd.DataFrame, env: pd.DataFrame, err_model, innings: int) -> pd.DataFrame:
    d = bs[bs.innings == innings].merge(env[["tier", "year", "env_par"]], on=["tier", "year"], how="left")
    d = d.rename(columns={"balls_rem_before": "balls_rem", "wickets_in_hand": "wih",
                          "runs_needed_before": "runs_needed", "score_before": "score"})
    d = add_features(d, err_model, innings)
    d["y"] = d["batting_side_won"]
    return d


def phase_baseline(tr: pd.DataFrame, te: pd.DataFrame) -> np.ndarray:
    key = ["phase", pd.cut(tr.wih, [0, 3, 6, 8, 10]).astype(str).name]
    trb = tr.assign(wb=pd.cut(tr.wih, [0, 3, 6, 8, 10]).astype(str))
    teb = te.assign(wb=pd.cut(te.wih, [0, 3, 6, 8, 10]).astype(str))
    rate = trb.groupby(["phase", "wb"]).y.mean()
    p = teb.set_index(["phase", "wb"]).index.map(rate).to_numpy(dtype=float)
    del key
    return np.clip(np.where(np.isnan(p), tr.y.mean(), p), EPS, 1 - EPS)


def calib(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    lg = np.log(p / (1 - p))
    r = sm.Logit(y, sm.add_constant(lg)).fit(disp=0)
    return float(r.params[1]), float(r.params[0])


def loso(d: pd.DataFrame, innings: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, oos = [], []
    for yr in sorted(d.year.unique()):
        tr, te = d[d.year != yr], d[d.year == yr]
        preds = {"phase_baseline": phase_baseline(tr, te),
                 "GLM": fit("GLM", tr, innings).predict(te),
                 "HGB": fit("HGB", tr, innings).predict(te)}
        y = te.y.to_numpy()
        for k, p in preds.items():
            s, i = calib(y, p)
            rows.append({"held_out_year": yr, "model": k, "n": len(te),
                         "log_loss": log_loss(y, p), "brier": brier_score_loss(y, p),
                         "auc": roc_auc_score(y, p), "calib_slope": s, "calib_intercept": i})
        oos.append(te[["match_id", "year", "y"]].assign(GLM=preds["GLM"], HGB=preds["HGB"],
                                                       phase_baseline=preds["phase_baseline"]))
    return pd.DataFrame(rows), pd.concat(oos)


def monotonic_gate(model: WPModel, err_model, innings: int, env_par: float) -> dict:
    br, w = np.arange(1, 121), np.arange(1, 11)
    if innings == 2:
        x = np.arange(1, 251, 3)
        X, B, W = np.meshgrid(x, br, w, indexing="ij")
        g = pd.DataFrame({"runs_needed": X.ravel(), "balls_rem": B.ravel(), "wih": W.ravel(),
                          "env_par": env_par, "ball_limit": 120})
        sign_x = -1                                   # more runs needed → lower WP
    else:
        x = np.arange(0, 251, 5)
        X, B, W = np.meshgrid(x, br, w, indexing="ij")
        g = pd.DataFrame({"score": X.ravel(), "balls_rem": B.ravel(), "wih": W.ravel(),
                          "env_par": env_par, "ball_limit": 120})
        sign_x = 1
    p = model.predict(add_features(g, err_model, innings)).reshape(X.shape)
    tol = 0.01
    return {"x_dir_violations": int((sign_x * np.diff(p, axis=0) < -tol).sum()),
            "balls_dir_violations": int((np.diff(p, axis=1) < -tol).sum()) if innings == 1
            else int((np.diff(p, axis=1) < -tol).sum()),
            "wkts_dir_violations": int((np.diff(p, axis=2) < -tol).sum()),
            "grid_points": int(p.size)}


# --------------------------------------------------------------------------- run
def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    interim, out = path(cfg, "interim"), path(cfg, "outputs")
    for sub in ("validation", "figures"):
        (out / sub).mkdir(exist_ok=True)
    with open(interim / "models" / "err.pkl", "rb") as fh:
        err_model = pickle.load(fh)
    bs = pd.read_parquet(interim / "ball_state.parquet")
    env = pd.read_parquet(interim / "env_par.parquet")
    ref_env = float(env.loc[(env.tier == "T1_IPL") & (env.year == 2026), "env_par"].iloc[0])

    L = ["# T6 — Win-probability models", "",
         "Generated by `src/models_wp.py`. Target = batting side wins (ties / no-results excluded). "
         "Training rows = legal balls with `wp_usable` (reliable targets, decided matches).", ""]
    finals, figs = {}, {}
    for inn in (2, 1):
        name = "Chase (innings 2)" if inn == 2 else "First innings"
        d_all = model_frame(bs, env, err_model, inn)
        d = d_all[d_all.is_legal & d_all.wp_usable].copy()
        cv, oos = loso(d, inn)
        summ = cv.groupby("model").apply(lambda g: pd.Series({
            "log_loss": np.average(g.log_loss, weights=g.n), "brier": np.average(g.brier, weights=g.n),
            "auc": np.average(g.auc, weights=g.n), "calib_slope": np.average(g.calib_slope, weights=g.n),
            "calib_intercept": np.average(g.calib_intercept, weights=g.n)}), include_groups=False)

        gate = []
        cands = {k: fit(k, d, inn) for k in ("GLM", "HGB")}
        for k, mdl in cands.items():
            mg = monotonic_gate(mdl, err_model, inn, ref_env)
            passes = (mg["x_dir_violations"] + mg["balls_dir_violations"] + mg["wkts_dir_violations"]) == 0
            gate.append({"model": k, **mg, "LOSO_log_loss": summ.loc[k, "log_loss"], "passes": passes})
        gate = pd.DataFrame(gate).set_index("model")
        passing = gate[gate.passes]
        if passing.empty:
            raise RuntimeError(f"No WP candidate passes the monotonicity gate for innings {inn}")
        best = passing.LOSO_log_loss.min()
        kind = next(k for k in ("GLM", "HGB") if k in passing.index
                    and passing.loc[k, "LOSO_log_loss"] <= best * 1.01)
        finals[inn] = cands[kind]
        figs[inn] = (oos, kind)

        L += [f"## {name}", "", f"Training rows: {len(d):,} legal balls from {d.match_id.nunique()} matches.", "",
              "### Leave-one-season-out (log-loss, lower is better)", "",
              md_table(cv.pivot(index="held_out_year", columns="model", values="log_loss"), floatfmt="{:.4f}"), "",
              "### Pooled LOSO metrics", "", md_table(summ, floatfmt="{:.4f}"), "",
              "### Monotonicity gate (IPL 2026 environment; tolerance 0.01 WP)", "",
              md_table(gate, floatfmt="{:.4f}"), "", f"**Selected: {kind}**", ""]

    with open(interim / "models" / "wp.pkl", "wb") as fh:
        pickle.dump({"err": err_model, "wp": finals}, fh)

    # ---- per-delivery WP (batting-side perspective), then wp_after by chaining
    parts = []
    for inn in (1, 2):
        d_all = model_frame(bs, env, err_model, inn)
        p = finals[inn].predict(d_all)
        if inn == 2:
            p = np.where(d_all.target_reliable, p, np.nan)
        parts.append(d_all[["match_id", "innings", "innings_ball_num", "batting_team_id"]].assign(wp_before=p))
    wp = pd.concat(parts).sort_values(["match_id", "innings", "innings_ball_num"]).reset_index(drop=True)
    wp["wp_after"] = wp.groupby(["match_id", "innings"]).wp_before.shift(-1)
    last = wp.groupby(["match_id", "innings"]).tail(1).index
    res = bs[bs.innings <= 2].groupby(["match_id", "innings"]).batting_side_won.first()
    first2 = wp[wp.innings == 2].groupby("match_id").wp_before.first()
    for ix in last:
        mid, inn = wp.at[ix, "match_id"], wp.at[ix, "innings"]
        if inn == 1:   # end of innings 1 → batting-first side's WP at start of the chase
            wp.at[ix, "wp_after"] = 1 - first2.get(mid, np.nan)
        else:          # end of the match → actual result (NaN for ties / no-results)
            wp.at[ix, "wp_after"] = res.get((mid, inn), np.nan)
    wp.to_parquet(interim / "wp.parquet", index=False)

    # ---- diagnostics: innings-break continuity and a worked example
    w1 = wp[wp.innings == 1].groupby("match_id").tail(1).set_index("match_id")
    cont = (w1.wp_before - w1.wp_after).abs().dropna()
    ex_id = 20248
    ex = wp[(wp.match_id == ex_id) & (wp.innings == 2)].tail(8).merge(
        bs[["match_id", "innings", "innings_ball_num", "striker_name", "total_runs", "runs_needed_before",
            "balls_rem_before"]], on=["match_id", "innings", "innings_ball_num"])
    L += ["## Coherence checks", "",
          f"- Innings-break continuity: |WP(last ball of inn 1, first-innings model) − WP(first ball of chase, "
          f"chase model)|: median {cont.median():.3f}, 90th pct {cont.quantile(.9):.3f} (n = {len(cont)}).",
          f"- Deliveries with a WP estimate: {wp.wp_before.notna().mean():.1%} of innings-1/2 deliveries "
          "(missing = unreliable chase targets).", "",
          f"### Worked example — match {ex_id} (IPL 2023, chase lost by 1 run): last 8 deliveries", "",
          md_table(ex[["striker_name", "runs_needed_before", "balls_rem_before", "total_runs", "wp_before",
                       "wp_after"]], index=False, floatfmt="{:.3f}"), "",
          "![Calibration](../figures/wp_calibration.png)", ""]

    fig, ax = plt.subplots(1, 2, figsize=(10, 4.4))
    for a, inn in zip(ax, (1, 2)):
        oos, kind = figs[inn]
        for k, style in ((kind, "o-"), ("phase_baseline", "s--")):
            q = pd.qcut(oos[k], 10, duplicates="drop")
            c = oos.groupby(q, observed=True).agg(p=(k, "mean"), y=("y", "mean"))
            a.plot(c.p, c.y, style, label=f"{k} (held-out seasons)")
        a.plot([0, 1], [0, 1], color="grey", lw=.8)
        a.set(title=("First innings" if inn == 1 else "Chase") + " — calibration by decile",
              xlabel="Predicted WP", ylabel="Observed win rate")
        a.legend(fontsize=8); a.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(out / "figures" / "wp_calibration.png", dpi=130); plt.close(fig)

    (out / "validation" / "wp_model.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return finals, wp, L


if __name__ == "__main__":
    run()
