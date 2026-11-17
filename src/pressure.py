"""T7 — Pressure labelling (planning/03).

For every innings-1/2 delivery (state *before* the ball):
  * Leverage index (model A):
        Swing(s) = Σ_o p(o | ctx) · |WP(s ⊕ o) − Σ_o' p(o' | ctx) WP(s ⊕ o')|
                   (mean absolute spread of next-ball WP),  o ∈ {0,1,2,3,4,6 runs, wicket}
        LI(s)    = Swing(s) / mean Swing over legal balls of decided matches
    p(o | ctx) = empirical outcome mix by (comp group, innings, phase, wickets-in-hand bin).
  * WPA (batting side) = wp_after − wp_before (from T6).
  * Rule-based Pressure Index PI (model B, cross-check; planning/03 §4).
  * Pressure tier: Low / Moderate / High / Extreme on LI quantiles within IPL and non-IPL.
  * Situation flags S1–S6 (planning/03 §6; descriptive only).

Outputs: data_interim/pressure.parquet, outputs/validation/pressure_validation.md,
         outputs/figures/pressure_*.png
"""
from __future__ import annotations

import pickle

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

import models_par  # noqa: E402,F401  (unpickling)
import models_wp  # noqa: E402
from common import load_config, md_table, path  # noqa: E402

OUTCOMES = [("r0", 0, 0), ("r1", 1, 0), ("r2", 2, 0), ("r3", 3, 0), ("r4", 4, 0), ("r6", 6, 0), ("wkt", 0, 1)]
TIERS = ["Low", "Moderate", "High", "Extreme"]


# --------------------------------------------------------------------------- WP of hypothetical states
def wp_chase(models, runs_needed, balls_rem, wih, env_par, ball_limit):
    """Chasing side WP with terminal states handled exactly."""
    rn, br, w = (np.asarray(x, float) for x in (runs_needed, balls_rem, wih))
    out = np.full(len(rn), np.nan)
    won, tie = rn <= 0, (rn == 1) & ((br <= 0) | (w <= 0))
    lost = ~won & ~tie & ((br <= 0) | (w <= 0))
    live = ~(won | tie | lost)
    out[won], out[tie], out[lost] = 1.0, 0.5, 0.0
    if live.any():
        d = pd.DataFrame({"runs_needed": rn[live], "balls_rem": br[live], "wih": w[live],
                          "env_par": np.asarray(env_par, float)[live],
                          "ball_limit": np.asarray(ball_limit, float)[live]})
        out[live] = models["wp"][2].predict(models_wp.add_features(d, models["err"], 2))
    return out


def wp_first(models, score, balls_rem, wih, env_par, ball_limit):
    """Batting-first side WP; at innings end → 1 − chase WP at the start of the chase."""
    s, br, w = (np.asarray(x, float) for x in (score, balls_rem, wih))
    env, lim = np.asarray(env_par, float), np.asarray(ball_limit, float)
    out = np.full(len(s), np.nan)
    end = (br <= 0) | (w <= 0)
    if end.any():
        out[end] = 1 - wp_chase(models, s[end] + 1, lim[end], np.full(end.sum(), 10.0), env[end], lim[end])
    if (~end).any():
        d = pd.DataFrame({"score": s[~end], "balls_rem": br[~end], "wih": w[~end],
                          "env_par": env[~end], "ball_limit": lim[~end]})
        out[~end] = models["wp"][1].predict(models_wp.add_features(d, models["err"], 1))
    return out


