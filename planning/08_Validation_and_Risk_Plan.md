# 08 — Validation and Risk Plan

## 1. Risk register

| # | Risk | Where it bites | Likelihood / impact | Mitigation | Check |
|---|---|---|---|---|---|
| R1 | **Small samples** | Pressure subsets are ~25% of balls, so few players have large n | High / High | Reliability-based eligibility; EB shrinkage; bootstrap CIs; P(top-10) | Report n\*; no top-10 player below eligibility; CI width in the table |
| R2 | **Selection bias** (who gets pressure balls) | Finishers and death bowlers *choose* or are *chosen* for pressure roles. Top-order batters see fewer chase-pressure balls. | High / Med | Context baselines include phase and wickets; role-group priors; report opportunity counts; differential vs own baseline | Compare rankings within role groups |
| R3 | **Competition-strength differences** | T20Is vs Associates; A-team events | Med / High | Tiering by opponent; tier credibility factor from bridging players; IPL-only scenario | Tier-mix column; flag any top-10 player with > 40% of pressure balls from T3/T4 |
| R4 | **Role differences** | Openers vs finishers; new-ball vs death bowlers | High / Med | Role-specific priors; phase-aware expectations; no merged bat/bowl score | Role distribution of the top 10 reviewed |
| R5 | **Incomplete match context** | No venue name, pitch, dew, team strength; first-innings target unknown | Med / Med | Venue-season scoring effects via venue_id; par model; state that pressure = *situational* | Limitation section |
| R6 | **Coverage gaps** | No T20 World Cups; T20I subset only; 16 matches without ball-by-ball data | Certain / Med | Disclose; weight IPL credibly; do not claim "all T20Is" | Stated in the report |
| R7 | **Recency bias** | Overweighting 2026 | Med / Med | Half-life 2 years, with H = 1 and H = ∞ scenarios | Overlap metrics across H |
| R8 | **Overfitting** | WP model and weights tuned to the data | Med / High | Leave-one-season-out CV for WP; weights fixed a priori; out-of-time test | Calibration on held-out seasons; pre-registration note in config |
| R9 | **Incorrect player matching** | Seven shared names; possible duplicate IDs (Basil Hameed) | Med / High | ID-only joins; verification V1–V2; team suffix in display names | Verification log |
| R10 | **Misleading averages** | Not-outs inflate batting averages; economy ignores wickets | High / Med | Use run value with wicket cost (λ_ctx); runs per dismissal only as descriptive | Reported alongside |
| R11 | **Survivorship bias** | Players dropped after poor pressure games have short records; those who survive look better | Med / Med | Shrink toward the role-group mean (not the elite mean); report how many short-career players exist | Discussed qualitatively |
| R12 | **Unverified auction availability** | Recommending a retained player as a buy | High / High | [CONFIRMED] labels; "benchmark only" band | RR overlay audit |
| R13 | **Overstated IPL predictions** | Claiming future pressure performance | Med / High | Language rules (§4); out-of-time validation quantifies predictive value | Report wording review |
| R14 | **Pressure-skill may be weakly repeatable** | Clutch ability is often mostly noise in sports analytics | Med / High | Measure it (T10). If low, rely more on shrunk *general quality in pressure contexts* and say so. | Reliability numbers reported |
| R15 | **Metric multiplicity / cherry-picking** | Many splits (S1–S6, pace vs spin) | Med / Med | Core score uses only the pre-declared components; splits are descriptive | Pre-stated in config |
| R16 | **Data errors in the pack** | Duplicate playing-XI rows, extras semantics, DLS | Low / Med | Validation invariants (`07 T3`); manual scorecard spot-checks | ≥ 99% totals reconciliation |
| R18 | **Ranked player not selectable on Unstop** | The final lists include someone missing from the dropdown | Med / High | Task T0: verify the pool from the actual form; never assume it (D4) | Every pick matched to a dropdown entry |
| R19 | **WP model limits (found in T6)** | First-innings WP is mildly overconfident in its top decile (predicts 0.80, observed 0.75). The model has no team-strength, venue or toss terms. ERR wicket values are coarse where the 9- and 10-wicket curves merge. | Med / Low–Med | First-innings pressure is already treated as less certain (`03 §9`). Run a sensitivity check with chase-only leverage (S-K). Disclose. | Report calibration plots |
| R17 | **Confidentiality breach** | Raw data exposed | Low / High | No public repo or dashboard; aggregates only in the report | Final QA checklist |

