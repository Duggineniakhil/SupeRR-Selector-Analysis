"""T11 — Reliability-adjusted pressure performance estimators (decision D5).

Per-ball context-adjusted value v (batting: (runs − E) − λ(out − E); bowling: (E[conc] − conc)
+ λ(wkt − E)). Per player and period:
    x_P  = leverage-weighted mean of v on pressure balls      (actual pressure performance)
    x_N  = mean of v on non-pressure balls                    (baseline evidence)
    x_A  = mean of v on all balls                             (all-balls evidence)
(all weights include recency and the competition-tier factor; effective n = (Σw)² / Σw²)

Empirical-Bayes (normal–normal) with hyper-parameters estimated on the TRAINING data only:
    μ_g  role-group mean, τ² between-player true variance (method of moments),
    σ²_g per-ball variance by role group; posterior = μ_g + τ²/(τ² + σ²_g/n)·(x − μ_g)

Estimators of future pressure performance:
    M1  pressure-only:  EB(x_P)
    M2  all-balls:      EB(x_A)
    M3  hybrid:         B = EB(x_N) (baseline ability);  r = x_P − B (pressure residual);
                        Adv = m_r + s_R·(r − m_r), s_R = τ²_R/(τ²_R + Var(r)) (shrunk pressure
                        advantage; τ²_R by method of moments, floored at 0)
    M4  pre-registered composite (z(M1) + z(pressure WPA) + z(consistency), T10 weights);
        ranking metric only.
Each of M1–M3 is mapped to a prediction by y = a + b·features, with (a, b) fitted on an
inner random half-split of the TRAINING matches (features on half A → observed pressure
value on half B), so no blend weight is set by hand and nothing leaks from the test season.

Validation: chronological folds (train < season, test = season) for 2024, 2025, 2026.
Selection: pre-registered rule in config.yaml (estimators).
Final fit: all data; match-cluster bootstrap for rank uncertainty.

Outputs: outputs/validation/t11_estimators.md (no names),
         outputs/rankings/{batting,bowling}_ratings.csv (+ .md)  [local only, git-ignored]
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import player_metrics as pm
from common import load_config, md_table, path

KINDS = ("bat", "bowl")


# --------------------------------------------------------------------------- per-player stats
def ball_values(d: pd.DataFrame, kind: str) -> pd.DataFrame:
    if kind == "bat":
        x = d[d.is_ball_faced]
        v = (x.runs - x.e_runs) - x.lam * (x.out_striker - x.e_out)
        pid = x.striker_id
    else:
        x = d
        v = (x.e_conc - x.bowler_runs) + x.lam * (x.is_bowler_wicket - x.e_wkt)
        pid = x.bowler_id
    return pd.DataFrame({"pid": pid.to_numpy(), "match_id": x.match_id.to_numpy(), "v": v.to_numpy(),
                         "P": x.is_pressure.to_numpy(), "li_w": x.li_weight.to_numpy(),
                         "tier": x.tier.to_numpy(), "date": x.match_date.to_numpy(),
                         "batting_order": x.batting_order.to_numpy(), "pace_or_spin": x.pace_or_spin.to_numpy(),
                         "phase": x.phase.to_numpy()})


def player_stats(bv: pd.DataFrame, kappa: dict, ref_date, half_life: float) -> pd.DataFrame:
    age = (pd.Timestamp(ref_date) - pd.to_datetime(bv.date)).dt.days.to_numpy() / 365.25
    base = 0.5 ** (age / half_life) * bv.tier.map(kappa).to_numpy()
    P = bv.P.to_numpy()
    w = {"P": np.where(P, bv.li_w.to_numpy() * base, 0.0), "N": np.where(~P, base, 0.0), "A": base}
    df = pd.DataFrame({"pid": bv.pid.to_numpy(), "P": P.astype(int)})
    for s, ws in w.items():
        df[f"vw{s}"], df[f"w{s}"], df[f"q{s}"] = bv.v.to_numpy() * ws, ws, ws ** 2
    g = df.groupby("pid").sum()
    out = pd.DataFrame(index=g.index)
    for s in "PNA":
        out[f"x_{s}"] = g[f"vw{s}"] / g[f"w{s}"].replace(0, np.nan)
        out[f"neff_{s}"] = (g[f"w{s}"] ** 2 / g[f"q{s}"].replace(0, np.nan)).fillna(0)
    out["n_P"] = g["P"]
    out["n_A"] = df.groupby("pid").size()
    return out


def role_groups(bv: pd.DataFrame, kind: str) -> pd.Series:
    if kind == "bat":
        bo = bv.groupby("pid").batting_order.median()
        return pd.cut(bo, [0, 3, 5, 8, 20], labels=["top_order", "middle_order", "finisher", "lower_order"]).astype(str)
    ps = bv.groupby("pid").pace_or_spin.agg(lambda s: s.mode().iat[0])
    death = (bv.phase == "DEATH").groupby(bv.pid).mean()
    return pd.Series(np.where(ps == "Spin", "spin", np.where(death >= .3, "pace_death", "pace_other")), index=ps.index)


def sigma2_by_group(bv: pd.DataFrame, grp: pd.Series) -> dict:
    g = bv.groupby("pid").v.agg(["var", "size"])
    g = g[g["size"] >= 50].join(grp.rename("g"))
    s = g.groupby("g").apply(lambda t: np.average(t["var"], weights=t["size"]), include_groups=False)
    allv = float(np.average(g["var"], weights=g["size"]))
    return {**s.to_dict(), "_all": allv}


# --------------------------------------------------------------------------- empirical Bayes
def eb_fit(x: pd.Series, neff: pd.Series, grp: pd.Series, sig2: dict, min_neff: float) -> dict:
    sv = grp.map(lambda g: sig2.get(g, sig2["_all"])).astype(float) / neff.replace(0, np.nan)   # σ²_g / n
    ok = x.notna() & (neff >= min_neff)
    mu = (x[ok] * neff[ok]).groupby(grp[ok]).sum() / neff[ok].groupby(grp[ok]).sum()
    mu_all = float((x[ok] * neff[ok]).sum() / neff[ok].sum())
    dev2 = (x[ok] - grp[ok].map(mu)) ** 2 - sv[ok]
    tau2 = max(float(dev2.mean()), 1e-6)
    return {"mu": mu.to_dict(), "mu_all": mu_all, "tau2": tau2, "sig2": sig2}


def eb_apply(h: dict, x: pd.Series, neff: pd.Series, grp: pd.Series) -> tuple[pd.Series, pd.Series]:
    mu = grp.map(lambda g: h["mu"].get(g, h["mu_all"])).astype(float)
    s2 = grp.map(lambda g: h["sig2"].get(g, h["sig2"]["_all"])).astype(float)
    sv = s2 / neff.replace(0, np.nan)
    shrink = (h["tau2"] / (h["tau2"] + sv)).fillna(0.0)
    post = mu + shrink * (x.fillna(mu) - mu)
    postvar = 1 / (1 / h["tau2"] + 1 / sv.fillna(np.inf))
    return post, postvar


def fit_hyper(st: pd.DataFrame, grp: pd.Series, sig2: dict, min_neff: float) -> dict:
    hyp = {s: eb_fit(st[f"x_{s}"], st[f"neff_{s}"], grp, sig2, min_neff) for s in "PNA"}
    B, Bvar = eb_apply(hyp["N"], st.x_N, st.neff_N, grp)
    r = st.x_P - B
    s2 = grp.map(lambda g: sig2.get(g, sig2["_all"])).astype(float)
    sv_r = s2 / st.neff_P.replace(0, np.nan) + Bvar
    ok = r.notna() & (st.neff_P >= min_neff)
    m_r = float(np.average(r[ok], weights=1 / sv_r[ok]))
    tau2_r = max(float(((r[ok] - m_r) ** 2 - sv_r[ok]).mean()), 0.0)
    hyp["R"] = {"m_r": m_r, "tau2_r": tau2_r}
    return hyp


def features(st: pd.DataFrame, grp: pd.Series, hyp: dict) -> pd.DataFrame:
    f = pd.DataFrame(index=st.index)
    f["post_P"], f["var_P"] = eb_apply(hyp["P"], st.x_P, st.neff_P, grp)
    f["post_A"], f["var_A"] = eb_apply(hyp["A"], st.x_A, st.neff_A, grp)
    f["B"], f["var_B"] = eb_apply(hyp["N"], st.x_N, st.neff_N, grp)
    s2 = grp.map(lambda g: hyp["P"]["sig2"].get(g, hyp["P"]["sig2"]["_all"])).astype(float)
    r = st.x_P - f.B
    sv_r = s2 / st.neff_P.replace(0, np.nan) + f.var_B
    t2 = hyp["R"]["tau2_r"]
    s_r = (t2 / (t2 + sv_r)).fillna(0.0) if t2 > 0 else pd.Series(0.0, index=st.index)
    f["resid_raw"] = r
    f["adv"] = hyp["R"]["m_r"] + s_r * (r.fillna(hyp["R"]["m_r"]) - hyp["R"]["m_r"])
    f["shrink_resid"] = s_r
    return f


MODEL_COLS = {"M1": ["post_P"], "M2": ["post_A"], "M3": ["B", "adv"]}


def wls(X: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    Xc = np.column_stack([np.ones(len(X)), X])
    W = np.sqrt(w)
    return np.linalg.lstsq(Xc * W[:, None], y * W, rcond=None)[0]


def predict(coef: np.ndarray, f: pd.DataFrame, cols: list[str]) -> pd.Series:
    return pd.Series(coef[0] + f[cols].to_numpy() @ coef[1:], index=f.index)


# --------------------------------------------------------------------------- one training fit
def train(bv_tr: pd.DataFrame, kind: str, cfg: dict, ref_date, seed: int):
    ec, mc = cfg["estimators"], cfg["metrics"]
    kappa, H = mc["tier_credibility_fallback"], mc["recency_half_life_years"]
    grp_all = role_groups(bv_tr, kind)
    sig2 = sigma2_by_group(bv_tr, grp_all)
    # inner half-split calibration (training data only)
    rng = np.random.default_rng(seed)
    mids = bv_tr.match_id.unique()
    half = set(rng.choice(mids, len(mids) // 2, replace=False))
    a, b = bv_tr[bv_tr.match_id.isin(half)], bv_tr[~bv_tr.match_id.isin(half)]
    sa, sb_ = player_stats(a, kappa, ref_date, H), player_stats(b, kappa, ref_date, H)
    ga = grp_all.reindex(sa.index).fillna("_all")
    fa = features(sa, ga, fit_hyper(sa, ga, sig2, ec["min_eb_eff_n"]))
    ids = sa.index[sa.neff_A >= 1].intersection(sb_.index[sb_.neff_P >= ec["inner_min_eff_n"]])
    coefs = {m: wls(fa.loc[ids, c].to_numpy(), sb_.loc[ids, "x_P"].to_numpy(), sb_.loc[ids, "neff_P"].to_numpy())
             for m, c in MODEL_COLS.items()}
    # full-training features
    st = player_stats(bv_tr, kappa, ref_date, H)
    g = grp_all.reindex(st.index).fillna("_all")
    hyp = fit_hyper(st, g, sig2, ec["min_eb_eff_n"])
    f = features(st, g, hyp)
    preds = pd.DataFrame({m: predict(coefs[m], f, c) for m, c in MODEL_COLS.items()})
    return {"stats": st, "grp": g, "hyp": hyp, "feat": f, "coefs": coefs, "pred": preds,
            "inner_n": len(ids), "sig2": sig2}


def wcorr(x, y, w):
    mx, my = np.average(x, weights=w), np.average(y, weights=w)
    return np.average((x - mx) * (y - my), weights=w) / np.sqrt(np.average((x - mx) ** 2, weights=w) *
                                                                np.average((y - my) ** 2, weights=w))


# --------------------------------------------------------------------------- run
def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    ec, mc = cfg["estimators"], cfg["metrics"]
    interim, out = path(cfg, "interim"), path(cfg, "outputs")
    (out / "rankings").mkdir(exist_ok=True)
    d = pd.read_parquet(interim / "rating_balls.parquet")
    rel = pd.read_pickle(interim / "reliability.pkl")
    seed = cfg["pressure"]["seed"]
    kappa, H = mc["tier_credibility_fallback"], mc["recency_half_life_years"]

    L = ["# T11 — Reliability-adjusted pressure estimators (decision D5)", "",
         "Generated by `src/estimators.py`. Selection rule pre-registered in `config.yaml` (`estimators`) "
         "before any result. Validation tables contain no player names.", "",
         "Note on T10's \"~70% better\": that compared **correlation coefficients** (batting r 0.178 vs 0.104; "
         "bowling 0.237 vs 0.136, i.e. ~3.2% vs ~1.1% of variance explained), not prediction error. "
         "Prediction error is evaluated directly below.", ""]
    summary = {}
    for kind in KINDS:
        bv = ball_values(d, kind)
        bv["season"] = pd.to_datetime(bv.date).dt.year
        tbl = pd.read_parquet(interim / f"player_{kind}.parquet")
        rows, fold_coefs = [], []
        for ts in ec["test_seasons"]:
            tr, te = bv[bv.season < ts], bv[bv.season == ts]
            ref = pd.to_datetime(tr.date).max()
            fit = train(tr, kind, cfg, ref, seed)
            st_te = player_stats(te, kappa, pd.to_datetime(te.date).max(), H)
            ids = st_te.index[(st_te.n_P >= ec["min_test_pressure_balls"])].intersection(
                fit["stats"].index[fit["stats"].neff_A >= ec["min_train_eff_n"]])
            y, w = st_te.loc[ids, "x_P"].to_numpy(), st_te.loc[ids, "neff_P"].to_numpy()
            null = np.average(fit["stats"].x_P.dropna(), weights=fit["stats"].neff_P[fit["stats"].x_P.notna()])
            mse0 = np.average((y - null) ** 2, weights=w)
            # M4 composite (ranking only)
            tb = (pm.batting if kind == "bat" else pm.bowling)(
                d[(d.year < ts)].assign(rec=pm.recency(d[d.year < ts].match_date, str(ref.date()), H)), kappa, cfg)
            wts = rel[kind]["weights"]
            z = lambda s: (s - s.loc[ids].mean()) / s.loc[ids].std()  # noqa: E731
            m4 = (wts["performance"] * z(fit["feat"].post_P.reindex(ids))
                  + wts["wpa"] * z(tb.wpa_per100_P.reindex(ids).fillna(tb.wpa_per100_P.median()))
                  + wts["consistency"] * z(tb.consistency.reindex(ids).fillna(0)))
            for m in ("M1", "M2", "M3", "M4"):
                p = (fit["pred"][m].reindex(ids).to_numpy() if m != "M4" else m4.to_numpy())
                r = {"model": m, "test_season": ts, "players": len(ids),
                     "pearson_w": wcorr(p, y, w), "spearman": pd.Series(p).corr(pd.Series(y), method="spearman")}
                if m != "M4":
                    mse = np.average((y - p) ** 2, weights=w)
                    slope = wls(p[:, None], y, w)[1]
                    r.update({"mse": mse, "mse_null": mse0, "skill": 1 - mse / mse0, "calib_slope": slope})
                rows.append(r)
            fold_coefs.append({"test_season": ts, **{f"{m}_coef": np.round(fit["coefs"][m], 3).tolist() for m in MODEL_COLS},
                               "tau2_P": fit["hyp"]["P"]["tau2"], "tau2_A": fit["hyp"]["A"]["tau2"],
                               "tau2_N": fit["hyp"]["N"]["tau2"], "tau2_resid": fit["hyp"]["R"]["tau2_r"],
                               "inner_n": fit["inner_n"]})
        res = pd.DataFrame(rows)
        pooled = res.groupby("model").apply(lambda t: pd.Series({
            "skill": 1 - (t.mse * t.players).sum() / (t.mse_null * t.players).sum() if t.mse.notna().all() else np.nan,
            "pearson_w": np.average(t.pearson_w, weights=t.players),
            "spearman": np.average(t.spearman, weights=t.players),
            "calib_slope": np.average(t.calib_slope, weights=t.players) if t.calib_slope.notna().all() else np.nan}),
            include_groups=False)
        # selection rule
        sk = res.pivot(index="test_season", columns="model", values="skill")
        m3_wins = int((sk.M3 > sk.M2).sum())
        if m3_wins >= 2 and pooled.loc["M3", "skill"] > pooled.loc["M2", "skill"]:
            chosen = "M3"
        else:
            chosen = "M1" if pooled.loc["M1", "skill"] > pooled.loc["M2", "skill"] else "M2"
        use_m4 = pooled.loc["M4", "spearman"] > pooled.loc[chosen, "spearman"]
        rule_choice = chosen
        override = (ec.get("override") or {}).get(kind)
        if override and override != chosen:
            chosen = override
        summary[kind] = {"rule_choice": rule_choice, "chosen": chosen, "use_m4": bool(use_m4)}

        name = "Batting" if kind == "bat" else "Bowling"
        L += [f"## {name}", "", "### Chronological out-of-sample results (per fold)", "",
              md_table(res.round(4), index=False, floatfmt="{:.4f}"), "",
              "### Pooled", "", md_table(pooled, floatfmt="{:.4f}"), "",
              "### Fitted calibration coefficients & EB hyper-parameters (per fold)", "",
              md_table(pd.DataFrame(fold_coefs), index=False, floatfmt="{:.5f}"), "",
              f"**Selection:** M3 beat M2 on skill in {m3_wins}/3 folds → rule selects **{rule_choice}**"
              f"{'; M4 composite has higher Spearman' if use_m4 else '; M4 composite not better on Spearman'}.",
              *([f"**Override (decision D6, disclosed):** final estimator = **{chosen}** — see `config.yaml` "
                 "`estimators.override` for the reasons."] if chosen != rule_choice else
                [f"**Final estimator: {chosen}**"]), ""]

        # ------------------------------ final fit on all data
        ref = pd.Timestamp(cfg["reference_date"])
        fit = train(bv, kind, cfg, ref, seed)
        f, st = fit["feat"], fit["stats"]
        rating = fit["pred"][chosen]
        el = rel[kind]
        ncol, mcol = ("balls_P", "pressure_innings_any") if kind == "bat" else ("legal_P", "pressure_matches_any")
        pool = tbl.index[(tbl[ncol] >= el["min_pressure_n"]) & (tbl[mcol] >= el["min_pressure_units"])
                         & tbl.active_since_2025]
        # bootstrap (match clusters), hyper-parameters and coefficients held fixed
        rng = np.random.default_rng(seed)
        mids = bv.match_id.unique()
        idx_by_match = bv.groupby("match_id").indices
        ranks = []
        for _ in range(ec["bootstrap_reps"]):
            pick = rng.choice(mids, len(mids), replace=True)
            bb = bv.iloc[np.concatenate([idx_by_match[m] for m in pick])]
            sb = player_stats(bb, kappa, ref, H).reindex(st.index)
            fb = features(sb, fit["grp"], fit["hyp"])
            pb = predict(fit["coefs"][chosen], fb, MODEL_COLS[chosen]).reindex(pool)
            ranks.append(pb.rank(ascending=False, method="min"))
        R = pd.concat(ranks, axis=1)
        out_t = pd.DataFrame({
            "display_name": tbl.display_name.reindex(pool),
            "role_group": tbl.role_group.reindex(pool),
            "baseline_ability_B": f.B.reindex(pool),
            "all_balls_value_EB": f.post_A.reindex(pool),
            "actual_pressure_value_raw": st.x_P.reindex(pool),
            "pressure_advantage_raw": f.resid_raw.reindex(pool),
            "pressure_advantage_shrunk": f.adv.reindex(pool),
            "pressure_balls": st.n_P.reindex(pool),
            "pressure_eff_n": st.neff_P.reindex(pool),
            "posterior_sd_rating": np.sqrt(f["var_A" if chosen == "M2" else ("var_P" if chosen == "M1" else "var_B")]).reindex(pool),
            "rating": rating.reindex(pool),
            "rank": rating.reindex(pool).rank(ascending=False, method="min"),
            "median_boot_rank": R.median(axis=1),
            "rank_p05": R.quantile(.05, axis=1), "rank_p95": R.quantile(.95, axis=1),
            "p_top10": (R <= 10).mean(axis=1),
            "pct_P_balls_ipl": tbl.pct_P_balls_ipl.reindex(pool),
            "M1_rank": fit["pred"].M1.reindex(pool).rank(ascending=False, method="min"),
            "M2_rank": fit["pred"].M2.reindex(pool).rank(ascending=False, method="min"),
            "M3_rank": fit["pred"].M3.reindex(pool).rank(ascending=False, method="min"),
        }).sort_values("rank")
        out_t.to_csv(out / "rankings" / f"{'batting' if kind == 'bat' else 'bowling'}_ratings.csv")
        (out / "rankings" / f"{'batting' if kind == 'bat' else 'bowling'}_top25.md").write_text(
            md_table(out_t.head(25), floatfmt="{:.3f}") + "\n", encoding="utf-8")
        top = {m: set(out_t.nsmallest(10, f"{m}_rank").index) for m in ("M1", "M2", "M3")}
        ov = pd.DataFrame([[len(top[a] & top[b]) for b in top] for a in top], index=list(top), columns=list(top))
        L += ["### Final fit (all data): top-10 overlap between estimators (count of shared players)", "",
              md_table(ov), "",
              f"- Eligible pool: {len(pool)}. Bootstrap: {ec['bootstrap_reps']} match-cluster resamples "
              "(EB hyper-parameters and calibration held fixed).",
              f"- Selected-model top 10: median P(top-10) = {out_t.head(10).p_top10.median():.2f}; "
              f"min = {out_t.head(10).p_top10.min():.2f}; mean 90% rank-interval width = "
              f"{(out_t.head(10).rank_p95 - out_t.head(10).rank_p05).mean():.1f}.", ""]
    (out / "validation" / "t11_estimators.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return summary, L


if __name__ == "__main__":
    run()