# --------------------------------------------------------------------------- leverage
def outcome_probs(b: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Empirical outcome mix per context, estimated on legal balls."""
    bins = cfg["pressure"]["outcome_context_wih_bins"]
    lg = b[b.is_legal & (b.innings <= 2)].copy()
    lg["o"] = np.select([lg.is_wicket, lg.total_runs >= 6, lg.total_runs >= 4, lg.total_runs == 3,
                         lg.total_runs == 2, lg.total_runs == 1], ["wkt", "r6", "r4", "r3", "r2", "r1"], "r0")
    lg["wbin"] = pd.cut(lg.wickets_in_hand, bins).astype(str)
    p = pd.crosstab([lg.is_ipl, lg.innings, lg.phase, lg.wbin], lg.o, normalize="index")
    return p.reindex(columns=[o for o, _, _ in OUTCOMES], fill_value=0.0)


def leverage(b: pd.DataFrame, env: pd.DataFrame, models: dict, cfg: dict) -> pd.DataFrame:
    bins = cfg["pressure"]["outcome_context_wih_bins"]
    d = b[b.innings <= 2].merge(env[["tier", "year", "env_par"]], on=["tier", "year"], how="left")
    d["wbin"] = pd.cut(d.wickets_in_hand, bins).astype(str)
    probs = outcome_probs(b, cfg)
    P = probs.reindex(pd.MultiIndex.from_frame(d[["is_ipl", "innings", "phase", "wbin"]])).to_numpy()
    P = np.nan_to_num(P, nan=0.0)

    swing = np.zeros(len(d))
    wp0 = np.full(len(d), np.nan)
    for inn in (1, 2):
        ix = np.flatnonzero(d.innings.to_numpy() == inn)
        x = d.iloc[ix]
        br, w, env_par, lim = (x.balls_rem_before.to_numpy(float), x.wickets_in_hand.to_numpy(float),
                               x.env_par.to_numpy(float), x.ball_limit.to_numpy(float))
        if inn == 2:
            rn = x.runs_needed_before.to_numpy(float)
            base = wp_chase(models, rn, br, w, env_par, lim)
            alt = [wp_chase(models, rn - r, br - 1, w - k, env_par, lim) for _, r, k in OUTCOMES]
        else:
            s = x.score_before.to_numpy(float)
            base = wp_first(models, s, br, w, env_par, lim)
            alt = [wp_first(models, s + r, br - 1, w - k, env_par, lim) for _, r, k in OUTCOMES]
        # Spread of next-ball WP around its expectation (mean absolute deviation). Measuring the
        # spread rather than |WP_o − WP(s)| keeps LI immune to the small seam between the
        # first-innings and chase models at innings end (continuity gap, T6).
        exp_next = sum(P[ix, j] * a for j, a in enumerate(alt))
        swing[ix] = sum(P[ix, j] * np.abs(a - exp_next) for j, a in enumerate(alt))
        wp0[ix] = base
    d["swing"], d["wp_state"] = swing, wp0
    unrel = (d.innings == 2) & ~d.target_reliable
    d.loc[unrel, ["swing", "wp_state"]] = np.nan
    ref = d.loc[d.is_legal & d.batting_side_won.notna(), "swing"].mean()
    d["li"] = d["swing"] / ref
    return d


# --------------------------------------------------------------------------- rule-based PI
def rule_pi(d: pd.DataFrame, models: dict, cfg: dict) -> pd.Series:
    pc = cfg["pressure"]
    w1, w2, w3 = pc["pi_weights"]
    lo, hi = pc["alive_wp"]
    alive = d.wp_state.between(lo, hi).astype(float)
    time = 1 - d.balls_rem_before / 120
    # chase
    crr = d.crr_before.fillna(d.rrr_before)
    rrr_gap = ((d.rrr_before - crr) / 6).clip(-1, 2)
    wk_press = (d.runs_needed_before / d.wickets_in_hand.clip(lower=1) / 25).clip(0, 2)
    pi_chase = alive * (w1 * rrr_gap + w2 * wk_press + w3 * time)
    # first innings: runs below the par path, standardised by bucket of balls bowled
    par_limit = models["err"].predict(d.ball_limit, 10, d.env_par)
    expected_so_far = par_limit - models["err"].predict(d.balls_rem_before, 10, d.env_par)
    gap = expected_so_far - d.score_before
    sd = gap.groupby((d.legal_before // 12)).transform("std").replace(0, np.nan)
    par_gap = (gap / sd).clip(-1, 2)
    collapse = d.wkts_last18.clip(upper=3) / 3
    pi_first = alive * (w1 * par_gap + w2 * collapse + w3 * time * (d.wkts_before >= 4))
    return pd.Series(np.where(d.innings == 2, pi_chase, pi_first), index=d.index)


# --------------------------------------------------------------------------- tiers & situations
def assign_tiers(d: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    qs = cfg["pressure"]["tier_quantiles"]
    ref = d[d.is_legal & d.batting_side_won.notna() & d.li.notna()]
    cuts = ref.groupby("is_ipl").li.quantile(qs).unstack()
    cuts.columns = [f"P{int(q*100)}" for q in qs]
    d["pressure_tier"] = pd.NA
    for grp, c in cuts.iterrows():
        m = (d.is_ipl == grp) & d.li.notna()
        d.loc[m, "pressure_tier"] = pd.cut(d.loc[m, "li"], [-np.inf, *c.to_list(), np.inf], labels=TIERS,
                                           right=False).astype(str)
    d["is_pressure"] = d.pressure_tier.isin(["High", "Extreme"])
    cap = ref.li.quantile(cfg["pressure"]["li_cap_quantile"])
    d["li_weight"] = d.li.clip(upper=cap)
    cuts["li_cap"] = cap
    return d, cuts


def situations(d: pd.DataFrame, models: dict) -> pd.DataFrame:
    inn2, death = d.innings == 2, d.overid >= 16
    d["S1_tight_chase_death"] = inn2 & death & d.rrr_before.between(8, 14) & d.wp_state.between(.15, .85)
    d["S2_after_collapse"] = d.wkts_last18 >= 2
    d["S3_steep_chase"] = inn2 & (d.rrr_before >= 10) & (d.balls_rem_before >= 30) & (d.wp_state >= .10)
    # Bowling side defending a live total late in the chase (WP band, not a run-rate rule)
    d["S4_defending_close"] = inn2 & (d.overid >= 13) & d.wp_state.between(.2, .8)
    par_limit = models["err"].predict(d.ball_limit, 10, d.env_par)
    expected_so_far = par_limit - models["err"].predict(d.balls_rem_before, 10, d.env_par)
    d["S5_first_inns_death_below_par"] = (d.innings == 1) & death & (d.score_before < expected_so_far)
    d["S6_knockout"] = d.knock_out.astype(bool)
    return d


# --------------------------------------------------------------------------- validation
def cluster_boot_rates(x: pd.DataFrame, reps: int, seed: int) -> pd.DataFrame:
    """Per-tier rates with 95% match-cluster bootstrap CIs."""
    g = x.groupby(["match_id", "pressure_tier"]).agg(
        n=("is_legal", "size"), runs=("runs", "sum"), dots=("is_bat_dot", "sum"),
        bnd=("is_boundary", "sum"), outs=("is_batter_dismissal", "sum")).reset_index()
    mids = g.match_id.unique()
    rng = np.random.default_rng(seed)

    def rates(gg):
        t = gg.groupby("pressure_tier")[["n", "runs", "dots", "bnd", "outs"]].sum()
        return pd.DataFrame({"runs_per_ball": t.runs / t.n, "dot_pct": 100 * t.dots / t.n,
                             "boundary_pct": 100 * t.bnd / t.n, "dismissal_pct": 100 * t.outs / t.n})

    point = rates(g)
    idx = g.groupby("match_id").indices
    boots = []
    for _ in range(reps):
        pick = rng.choice(mids, len(mids), replace=True)
        boots.append(rates(g.iloc[np.concatenate([idx[m] for m in pick])]))
    B = pd.concat(boots, keys=range(reps))
    lo = B.groupby(level=1).quantile(.025)
    hi = B.groupby(level=1).quantile(.975)
    out = point.copy().astype(object)
    for c in point.columns:
        out[c] = [f"{point.loc[t, c]:.2f} [{lo.loc[t, c]:.2f}, {hi.loc[t, c]:.2f}]" for t in point.index]
    out.insert(0, "balls", g.groupby("pressure_tier").n.sum())
    return out.reindex(TIERS)


def cohen_kappa(a: np.ndarray, b: np.ndarray) -> float:
    po = np.mean(a == b)
    pe = np.mean(a) * np.mean(b) + (1 - np.mean(a)) * (1 - np.mean(b))
    return float((po - pe) / (1 - pe))


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    pc = cfg["pressure"]
    interim, out = path(cfg, "interim"), path(cfg, "outputs")
    with open(interim / "models" / "wp.pkl", "rb") as fh:
        models = pickle.load(fh)
    bs = pd.read_parquet(interim / "ball_state.parquet")
    env = pd.read_parquet(interim / "env_par.parquet")
    wp = pd.read_parquet(interim / "wp.parquet")

    d = leverage(bs, env, models, cfg)
    d = d.merge(wp[["match_id", "innings", "innings_ball_num", "wp_before", "wp_after"]],
                on=["match_id", "innings", "innings_ball_num"], how="left")
    d["wpa_bat"] = d.wp_after - d.wp_before
    d["pi"] = rule_pi(d, models, cfg)
    d, cuts = assign_tiers(d, cfg)
    d = situations(d, models)

    keep = ["match_id", "innings", "innings_ball_num", "is_ipl", "tier", "year", "phase", "overid",
            "wp_state", "wp_before", "wp_after", "wpa_bat", "swing", "li", "li_weight", "pressure_tier",
            "is_pressure", "pi"] + [c for c in d.columns if c[:2] in {"S1", "S2", "S3", "S4", "S5", "S6"}]
    d[keep].to_parquet(interim / "pressure.parquet", index=False)

    # ------------------------------ validation
    ref = d[d.is_legal & d.batting_side_won.notna() & d.li.notna()].copy()
    L = ["# T7 — Pressure labelling & construct validation", "",
         "Generated by `src/pressure.py`. Reference set = legal balls of decided matches with a WP estimate "
         f"(n = {len(ref):,}). LI = expected |ΔWP| of the next ball ÷ its mean.", "",
         "## Tier cut-points (LI quantiles within IPL / non-IPL)", "", md_table(cuts, floatfmt="{:.3f}"), ""]

    # Outcome relevance
    ref["abs_wpa"] = ref.wpa_bat.abs()
    top25 = ref.is_pressure
    share = ref.loc[top25, "abs_wpa"].sum() / ref.abs_wpa.sum()
    L += ["## 1. Outcome relevance", "",
          f"- High + Extreme balls are **{top25.mean():.1%}** of balls but carry **{share:.1%}** of all "
          "realised win-probability movement (|WPA|).",
          f"- Extreme alone: {ref.pressure_tier.eq('Extreme').mean():.1%} of balls, "
          f"{ref.loc[ref.pressure_tier.eq('Extreme'), 'abs_wpa'].sum() / ref.abs_wpa.sum():.1%} of |WPA|.", ""]
    # Separation
    L += ["## 2. Separation: league outcomes by pressure tier (95% match-cluster bootstrap CI)", "",
          "Batting outcomes on legal balls; runs = runs off the bat.", ""]
    for inn in (1, 2):
        L += [f"### Innings {inn} — raw rates", "",
              md_table(cluster_boot_rates(ref[ref.innings == inn], pc["bootstrap_reps"], pc["seed"])), ""]
    # Context-adjusted: actual − expected, expectation = league mean in the same
    # (comp group, innings, phase, wickets-in-hand bin). Removes the phase/wickets mix of each tier.
    bins = pc["outcome_context_wih_bins"]
    ref["wbin"] = pd.cut(ref.wickets_in_hand, bins).astype(str)
    ctx = ["is_ipl", "innings", "phase", "wbin"]
    for col in ("runs", "is_bat_dot", "is_boundary", "is_batter_dismissal"):
        ref[f"{col}_res"] = ref[col].astype(float) - ref.groupby(ctx)[col].transform("mean")
    adj = ref.copy()
    adj["runs"], adj["is_bat_dot"], adj["is_boundary"], adj["is_batter_dismissal"] = (
        adj.runs_res, adj.is_bat_dot_res, adj.is_boundary_res, adj.is_batter_dismissal_res)
    L += ["### Context-adjusted (actual − expected for the same innings × phase × wickets-in-hand; "
          "positive = above normal)", "",
          "Units: runs per ball; percentage points for dot / boundary / dismissal.", ""]
    for inn in (1, 2):
        L += [f"#### Innings {inn}", "",
              md_table(cluster_boot_rates(adj[adj.innings == inn], pc["bootstrap_reps"], pc["seed"])), ""]
    # Where pressure happens
    ph = pd.crosstab([ref.innings, ref.phase], ref.pressure_tier, normalize="index").reindex(columns=TIERS) * 100
    L += ["## 3. Where pressure occurs (% of balls in each tier by innings × phase)", "",
          md_table(ph, floatfmt="{:.1f}"), ""]
    death = ref[ref.phase == "DEATH"]
    L += [f"- Death-over balls classified **Low** leverage: {death.pressure_tier.eq('Low').mean():.1%}; "
          f"middle-over balls classified High/Extreme: {ref[ref.phase=='MID'].is_pressure.mean():.1%}.", ""]
    # Convergence with rule-based PI
    conv = []
    for inn in (1, 2):
        x = ref[(ref.innings == inn) & ref.pi.notna()]
        rho = spearmanr(x.li, x.pi).statistic
        share = x.is_pressure.mean()           # match base rates so kappa is not deflated
        pi_top = (x.pi >= x.pi.quantile(1 - share)).to_numpy()
        conv.append({"innings": inn, "n": len(x), "spearman_LI_PI": rho,
                     "pressure_share": share,
                     "kappa_same_share": cohen_kappa(x.is_pressure.to_numpy(), pi_top)})
    L += ["## 4. Convergence with the rule-based Pressure Index (model B)", "",
          md_table(pd.DataFrame(conv), index=False, floatfmt="{:.3f}"), "",
          "Interpretation threshold set in planning/03 §4: Spearman < 0.4 ⇒ explain disagreement.", ""]
    # Situations
    sit_cols = [c for c in d.columns if c.startswith("S") and c[1].isdigit()]
    sit = pd.DataFrame({c: {"balls": int(ref[c].sum()), "share_high_extreme_%": 100 * ref.loc[ref[c], "is_pressure"].mean(),
                            "mean_LI": ref.loc[ref[c], "li"].mean()} for c in sit_cols}).T
    L += ["## 5. Situation flags S1–S6 (descriptive)", "", md_table(sit, floatfmt="{:.2f}"), ""]
    # Face validity (state only; no player names)
    rng = np.random.default_rng(pc["seed"])
    cols = ["match_id", "innings", "overid", "score_before", "wkts_before", "runs_needed_before",
            "balls_rem_before", "wp_state", "li", "pressure_tier"]
    ext = ref[ref.pressure_tier == "Extreme"]
    lowd = ref[(ref.phase == "DEATH") & (ref.pressure_tier == "Low")]
    L += ["## 6. Face validity (random samples, seed fixed)", "", "### 10 Extreme-leverage balls", "",
          md_table(ext.iloc[rng.choice(len(ext), 10, replace=False)][cols], index=False, floatfmt="{:.2f}"), "",
          "### 10 Low-leverage death-over balls", "",
          md_table(lowd.iloc[rng.choice(len(lowd), 10, replace=False)][cols], index=False, floatfmt="{:.2f}"), "",
          "![LI by phase](../figures/pressure_li_by_phase.png)", ""]

    # Figure: LI distribution by innings × phase
    fig, ax = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for a, inn in zip(ax, (1, 2)):
        data = [ref[(ref.innings == inn) & (ref.phase == p)].li.clip(upper=6) for p in ("PP", "MID", "DEATH")]
        a.boxplot(data, tick_labels=["Powerplay", "Middle", "Death"], showfliers=False, whis=(5, 95))
        for q, ls in zip(cuts.loc[True, ["P75", "P90"]], ("--", ":")):
            a.axhline(q, color="crimson", ls=ls, lw=1)
        a.set(title=f"Innings {inn}: leverage index by phase", ylabel="LI (1 = average ball)")
        a.grid(alpha=.3, axis="y")
    fig.text(.5, -.02, "Boxes: IQR; whiskers 5–95th pct. Red lines: IPL High (P75, dashed) and Extreme (P90, dotted) cut-points.",
             ha="center", fontsize=8)
    fig.tight_layout(); fig.savefig(out / "figures" / "pressure_li_by_phase.png", dpi=130, bbox_inches="tight")
    plt.close(fig)

    (out / "validation" / "pressure_validation.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return d, L


if __name__ == "__main__":
    run()