## 2. Validation procedures

### 2.1 Pressure construct validity
- **Separation:** league outcome rates (dot%, dismissal%, RPB) across Low/Moderate/High/Extreme tiers, with 95% bootstrap CIs. Expect a monotonic, non-overlapping progression.
- **Outcome relevance:** the share of total |ΔWP| that falls in the top 25% LI balls.
- **Convergence:** Spearman(LI, PI) at ball level; agreement on tier membership (Cohen's κ).
- **Face validity:** inspect 10 random Extreme balls and 10 random Low death-over balls.

### 2.2 WP model validity
Leave-one-season-out log-loss, Brier, calibration slope and intercept; monotonicity tests; comparison with a phase-only baseline.

### 2.3 Metric reliability
Split-half (odd vs even matches) Spearman-Brown reliability for every component, by role group; season-to-season correlation for players with adequate n in both seasons.

### 2.4 Predictive check (out-of-time)
Compute composites on 2022–2024; correlate with shrunk pressure value in 2025–2026 for players eligible in both periods. Compare with naive predictors (raw pressure SR / economy, overall SR / economy). Reported as **correlation**, never as a guarantee.

### 2.5 Reproducibility
A clean rerun from raw CSVs with fixed seeds reproduces identical rankings. The scripts and config are archived with the report.

## 3. Sensitivity analysis and alternative ranking scenarios

| Scenario | Change from main |
|---|---|
| S-A Pressure threshold | Top 15% / top 35% LI instead of top 25% |
| S-B Pressure definition | Rule-based PI instead of LI |
| S-C Weighting | Unweighted pressure balls (no LI weights) |
| S-D Composite weights | Equal 25% each; performance-only (B3 + B4); differential-heavy (40% Δ) |
| S-E Competition | IPL-only; IPL + T2 only; no tier discount |
| S-F Recency | H = 1 yr; H = ∞ |
| S-G Shrinkage | Weaker prior (τ² × 2); none (raw, eligibility only) |
| S-H Eligibility | Thresholds ×0.75 and ×1.5 |
| S-I Outcome metric | WPA-only ranking |
| S-L Tiering scope | Pressure tiers computed within each innings (equal High/Extreme share for batting-first and chasing) instead of pooled LI quantiles |
| S-K Innings scope | Leverage from chase (innings 2) balls only (the better-calibrated WP model) |
| S-J Activity filter | No "active since 2025" filter (main run uses it, per D2) |

**Reported per scenario:** overlap with the main top 10, Kendall τ on the top 20, and players entering or leaving.
**Robustness label per pick:** *Robust* (top 10 in ≥ 80% of scenarios), *Moderate* (50–80%), *Fragile* (< 50%). Fragile picks need an explicit justification or are replaced by the next robust player **according to a rule stated before results are seen**: "if the main rank is 8–10 and the pick is Fragile while rank 11–12 is Robust with an overlapping CI, swap them". The rule is documented.

## 4. Evidence language (descriptive vs correlational vs predictive)

| Claim type | Allowed wording | Requirement |
|---|---|---|
| Descriptive | "In 2022–26 pressure balls, X scored 1.62 runs per ball against an expected 1.38" | Number + n |
| Comparative | "X ranks 3rd of 74 eligible batters (90% CI rank 1–7)" | Bootstrap interval |
| Correlational | "Pressure composites from 2022–24 correlated r = … with 2025–26 pressure value" | T14 result |
| Predictive | "We expect X to …" | Only with a T14 result attached and hedged; no certainty |
| Causal / psychological | "X has a strong temperament" | **Not allowed** as a data claim. Opinion only, clearly labelled. |

## 5. Final QA gate before submission
- [ ] All counts in the report trace back to scripts/outputs
- [ ] Unstop dropdown names = report names = player_ids (duplicate-name players checked)
- [ ] No repeated player within a list
- [ ] Each top-10 player: n, CI, P(top-10), robustness label, verification status
- [ ] Limitations section covers R1–R16
- [ ] No raw data in any shared artefact
- [ ] The participant has reviewed and owns the final picks
