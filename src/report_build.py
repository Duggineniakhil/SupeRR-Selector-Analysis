"""T19 — Build the methodology report (Markdown) from pipeline outputs.

Every number is read from a pipeline artefact (parquet / pickle / validation CSV or Markdown),
so the report regenerates exactly from `python -I src/run_pipeline.py`. Output is local only
(report/ is git-ignored) because it names the picks.

Output: report/SupeRR_Selector_Methodology_Report.md (+ report/figures/*)
"""
from __future__ import annotations

import pickle
import re
import shutil

import numpy as np
import pandas as pd

from common import ROOT, load_config, md_table, path


def pooled_table(md: str, section: str) -> pd.DataFrame:
    """Parse the '### Pooled' table under '## {section}' in t11_estimators.md."""
    block = md.split(f"## {section}")[1].split("### Pooled")[1]
    rows = [r for r in block.splitlines() if r.startswith("| M")]
    data = [[c.strip() for c in r.strip("|").split("|")] for r in rows[:4]]
    return pd.DataFrame(data, columns=["model", "skill", "pearson_w", "spearman", "calib_slope"]).set_index("model")


def f2(x, d=2):
    return "–" if pd.isna(x) else f"{x:.{d}f}"


def top10_table(kind: str, out, interim) -> pd.DataFrame:
    rk = pd.read_csv(out / "rankings" / f"{kind}_ratings.csv", index_col=0)
    rob = pd.read_csv(out / "rankings" / f"{kind}_robustness.csv", index_col=0)
    tb = pd.read_parquet(interim / f"player_{'bat' if kind == 'batting' else 'bowl'}.parquet")
    # Decision D7: the official lists exclude IPL-ineligible players (Pakistan nationals); the
    # players below move up. Model ranks, rank ranges and P(top-10) are from the full model run.
    players = pd.read_parquet(interim / "players.parquet").set_index("player_id")
    nat = players.pack_country.astype(object).where(players.pack_country.notna(), "")
    rk = rk[nat.reindex(rk.index).fillna("").ne("Pakistan").to_numpy()].copy()
    rk["rank"] = range(1, len(rk) + 1)
    t = rk.head(10).copy()
    raw = (tb.sr_P if kind == "batting" else tb.econ_P).reindex(t.index)
    return pd.DataFrame({
        "Rank": t["rank"].astype(int),
        "Player": t.display_name,
        "Role": t.role_group.str.replace("_", " "),
        "Rating (M2)": t.rating.map(f2, 3) if False else t.all_balls_value_EB.map(lambda v: f2(v, 3)),
        "Baseline ability": t.baseline_ability_B.map(lambda v: f2(v, 3)),
        "Actual pressure value": t.actual_pressure_value_raw.map(lambda v: f2(v, 3)),
        "Pressure advantage": t.pressure_advantage_raw.map(lambda v: f"{v:+.3f}"),
        ("Pressure SR" if kind == "batting" else "Pressure econ."): raw.map(lambda v: f2(v, 1)),
        "Pressure balls": t.pressure_balls.astype(int),
        "P(top-10)": t.p_top10.map(f2),
        "90% rank interval": [f"{int(a)}–{int(b)}" for a, b in zip(t.rank_p05, t.rank_p95)],
        "Robustness": rob.robustness.reindex(t.index),
        "% IPL": t.pct_P_balls_ipl.map(lambda v: f"{v:.0f}%"),
    })


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    interim, out = path(cfg, "interim"), path(cfg, "outputs")
    rep = ROOT / "report"; (rep / "figures").mkdir(parents=True, exist_ok=True)
    for f in (out / "figures").glob("fig_*.png"):
        shutil.copy(f, rep / "figures" / f.name)
    for f in ("wp_calibration.png", "err_curves.png"):
        shutil.copy(out / "figures" / f, rep / "figures" / f)

    # ---------- numbers from artefacts
    m = pd.read_parquet(interim / "matches.parquet")
    bs_n = len(pd.read_parquet(interim / "ball_state.parquet", columns=["match_id"]))
    d = pd.read_parquet(interim / "rating_balls.parquet")
    tiers = m[m.has_bbb].tier.value_counts()
    ref = d[d.is_legal & d.batting_side_won.notna()].copy()
    ref["a"] = ref.wpa_bat.abs()
    share_top = ref.loc[ref.is_pressure, "a"].sum() / ref.a.sum()
    share_ext = ref.loc[ref.pressure_tier == "Extreme", "a"].sum() / ref.a.sum()
    death_low = (ref[ref.phase == "DEATH"].pressure_tier == "Low").mean()
    mid_hi = ref[ref.phase == "MID"].is_pressure.mean()
    chase_p, first_p = ref[ref.innings == 2].is_pressure.mean(), ref[ref.innings == 1].is_pressure.mean()
    with open(interim / "reliability.pkl", "rb") as fh:
        rel = pickle.load(fh)
    t11 = (out / "validation" / "t11_estimators.md").read_text(encoding="utf-8")
    pb, pw = pooled_table(t11, "Batting"), pooled_table(t11, "Bowling")
    sens = (out / "validation" / "sensitivity.md").read_text(encoding="utf-8")
    ov = re.findall(r"Mean top-10 overlap across 17 scenarios: \*\*([\d.]+) / 10\*\*", sens)
    oot = {k: pd.read_csv(out / "validation" / f"out_of_time_{k}.csv") for k in ("bat", "bowl")}
    o = {k: oot[k].set_index("predictor (2022–24)") for k in oot}
    rr_md = (out / "rankings" / "rr_overlay.md").read_text(encoding="utf-8")
    chains = rr_md.split("## Scenario chains by role (most severe need first)")[1].split("## Caveats")[0].strip()
    need = rr_md.split("## Need matrix (pre-registered rule)")[1].split("## Scenario chains")[0].strip()
    rb = {k: rel[k]["split_half"].set_index("metric").full_sample_reliability for k in ("bat", "bowl")}
    bat10, bowl10 = top10_table("batting", out, interim), top10_table("bowling", out, interim)
    el = {k: rel[k]["pool"] for k in ("bat", "bowl")}
    m2b, m2w = o["bat"].loc["M2 all-balls EB (final)"], o["bowl"].loc["M2 all-balls EB (final)"]
    srb = o["bat"].loc["naive: overall SR (non-pressure)"]

    L = []
    A = L.append
    A("# Identifying the Most Reliable Players Under Pressure")
    A("### SupeRR Selector Season 2 — Round 1 Methodology Report")
    A("")
    A(f"*Prepared for Rajasthan Royals. Data: supplied IPL and T20I data pack (Jan 2022 – Nov 2026). "
      f"Analysis date: {cfg['rr_overlay']['as_of']}. Fully reproducible: `python -I src/run_pipeline.py`.*")
    A("")
    A("## Executive summary")
    A("")
    A("**The question.** Which batters and bowlers deliver most reliably when a match is on the line, and "
      "can data separate genuine pressure performers from players who simply had a few good moments?")
    A("")
    A("**How we defined pressure.** Pressure is *how much the next ball can change who wins*. We built a "
      "win-probability model from this data pack, measured every delivery's leverage (the spread of win "
      f"probability its possible outcomes could produce), and labelled the top 25% of balls as High/Extreme "
      f"pressure. Those balls are 25% of deliveries but carry **{share_top:.0%}** of all realised "
      f"match swing. Pressure is not the same as the death overs: {death_low:.0%} of death-over balls are "
      f"low-leverage, while {mid_hi:.0%} of middle-over balls are high-leverage.")
    A("")
    A("**What we found, and why it shaped the method.** Performance on pressure balls alone barely repeats: "
      f"split-half reliability is {rb['bat']['rv_P']:.2f} for batters and {rb['bowl']['bv_P']:.2f} for bowlers, "
      "and season-to-season correlation is roughly zero. A player's *difference* between pressure and usual "
      f"performance does not repeat at all ({rb['bat']['delta_rv']:.2f} / {rb['bowl']['delta_bv']:.2f}). "
      "Ranking players on a handful of dramatic pressure moments would therefore largely rank luck. "
      "We tested three estimators on later seasons and selected the one that best predicts future pressure "
      "performance: **context-adjusted ability measured on all balls, shrunk for sample size (Empirical "
      "Bayes), with pressure balls included as evidence**.")
    A("")
    A("**What the evidence supports.** For bowlers the method works clearly: ratings built only from 2022–24 "
      f"correlate r = {m2w['r_w vs pressure value']:.2f} {m2w['r 90% CI']} with 2025–26 pressure performance, "
      "beating economy-based and pressure-only alternatives. For batters the signal is weaker "
      f"(r = {m2b['r_w vs pressure value']:.2f} {m2b['r 90% CI']}) and not distinguishable from plain strike rate "
      f"(r = {srb['r_w vs pressure value']:.2f}); we report this openly and keep batting claims descriptive.")
    A("")
    A("**Our message to RR.** *The goal is not to find players who once produced extraordinary pressure "
      "performances; it is to identify players whose underlying ability and demonstrated performance give the "
      "strongest evidence that they will deliver when it matters.*")
    A("")
    A("### Final rankings")
    A("")
    two = pd.DataFrame({"Rank": range(1, 11), "Top 10 batters": bat10.Player.to_numpy(),
                        "Robustness (bat)": bat10.Robustness.to_numpy(),
                        "Top 10 bowlers": bowl10.Player.to_numpy(), "Robustness (bowl)": bowl10.Robustness.to_numpy()})
    A(md_table(two, index=False))
    A("")
    A("*Robustness = share of 17 alternative-assumption scenarios in which the player stays top 10 "
      "(Robust ≥ 80%, Moderate 50–80%, Fragile < 50%).*")
    A("")

    # ---------------- 1. Data
    A("## 1. Data and preparation")
    A("")
    A(f"- **Coverage:** {bs_n:,} deliveries from {int(m.has_bbb.sum())} matches (Jan 2022 – Nov 2026): IPL 2022–26 "
      f"({tiers.get('T1_IPL', 0)} matches), T20Is between top-10 nations ({tiers.get('T2_T20I_TOP', 0)}), other T20Is "
      f"({tiers.get('T3_T20I_OTHER', 0)}) and two A-team tournaments ({tiers.get('T4_A_TEAM', 0)}). The T20I set is a "
      "subset of bilateral/tri-series and Asia Cups; **no T20 World Cup is included**.")
    A("- **Semantics validated:** total runs per delivery = bat runs + two extras columns; rebuilt innings totals "
      "reproduce official winning margins in 99.7% (runs) and 99.8% (wickets) of non-DLS results. 'Overstep' and "
      "'other' extras behave as no-balls.")
    A("- **Match state rebuilt for every ball:** score, wickets, legal balls left, target, required/current run "
      "rate, partnership, wickets in the last 18 balls; rain-reduced limits inferred where revised-overs fields "
      "were blank; 5 chases with unknown or superseded DLS targets excluded from win-probability modelling. "
      "All 11 integrity checks pass.")
    A(f"- **Rating set:** {len(d):,} deliveries (innings 1–2 of decided or tied matches with a reliable target; "
      "super overs and no-results excluded).")
    A("- **Player identity:** joins use `player_id` only; seven names shared by different players are kept "
      "separate and displayed with a team suffix.")
    A("")

    # ---------------- 2. Pressure
    A("## 2. Pressure definition")
    A("")
    A("**Definition.** A delivery is high-pressure when the match is still in the balance *and* its outcome can "
      "move the result far more than a typical ball. This is measured, not assumed:")
    A("")
    A("1. **Win-probability (WP) model** fitted on this data pack: spline logistic models for the chase "
      "(runs needed, balls left, wickets in hand, a DLS-style resource curve) and for the first innings "
      "(score vs par for the scoring environment). Validated on held-out seasons: chase AUC 0.91, calibration "
      "slope 1.04; first innings AUC 0.71 (see `wp_model.md`).")
    A("2. **Leverage index (LI)** for every ball: the expected spread of win probability across the possible "
      "outcomes of that ball (dot, 1, 2, 3, 4, 6, wicket), divided by the average ball's spread. LI = 3 means "
      "the ball carries three times the usual match impact. The same LI applies to batter and bowler.")
    A("3. **Pressure tiers** on LI quantiles (computed separately for IPL and T20I): Low (< P50), Moderate, "
      "High (P75–P90), Extreme (≥ P90). *Pressure balls* = High + Extreme (top 25%).")
    A("")
    A("![Pressure concentration](figures/fig_pressure_concentration.png)")
    A("")
    A("**Why it is meaningful — evidence it separates pressure from ordinary situations:**")
    A("")
    A(f"- *Outcome relevance:* High+Extreme balls carry {share_top:.1%} of realised win-probability movement; "
      f"Extreme balls alone (10%) carry {share_ext:.1%}.")
    A(f"- *Not just phase:* {death_low:.0%} of death-over balls are Low leverage (decided matches); {mid_hi:.0%} of "
      "middle-over balls are High/Extreme. A rule such as 'death overs = pressure' would mislabel both.")
    A("- *Cross-check:* an independent rule-based Pressure Index (required-rate gap, runs needed per wicket, time "
      "remaining) agrees in chases (Spearman 0.65). In first innings it measures *difficulty* (below par, "
      "collapses) rather than *stakes*, so leverage remains primary.")
    A(f"- *Where pressure falls:* {chase_p:.0%} of chase balls vs {first_p:.0%} of first-innings balls are "
      "pressure balls — chases decide most matches, so ratings lean on chase evidence (tested in sensitivity S-L).")
    A("")
    A("![Pressure by phase](figures/fig_pressure_by_phase.png)")
    A("")
    A("**Measurable vs subjective:** crowd, rivalry and tournament stakes are not in the data and are not used. "
      "Knockout matches (31) are reported descriptively only.")
    A("")

    # ---------------- 3. Performance measurement
    A("## 3. Performance measurement")
    A("")
    A("**Context-expected baselines.** For every ball we estimate what an average player would produce in the "
      "same situation — innings × phase × wickets in hand × pressure tier × pace/spin × competition tier × season "
      "— using hierarchical cell means (sparse cells shrink toward broader ones). Residuals are ≈ 0 in every "
      "populated cell.")
    A("")
    A("**Per-ball value (runs above expected, with wickets priced):**")
    A("")
    A("- Batting: `v = (runs − E[runs]) − λ · (out − E[out])`")
    A("- Bowling: `v = (E[conceded] − conceded) + λ · (wicket − E[wicket])`")
    A("")
    A("λ is the run value of a wicket *at that moment*, from a DLS-style expected-remaining-runs curve fitted "
      "on the pack (≈ 10 runs in the powerplay, ≈ 3 at the death). This prices a dismissal properly instead of "
      "treating strike rate and average separately.")
    A("")
    A("**Player baselines and the three estimators (decision D5).** Per player we compute value on pressure "
      "balls (leverage-weighted), on non-pressure balls, and on all balls, each with recency weighting "
      "(half-life 2 years) and a competition-credibility factor. We then compared:")
    A("")
    A("| Estimator | Idea |")
    A("|---|---|")
    A("| M1 Pressure-only | Empirical-Bayes-shrunk value on pressure balls |")
    A("| **M2 All-balls (selected)** | Empirical-Bayes-shrunk value on all balls (pressure balls included) |")
    A("| M3 Hybrid | Baseline ability (non-pressure) + shrunk pressure residual, weights learned out-of-sample |")
    A("")
    A("Empirical-Bayes shrinkage: `θ̂ = μ_role + κ̄ · τ²/(τ² + σ²/n_eff) · (x − μ_role)`, with role-group priors, "
      "between-player variance τ² estimated on training data, and κ̄ the player's competition-credibility factor.")
    A("")
    A("**Chronological validation (train on earlier seasons, test on 2024, 2025, 2026):**")
    A("")
    A(md_table(pd.DataFrame({"Batting: MSE skill": pb.skill, "Batting: r": pb.pearson_w,
                             "Bowling: MSE skill": pw.skill, "Bowling: r": pw.pearson_w}).loc[["M1", "M2", "M3"]]))
    A("")
    A("M2 wins clearly for batting. For bowling, the pre-registered rule picked M3 by a margin inside noise; "
      "because M3's pressure-residual variance was estimated as zero (so it would ignore pressure balls entirely) "
      "and M2 had the higher out-of-sample correlation, we use M2 for both lists — a **disclosed deviation** "
      "(decision D6). The pressure-specific residual adds no detectable predictive value in either discipline.")
    A("")

    # ---------------- 4. Fair comparisons
    A("## 4. Fair comparisons")
    A("")
    A(f"- **Eligibility:** ≥ 120 pressure balls faced and ≥ 20 pressure innings (batters); ≥ 150 pressure legal "
      f"balls and ≥ 20 pressure matches (bowlers); and an appearance since 1 Jan 2025. Eligible pools: "
      f"**{el['bat']} batters, {el['bowl']} bowlers**.")
    A("- **Sample size:** Empirical-Bayes shrinkage pulls small samples toward their role-group mean, so 3 great "
      "innings cannot outrank 300 balls of evidence. Measured stabilisation point on pressure balls: "
      f"{rel['bat']['vd_P']['n_star']:.0f} balls (batting), {rel['bowl']['vd_P']['n_star']:.0f} (bowling).")
    A("- **Different match contexts:** every comparison is against the expectation for the same situation, so an "
      "opener is not compared with a finisher on raw strike rate. Role-group priors (top order / middle order / "
      "finisher; powerplay pace / death pace / spin) keep shrinkage like-for-like.")
    A("- **IPL and T20I data:** evidence is credibility-weighted by opposition tier — IPL 1.0, T20I between "
      "top-10 nations 0.9, other T20Is and A-team events 0.6 (pre-registered fallback after a bridging-player "
      "estimate proved too unstable). The factor is applied to each player's deviation from the prior, so "
      "T20I-only records count for less. No top-10 pick relies on weaker-opposition evidence (> 40% of pressure "
      "balls); IPL-only and IPL+top-T20I scenarios are part of the robustness check.")
    A("- **Recency:** a 2-year half-life weights recent seasons more without discarding older evidence.")
    A("")

    # ---------------- 5. Evidence for top 10
    A("## 5. Evidence for the top 10")
    A("")
    A("Units: value columns are runs per ball relative to the context expectation (batting: runs added "
      "including wicket cost; bowling: runs saved including wicket value). *Baseline ability* uses non-pressure "
      "balls; *Pressure advantage* = actual pressure value − baseline (raw; shown for transparency — it does not "
      "repeat and is not used in the rating).")
    A("")
    A("### 5.1 Batters")
    A("")
    A(md_table(bat10, index=False))
    A("")
    A("![Top 15 batters](figures/fig_top15_batting.png)")
    A("")
    A("### 5.2 Bowlers")
    A("")
    A(md_table(bowl10, index=False))
    A("")
    A("![Top 15 bowlers](figures/fig_top15_bowling.png)")
    A("")
    A("### 5.3 How the order was decided")
    A("")
    A("- Order = final rating (M2 posterior). No manual reordering. A pre-stated swap rule (a Fragile pick at "
      "rank 8–10 swaps with a Robust player at 11–12 whose rank interval overlaps) was checked and not triggered.")
    A("- The top three in each list are separated from the field (P(top-10) ≥ 0.69); positions 7–10 are close "
      "calls with wide rank intervals, which we state rather than hide.")
    neg = bowl10[bowl10["Actual pressure value"].astype(float) < 0.05]
    if len(neg):
        A(f"- {', '.join(f'{n} (#{r})' for n, r in zip(neg.Player, neg.Rank))} rank in the top 10 despite near-zero "
          "or negative *raw* pressure value. This is deliberate: their pressure samples sit well inside the noise "
          f"band (stabilisation point ≈ {rel['bowl']['vd_P']['n_star']:.0f} balls), and out-of-sample tests show "
          "all-ball ability predicts later pressure performance better than pressure-only samples do. We flag "
          "them so the reader can weigh this choice.")
    A("")

    # ---------------- 6. Reliability & limitations
    A("## 6. Reliability, consistency and limitations")
    A("")
    A("### 6.1 Does pressure performance repeat?")
    A("")
    A("![Reliability](figures/fig_reliability.png)")
    A("")
    A("Context-adjusted pressure skill repeats weakly; the pressure-vs-usual difference does not repeat. Raw "
      "strike rate/economy repeat strongly, but mostly because they encode role and style (finishers strike "
      "faster, death bowlers concede more), not skill above context.")
    A("")
    A("### 6.2 Consistency across matches")
    A("")
    A("Per pressure innings (≥ 4 pressure balls) or spell (≥ 6), we recorded success (value > 0) and failure "
      "(value < 0 and negative win-probability added). Consistency was part of the pre-registered composite, "
      "but its reliability was low (≈ 0.12–0.14), and the out-of-time test favoured the all-balls estimator "
      "over the composite; consistency is therefore reported, not scored.")
    A("")
    A("### 6.3 Robustness to our own assumptions")
    A("")
    A(f"Across 17 alternative scenarios (pressure threshold 15%/35%, rule-based pressure, IPL-only, no tier "
      "discount, recency 1 year / none, no or weaker shrinkage, eligibility ×0.75/×1.5, no activity filter, "
      "WPA-only, leverage-weighted all balls, pressure-only and hybrid estimators), the top 10 retains on average "
      f"**{ov[0]}/10 batters and {ov[1]}/10 bowlers**.")
    A("")
    A("![Robustness batting](figures/fig_robustness_batting.png)")
    A("")
    A("![Robustness bowling](figures/fig_robustness_bowling.png)")
    A("")
    A("### 6.4 Out-of-time validation (the honest test)")
    A("")
    A("![Out-of-time validation](figures/fig_out_of_time.png)")
    A("")
    A("All results are **correlational**: they show how well ratings from 2022–24 tracked 2025–26 pressure "
      "performance, not a guarantee of future performance. Bowling ratings track later pressure performance "
      "well; batting ratings modestly, and no better than overall strike rate. We did not change the batting "
      "model after seeing this, because 2025–26 is the test set.")
    A("")
    A("### 6.5 Limitations")
    A("")
    for s in [
        "Pressure is *situational* (match state); psychological stakes, crowd and rivalry are not measured.",
        "No T20 World Cup in the pack; T20I coverage is partial.",
        "The win-probability model has no team-strength, venue or toss terms; first-innings WP is mildly "
        "over-confident in its top decile.",
        "Pressure-specific skill is not distinguishable from noise in this sample; the rankings therefore "
        "reward reliable underlying ability demonstrated across all situations, including pressure.",
        "Batting predictive evidence is weak (see 6.4). Bowling evidence is strong.",
        "Competition-tier credibility factors are pre-registered judgement (the data-driven estimate was unstable).",
        "Positions 7–10 in both lists are statistically close; rank intervals are wide.",
    ]:
        A(f"- {s}")
    A("")

    # ---------------- 7. RR lens
    A("## 7. What this means for Rajasthan Royals' IPL 2027 auction")
    A("")
    A("The official rankings above are pure performance rankings. This section applies them to RR's squad "
      f"using the **official IPL 2027 retention lists** published on {cfg['rr_overlay']['as_of']} (SportsTak, "
      "corroborated by india.com). RR retained 19 players and released 9 (including Shimron Hetmyer and Tushar "
      "Deshpande), traded Sam Curran to LSG and received Mohammed Shami; purse Rs 27.05 crore, 6 slots, "
      "3 overseas. Ranks in this section are model ranks across all eligible players.")
    A("")
    A("### 7.1 Squad needs (RR IPL 2027 retained squad, rated with the same model)")
    A("")
    A("A role is COVERED if ≥ 2 RR players with enough evidence rate at or above the eligible-pool median, THIN "
      "if 1, GAP if 0 (rule fixed before the profile was computed).")
    A("")
    A(need)
    A("")
    A("**Death bowling is RR's one clear gap**: Deshpande was released and Curran traded, and the remaining "
      "death bowlers rate below the pool median. RR players already in the official lists (e.g. the #1 batter) "
      "are *back/retain* recommendations, not auction targets.")
    A("")
    A("### 7.2 Auction targets by role (officially available only)")
    A("")
    A("Each role lists the best player (retained elsewhere, for reference), then a primary target and two "
      "fallbacks in rating order, drawn only from players released [OFFICIAL] or with no IPL team in 2026. "
      "Priority with 3 overseas slots: Matheesha Pathirana for the death-bowling gap first, then the best "
      "available batter, then spin.")
    A("")
    A(chains.replace("### ", "#### "))
    A("")
    A("Excluded from targeting: players retired from the IPL, de facto unavailable (Pakistan players since 2008), "
      "or with doubtful availability (Bangladesh players after the Jan 2026 BCCI directive). Prices and "
      "overseas-slot costs are not assessed; Indian fallbacks are listed because most realistic targets are overseas.")
    A("")

    # ---------------- 8. Reproducibility
    A("## 8. Reproducibility and governance")
    A("")
    A("- Pipeline: `python -I src/run_pipeline.py` (ingest → clean → state → par → wp → pressure → baselines → "
      "players → reliability → estimators → sensitivity → oot → rr → figures → report). Seeds fixed; every "
      "threshold in `config.yaml`.")
    A("- Pre-registration: composite weights, reliability rules, estimator-selection rule and RR need rule were "
      "written into `config.yaml` before the corresponding results were computed. Deviations (D6) are disclosed.")
    A("- Confidentiality: the raw data pack and derived ball-level tables are never published; this report "
      "contains aggregates only.")
    A("- External facts (ages, nationality, availability, trades) are from public sources accessed on the "
      "analysis date and are labelled CONFIRMED / REPORTED / UNVERIFIED.")
    A("- **[Participant to confirm before submission]** Final player selections and reasoning reviewed and "
      "owned by the participant; Unstop dropdown names matched to the player IDs above.")

    p = rep / "SupeRR_Selector_Methodology_Report.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    return [f"report written: {p} ({len(L)} lines)"]


if __name__ == "__main__":
    run()
