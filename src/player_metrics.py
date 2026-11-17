"""T9 — Player-level pressure metrics (planning/04 §3–7).

Per player, separately for batting and bowling, on pressure balls (P = High/Extreme) and
non-pressure balls (N = Low/Moderate):

  weights  ω_P = li_weight · recency · κ_tier       ω_N = recency · κ_tier
  batting  rv  = (runs − E[runs]) − λ·(out − E[out])        (+ −λ for non-striker run-outs)
  bowling  bv  = (E[conc] − conc) + λ·(wkt − E[wkt])

Also WPA, descriptive rates, per-match consistency, opportunity counts, role group,
tier mix, recency and provisional eligibility.

Tier credibility κ: estimated from "bridging" players (enough balls in IPL and in another
tier): κ_x = corr(IPL value, tier-x value) / corr(IPL odd-match value, IPL even-match value),
with a player-bootstrap 90% CI. If the CI is wider than 0.5 or fewer than 15 bridging
players exist, the pre-registered fallback discounts in config.yaml are used.

**No leaderboards are produced here** — weights are locked and ranking happens in T11.
Outputs: data_interim/player_bat.parquet, data_interim/player_bowl.parquet,
         outputs/validation/player_metrics_checks.md
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import load_config, md_table, path

TIER_GROUP = {"T1_IPL": "T1", "T2_T20I_TOP": "T2", "T3_T20I_OTHER": "T34", "T4_A_TEAM": "T34"}


# --------------------------------------------------------------------------- helpers
def recency(dates: pd.Series, ref: str, half_life: float) -> np.ndarray:
    age = (pd.Timestamp(ref) - pd.to_datetime(dates)).dt.days / 365.25
    return 0.5 ** (age.to_numpy() / half_life)


def wmean(df: pd.DataFrame, key: str, w: str, cols: list[str], extra_num: pd.DataFrame | None = None):
    """Weighted means of cols by key; extra_num adds to numerators (not denominators)."""
    g = df.assign(**{f"_{c}": df[c] * df[w] for c in cols}).groupby(key)
    out = pd.DataFrame({"wsum": g[w].sum(), "w2": g[w].apply(lambda s: (s ** 2).sum())})
    for c in cols:
        num = g[f"_{c}"].sum()
        if extra_num is not None and c in extra_num.columns:
            num = num.add(extra_num[c], fill_value=0)
        out[c] = num / out.wsum
    out["eff_n"] = out.wsum ** 2 / out.w2
    return out.drop(columns="w2")


# --------------------------------------------------------------------------- tier credibility
def tier_credibility(rows: pd.DataFrame, pid: str, val: str, unit_min: dict, seed: int, reps: int = 1000):
    """Return table of κ estimates for T2 and T34 relative to IPL (T1)."""
    rows = rows.assign(tg=rows.tier.map(TIER_GROUP))
    per = rows.groupby([pid, "tg"])[val].agg(["mean", "size"]).unstack()
    t1 = rows[rows.tg == "T1"]
    par = t1.assign(h=(t1.match_id % 2)).groupby([pid, "h"])[val].agg(["mean", "size"]).unstack()
    ref_ok = (par[("size", 0)] >= unit_min["ref"]) & (par[("size", 1)] >= unit_min["ref"])
    ref_a, ref_b = par.loc[ref_ok, ("mean", 0)], par.loc[ref_ok, ("mean", 1)]
    rng = np.random.default_rng(seed)
    out = []
    for tg in ("T2", "T34"):
        ok = (per[("size", "T1")] >= unit_min["T1"]) & (per[("size", tg)] >= unit_min[tg])
        x, y = per.loc[ok, ("mean", tg)], per.loc[ok, ("mean", "T1")]
        n = int(ok.sum())
        if n < 5 or ref_ok.sum() < 5:
            out.append({"tier": tg, "bridging_players": n, "kappa": np.nan, "ci90_lo": np.nan, "ci90_hi": np.nan})
            continue
        r_ref = np.corrcoef(ref_a, ref_b)[0, 1]
        k_hat = np.corrcoef(x, y)[0, 1] / r_ref
        boots = []
        xa, ya, ra, rb = x.to_numpy(), y.to_numpy(), ref_a.to_numpy(), ref_b.to_numpy()
        for _ in range(reps):
            i = rng.integers(0, len(xa), len(xa)); j = rng.integers(0, len(ra), len(ra))
            rr = np.corrcoef(ra[j], rb[j])[0, 1]
            boots.append(np.corrcoef(xa[i], ya[i])[0, 1] / rr if rr > 0 else np.nan)
        lo, hi = np.nanpercentile(boots, [5, 95])
        out.append({"tier": tg, "bridging_players": n, "ref_players": int(ref_ok.sum()), "r_ref": r_ref,
                    "kappa": k_hat, "ci90_lo": lo, "ci90_hi": hi})
    return pd.DataFrame(out)


def choose_kappa(tbl: pd.DataFrame, fallback: dict) -> tuple[dict, str]:
    usable = tbl.dropna(subset=["kappa"])
    stable = (len(usable) == 2 and (usable.ci90_hi - usable.ci90_lo).max() <= 0.5
              and (usable.bridging_players >= 15).all())
    if not stable:
        return dict(fallback), "fallback (bridging estimate unstable: CI width > 0.5 or < 15 players)"
    k = {r.tier: float(np.clip(r.kappa, 0, 1)) for r in usable.itertuples()}
    return {"T1_IPL": 1.0, "T2_T20I_TOP": k["T2"], "T3_T20I_OTHER": k["T34"], "T4_A_TEAM": k["T34"]}, "estimated"


# --------------------------------------------------------------------------- per-match consistency
def match_consistency(P: pd.DataFrame, pid: str, val: str, wpa: str, min_balls: int) -> pd.DataFrame:
    g = P.groupby([pid, "match_id"]).agg(n=(val, "size"), v=(val, "sum"), w=(wpa, "sum"))
    g = g[g.n >= min_balls]
    g["vpb"] = g.v / g.n
    res = g.groupby(pid).agg(press_units=("n", "size"), success_rate=("v", lambda s: (s > 0).mean()),
                             vpb_sd=("vpb", "std"))
    fail = g.assign(f=(g.v < 0) & (g.w < 0)).groupby(pid).f.mean()
    res["failure_rate"] = fail
    res["consistency"] = res.success_rate - res.failure_rate
    return res


# --------------------------------------------------------------------------- batting
def batting(d: pd.DataFrame, kappa: dict, cfg: dict) -> pd.DataFrame:
    mc = cfg["metrics"]
    f = d[d.is_ball_faced].copy()
    f["kap"] = f.tier.map(kappa)
    f["wN"] = f.rec * f.kap
    f["wP"] = f.li_weight * f.rec * f.kap
    f["rv"] = (f.runs - f.e_runs) - f.lam * (f.out_striker - f.e_out)
    f["rae"] = f.runs - f.e_runs
    f["dae"] = f.out_striker - f.e_out
    P, N = f[f.is_pressure], f[~f.is_pressure]

    # non-striker run-outs: −λ on the dismissed non-striker (no ball faced)
    ns = d[d.out_nonstriker == 1].copy()
    ns["kap"] = ns.tier.map(kappa)
    ns_pen = lambda m, wcol: (ns[m].assign(v=-ns[m].lam * ns[m].rec * ns[m].kap *   # noqa: E731
                                           (ns[m].li_weight if wcol == "wP" else 1))
                              .groupby("non_striker_id").v.sum().rename("rv").to_frame()
                              .rename_axis("striker_id"))
    pen_P, pen_N = ns_pen(ns.is_pressure, "wP"), ns_pen(~ns.is_pressure, "wN")

    wp_ = wmean(P, "striker_id", "wP", ["rv", "rae", "dae"], pen_P).add_suffix("_P")
    wn_ = wmean(N, "striker_id", "wN", ["rv", "rae", "dae"], pen_N).add_suffix("_N")

    def raw(x, suf):
        g = x.groupby("striker_id")
        r = pd.DataFrame({"balls": g.size(), "runs": g.runs.sum(), "outs": g.out_striker.sum(),
                          "dots": g.is_bat_dot.sum(), "bnd": g.is_boundary.sum(),
                          "wpa_sum": (x.wpa_bat * x.rec * x.kap).groupby(x.striker_id).sum(),
                          "wpa_w": (x.rec * x.kap).groupby(x.striker_id).sum()})
        r["sr"] = 100 * r.runs / r.balls
        r["dot_pct"] = 100 * r.dots / r.balls
        r["bnd_pct"] = 100 * r.bnd / r.balls
        r["runs_per_dismissal"] = r.runs / r.outs.replace(0, np.nan)
        r["wpa_per100"] = 100 * r.wpa_sum / r.wpa_w
        return r.drop(columns=["wpa_sum", "wpa_w"]).add_suffix(suf)

    t = pd.concat([raw(P, "_P"), raw(N, "_N"), wp_, wn_], axis=1)
    t["delta_rv"] = t.rv_P - t.rv_N
    # chase-specific
    Pc = P[P.innings == 2]
    t["wpa_per100_P_chase"] = 100 * (Pc.wpa_bat * Pc.rec * Pc.kap).groupby(Pc.striker_id).sum() / \
        (Pc.rec * Pc.kap).groupby(Pc.striker_id).sum()
    last = d[d.innings == 2].sort_values("innings_ball_num").groupby("match_id").tail(1)
    won = last[last.batting_side_won == 1]
    fin = pd.concat([won.striker_id, won.non_striker_id]).value_counts()
    t["chases_finished_not_out"] = fin.reindex(t.index).fillna(0).astype(int)
    # pace / spin split of pressure value
    for ps in ("Pace", "Spin"):
        x = P[P.pace_or_spin == ps]
        t[f"rv_P_vs_{ps.lower()}"] = (x.rv * x.wP).groupby(x.striker_id).sum() / x.wP.groupby(x.striker_id).sum()
        t[f"balls_P_vs_{ps.lower()}"] = x.groupby("striker_id").size()
    # consistency
    P_unw = P.assign(v=P.rv)
    t = t.join(match_consistency(P_unw, "striker_id", "v", "wpa_bat", mc["min_pressure_balls_innings"]))
    # opportunity & context
    t["pressure_innings_any"] = P.groupby("striker_id").match_id.nunique()
    t["matches_batted"] = f.groupby("striker_id").match_id.nunique()
    t["pct_P_balls_ipl"] = 100 * P.groupby("striker_id").is_ipl.mean()
    t["pct_P_balls_T34"] = 100 * P.tier.isin(["T3_T20I_OTHER", "T4_A_TEAM"]).groupby(P.striker_id).mean()
    t["pct_P_balls_chase"] = 100 * (P.innings == 2).groupby(P.striker_id).mean()
    t["last_date"] = f.groupby("striker_id").match_date.max()
    bo = f.groupby("striker_id").batting_order.median()
    t["role_group"] = pd.cut(bo, [0, 3, 5, 8, 20], labels=["top_order", "middle_order", "finisher", "lower_order"]).astype(str)
    return t.rename_axis("player_id")


# --------------------------------------------------------------------------- bowling
def bowling(d: pd.DataFrame, kappa: dict, cfg: dict) -> pd.DataFrame:
    mc = cfg["metrics"]
    b = d.copy()
    b["kap"] = b.tier.map(kappa)
    b["wN"] = b.rec * b.kap
    b["wP"] = b.li_weight * b.rec * b.kap
    b["bv"] = (b.e_conc - b.bowler_runs) + b.lam * (b.is_bowler_wicket - b.e_wkt)
    b["rs"] = b.e_conc - b.bowler_runs
    b["wae"] = b.is_bowler_wicket - b.e_wkt
    b["wpa_bowl"] = -b.wpa_bat
    b["legal"] = b.is_legal.astype(float)
    P, N = b[b.is_pressure], b[~b.is_pressure]

    def raw(x, suf):
        g = x.groupby("bowler_id")
        r = pd.DataFrame({"deliveries": g.size(), "legal": g.legal.sum(), "conc": g.bowler_runs.sum(),
                          "wkts": g.is_bowler_wicket.sum(), "dots": g.is_bowler_dot.sum(),
                          "bnd": g.is_boundary.sum(), "extras": g.is_extra.sum(),
                          "wpa_sum": (x.wpa_bowl * x.rec * x.kap).groupby(x.bowler_id).sum()})
        r["econ"] = 6 * r.conc / r.legal
        r["balls_per_wkt"] = r.legal / r.wkts.replace(0, np.nan)
        r["dot_pct"] = 100 * r.dots / r.legal
        r["bnd_pct"] = 100 * r.bnd / r.legal
        r["extras_per_over"] = 6 * r.extras / r.legal
        w = (x.rec * x.kap * x.legal).groupby(x.bowler_id).sum()
        r["wpa_per100"] = 100 * r.wpa_sum / w
        return r.drop(columns="wpa_sum").add_suffix(suf)

    t = pd.concat([raw(P, "_P"), raw(N, "_N"),
                   wmean(P, "bowler_id", "wP", ["bv", "rs", "wae"]).add_suffix("_P"),
                   wmean(N, "bowler_id", "wN", ["bv", "rs", "wae"]).add_suffix("_N")], axis=1)
    t["delta_bv"] = t.bv_P - t.bv_N
    Pd = P[P.phase == "DEATH"]
    t["bv_P_death"] = (Pd.bv * Pd.wP).groupby(Pd.bowler_id).sum() / Pd.wP.groupby(Pd.bowler_id).sum()
    t["legal_P_death"] = Pd.groupby("bowler_id").legal.sum()
    t = t.join(match_consistency(P.assign(v=P.bv), "bowler_id", "v", "wpa_bowl", mc["min_pressure_balls_spell"]))
    t["pressure_matches_any"] = P.groupby("bowler_id").match_id.nunique()
    t["matches_bowled"] = b.groupby("bowler_id").match_id.nunique()
    t["pct_P_balls_ipl"] = 100 * P.groupby("bowler_id").is_ipl.mean()
    t["pct_P_balls_T34"] = 100 * P.tier.isin(["T3_T20I_OTHER", "T4_A_TEAM"]).groupby(P.bowler_id).mean()
    t["pct_P_balls_defending"] = 100 * (P.innings == 2).groupby(P.bowler_id).mean()
    t["last_date"] = b.groupby("bowler_id").match_date.max()
    ps = b.groupby("bowler_id").pace_or_spin.agg(lambda s: s.mode().iat[0])
    death_share = (b.phase == "DEATH").groupby(b.bowler_id).mean()
    pp_share = (b.phase == "PP").groupby(b.bowler_id).mean()
    t["pace_or_spin"] = ps
    t["death_share"] = death_share
    # build as an index-aligned Series (a bare np.where array would be assigned positionally)
    role = pd.Series(np.where(ps == "Spin", "spin",
                              np.where(death_share.reindex(ps.index) >= 0.30, "pace_death",
                                       np.where(pp_share.reindex(ps.index) >= 0.40, "pace_powerplay", "pace_other"))),
                     index=ps.index)
    t["role_group"] = role.reindex(t.index)
    return t.rename_axis("player_id")


# --------------------------------------------------------------------------- run
def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    mc, el = cfg["metrics"], cfg["eligibility_provisional"]
    interim, out = path(cfg, "interim"), path(cfg, "outputs")
    d = pd.read_parquet(interim / "rating_balls.parquet")
    players = pd.read_parquet(interim / "players.parquet")
    d["rec"] = recency(d.match_date, cfg["reference_date"], mc["recency_half_life_years"])

    # ---- tier credibility from bridging players (all balls, unweighted context-adjusted value)
    f = d[d.is_ball_faced].assign(v=lambda x: (x.runs - x.e_runs) - x.lam * (x.out_striker - x.e_out))
    bw = d.assign(v=lambda x: (x.e_conc - x.bowler_runs) + x.lam * (x.is_bowler_wicket - x.e_wkt))
    seed = cfg["pressure"]["seed"]
    kt_bat = tier_credibility(f, "striker_id", "v", {"T1": 300, "T2": 200, "T34": 150, "ref": 150}, seed)
    kt_bowl = tier_credibility(bw, "bowler_id", "v", {"T1": 300, "T2": 200, "T34": 150, "ref": 150}, seed)
    k_bat, how_bat = choose_kappa(kt_bat, mc["tier_credibility_fallback"])
    k_bowl, how_bowl = choose_kappa(kt_bowl, mc["tier_credibility_fallback"])

    bat = batting(d, k_bat, cfg)
    bowl = bowling(d, k_bowl, cfg)
    active = players.set_index("player_id").active_since_cutoff
    for t, kind in ((bat, "bat"), (bowl, "bowl")):
        t["display_name"] = players.set_index("player_id").display_name.reindex(t.index)
        t["active_since_2025"] = active.reindex(t.index).fillna(False)
    bat["eligible_provisional"] = ((bat.balls_P >= el["bat_min_pressure_balls"])
                                   & (bat.pressure_innings_any >= el["bat_min_pressure_innings"])
                                   & bat.active_since_2025)
    bowl["eligible_provisional"] = ((bowl.legal_P >= el["bowl_min_pressure_balls"])
                                    & (bowl.pressure_matches_any >= el["bowl_min_pressure_matches"])
                                    & bowl.active_since_2025)
    bat.to_parquet(interim / "player_bat.parquet")
    bowl.to_parquet(interim / "player_bowl.parquet")

    # ---- checks (aggregates only — no player names / leaderboards)
    fa = d[d.is_ball_faced]
    L = ["# T9 — Player metrics: checks (no rankings)", "",
         "Generated by `src/player_metrics.py`. Composite weights were locked in `config.yaml` before this "
         "stage; no leaderboard is produced until T11.", "",
         "## Tier credibility κ (bridging players)", "",
         "κ = corr(IPL value, tier-x value) ÷ corr(IPL odd-match, IPL even-match value); 90% player-bootstrap CI.", "",
         "### Batting", "", md_table(kt_bat, index=False, floatfmt="{:.3f}"), "", f"Used: **{how_bat}** → {k_bat}", "",
         "### Bowling", "", md_table(kt_bowl, index=False, floatfmt="{:.3f}"), "", f"Used: **{how_bowl}** → {k_bowl}", "",
         "## Reconciliation", ""]
    chk = [("Batting: Σ balls (P + N) = balls faced in rating set", int(bat.balls_P.fillna(0).sum() + bat.balls_N.fillna(0).sum()), int(len(fa))),
           ("Batting: Σ runs (P + N) = runs off the bat", int(bat.runs_P.fillna(0).sum() + bat.runs_N.fillna(0).sum()), int(fa.runs.sum())),
           ("Bowling: Σ legal (P + N) = legal balls", int(bowl.legal_P.fillna(0).sum() + bowl.legal_N.fillna(0).sum()), int(d.is_legal.sum())),
           ("Bowling: Σ wickets (P + N) = bowler wickets", int(bowl.wkts_P.fillna(0).sum() + bowl.wkts_N.fillna(0).sum()), int(d.is_bowler_wicket.sum()))]
    for name, a, b in chk:
        L.append(f"- [{'PASS' if a == b else 'FAIL'}] {name}: {a:,} vs {b:,}")
    L += ["", "## Pool sizes", "",
          f"- Batters with any pressure ball: {int(bat.balls_P.notna().sum())}; provisional eligible "
          f"(≥{el['bat_min_pressure_balls']} pressure balls, ≥{el['bat_min_pressure_innings']} pressure innings, active since 2025): "
          f"**{int(bat.eligible_provisional.sum())}**",
          f"- Bowlers with any pressure ball: {int(bowl.legal_P.notna().sum())}; provisional eligible "
          f"(≥{el['bowl_min_pressure_balls']} pressure legal balls, ≥{el['bowl_min_pressure_matches']} matches, active since 2025): "
          f"**{int(bowl.eligible_provisional.sum())}**",
          f"- Eligible batters by role: {bat[bat.eligible_provisional].role_group.value_counts().to_dict()}",
          f"- Eligible bowlers by role: {bowl[bowl.eligible_provisional].role_group.value_counts().to_dict()}", "",
          "## Metric distributions among provisionally eligible players (quantiles; no names)", ""]
    qs = [.05, .25, .5, .75, .95]
    bcols = ["balls_P", "eff_n_P", "rv_P", "rv_N", "delta_rv", "wpa_per100_P", "sr_P", "consistency", "pct_P_balls_ipl"]
    wcols = ["legal_P", "eff_n_P", "bv_P", "bv_N", "delta_bv", "wpa_per100_P", "econ_P", "consistency", "pct_P_balls_ipl"]
    L += ["### Batting", "", md_table(bat[bat.eligible_provisional][bcols].quantile(qs).T, floatfmt="{:.3f}"), "",
          "### Bowling", "", md_table(bowl[bowl.eligible_provisional][wcols].quantile(qs).T, floatfmt="{:.3f}"), "",
          "## Correlation between components (eligible players; Spearman)", "",
          "Checks the components are related but not redundant.", "",
          "### Batting", "", md_table(bat[bat.eligible_provisional][["rv_P", "wpa_per100_P", "delta_rv", "consistency"]]
                                     .corr("spearman"), floatfmt="{:.2f}"), "",
          "### Bowling", "", md_table(bowl[bowl.eligible_provisional][["bv_P", "wpa_per100_P", "delta_bv", "consistency"]]
                                      .corr("spearman"), floatfmt="{:.2f}"), ""]
    (out / "validation" / "player_metrics_checks.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return bat, bowl, L


if __name__ == "__main__":
    run()
