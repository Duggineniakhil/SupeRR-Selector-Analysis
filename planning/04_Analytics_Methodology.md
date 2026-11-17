# 04 — Analytics Methodology

**Principle:** separate models for batting and bowling. Every metric is (1) defined on a precise ball set, (2) compared with a **context-expected** value, (3) shrunk according to sample size, and (4) reported with uncertainty. Weights are fixed *before* player names are inspected, and then stress-tested.

Notation: `P` = set of pressure balls (High and Extreme tiers, `03 §5`); `N` = non-pressure balls; `w_b = min(LI_b, cap)` = leverage weight of ball *b*; `r_b` = recency weight (§7); `E[·|ctx]` = league expectation for the ball's context.

---

## 1. Ball sets and attribution

| Item | Batting | Bowling |
|---|---|---|
| Ball counts | Balls faced = all deliveries except wides | Legal balls bowled = deliveries not in {wide, Overstep, other} |
| Runs | `runs` (bat runs) | `runs + extras1 + extras2` on wides/no-balls; `runs` on legal balls; byes and leg-byes excluded |
| Dismissals | Striker dismissed (or non-striker run-out → the non-striker); excluding Retire Out | Wickets excluding RunOut, Retire Out, Obstructing |
| Boundary | is_four or is_six | Same, conceded |
| Dot | runs = 0 and no extras charged to bowler (batting: runs = 0 on a faced ball) | Same, legal ball with 0 runs conceded |

---

## 2. Context-expected baselines (the core fairness device)

For each ball, estimate league-expected outcomes given its context:

```
ctx = (innings, phase[PP/Mid/Death], wickets_fallen bucket[0-1,2-3,4-5,6+],
       competition_tier, season, pace_or_spin(bowling_type), pressure_tier)
```

- `E[runs_bat | ctx]`, `E[P(dismissal) | ctx]`, `E[P(dot) | ctx]`, `E[P(boundary) | ctx]`.
- Estimation: cell means with hierarchical smoothing (sparse cells shrink to their parent cell). A Poisson or logistic GLM is the alternative, if cells are too sparse.
- **Key design point:** the *pressure tier is part of ctx*. A player's "above expected under pressure" is therefore judged against **how the league performs in the same pressure tier and phase**. This removes the mechanical effect that pressure situations differ in phase and wickets.

---

## 3. Batting metrics

| ID | Metric | Formula (on ball set S, weights ω_b = w_b·r_b) | Direction |
|---|---|---|---|
| B1 | Pressure Runs Above Expected per 100 balls | `RAE_P = 100 · Σ_{b∈P} ω_b (runs_b − E[runs_b]) / Σ ω_b` | ↑ |
| B2 | Pressure dismissal rate vs expected | `DAE_P = Σ ω_b (out_b − E[out_b]) / Σ ω_b` (balls per dismissal, shown descriptively) | ↓ |
| B3 | **Pressure Value per ball** (combines runs and wickets) | `RV_P = Σ ω_b [ (runs_b − E[runs_b]) − λ_ctx · (out_b − E[out_b]) ] / Σ ω_b`, where `λ_ctx` = run value of a wicket in that context (from the expected-remaining-runs model) | ↑ |
| B4 | Pressure WPA per 100 balls | `100 · Σ_{b∈P} WPA_bat,b / |P|` | ↑ |
| B5 | Strike rate under pressure | `100 · Σ_P runs / balls_faced_P` (descriptive) | ↑ |
| B6 | Runs per dismissal under pressure | `Σ_P runs / dismissals_P` (descriptive; misleading at small n) | ↑ |
| B7 | Boundary % under pressure | `boundaries_P / balls_P` | ↑ |
| B8 | Dot % under pressure | `dots_P / balls_P` | ↓ |
| B9 | **Pressure differential** (vs own usual level) | `Δ = RV_P(player, ctx-adjusted) − RV_N(player, ctx-adjusted)` | ↑ (≥ 0 = holds up) |
| B10 | Chase completion contribution | WPA in innings-2 pressure balls; share of successful chases "finished" (not out at the win) | ↑ |
| B11 | Consistency | See §5 | ↑ |
| B12 | Splits vs pace / spin | B3 by `pace_or_spin` (derived from `bowling_type`) | profile only |

**Why B3 (run value) and not SR alone:** under pressure, a batter who strikes at 180 but gets out every 6 balls may cost the match. B3 prices a wicket by its context-specific run cost (`λ_ctx`), which is higher with fewer wickets in hand and more balls left.

## 4. Bowling metrics

| ID | Metric | Formula | Direction |
|---|---|---|---|
| W1 | Pressure Runs Saved per 100 balls | `RS_P = 100 · Σ_{b∈P} ω_b (E[conc_b] − conc_b) / Σ ω_b` | ↑ |
| W2 | Pressure wickets above expected | `Σ ω_b (wkt_b − E[wkt_b]) / Σ ω_b` (bowler wickets) | ↑ |
| W3 | **Pressure Bowling Value per ball** | `BV_P = Σ ω_b [ (E[conc_b] − conc_b) + λ_ctx·(wkt_b − E[wkt_b]) ] / Σ ω_b` | ↑ |
| W4 | Pressure WPA (bowler) per 100 balls | `−100 · Σ_P WPA_bat,b / |P|` | ↑ |
| W5 | Economy under pressure | `6 · conc_P / legal_P` (descriptive) | ↓ |
| W6 | Balls per wicket under pressure | `legal_P / wkts_P` | ↓ |
| W7 | Dot % under pressure | | ↑ |
| W8 | Boundary-concession % under pressure | | ↓ |
| W9 | Extras rate under pressure (wides + no-balls per over) | discipline marker | ↓ |
| W10 | **Pressure differential** | `BV_P − BV_N` (both ctx-adjusted) | ↑ |
| W11 | Death-over pressure effectiveness | W3 restricted to overs 16–20 ∩ P | profile |
| W12 | Consistency | See §5 | ↑ |

## 5. Consistency and reliability metrics

| ID | Metric | Definition |
|---|---|---|
| C1 | Match-level pressure dispersion | SD across matches of the per-match RV_P (BV_P), weighted by balls; reported as a shrunk coefficient of variation |
| C2 | Pressure failure rate | Batting: share of pressure innings (≥ 4 pressure balls) with negative RV and WPA. Bowling: share of pressure spells (≥ 6 pressure legal balls) conceding > E + 1 SD. |
| C3 | Pressure success rate | Share of pressure innings or spells with positive value |
| C4 | Season stability | Correlation of a player's RV_P across seasons (league-level, for RQ5), plus a player's number of positive seasons |
| C5 | Opportunity count | Pressure balls, pressure innings/spells, distinct matches |

---

## 6. Competition-strength handling (IPL vs T20I)

1. **Tiers** (based on opponent, not label):
   - T1 = IPL (all matches)
   - T2 = T20I between top-10 full members (Afg, Aus, Ban, Eng, Ind, NZ, Pak, SA, SL, WI)
   - T3 = T20I involving Ireland, Zimbabwe or Associate nations
   - T4 = A-team / Emerging events
2. Baselines (§2) include the tier, so performance is always *relative to that environment*.
3. **Tier credibility factor** `κ_tier` for combining evidence: estimated from **bridging players** (players with enough balls in both T1 and T2/T3/T4). Compare their context-adjusted value across tiers, and use the ratio to discount lower tiers. If the estimate is unstable, fall back to fixed discounts (T1 = 1.0, T2 = 0.9, T3 = 0.6, T4 = 0.6) and **disclose** them as judgement, with sensitivity runs.
4. Sensitivity runs: **IPL-only** ranking, and **T1 + T2 only**.

## 7. Recency

`r_b = 0.5^{(ref_date − match_date)/H}` with ref_date = 1 Nov 2026 and half-life H = 2 years (sensitivity: H = 1 year, H = ∞). Rationale: the auction buys future performance. Older seasons still inform the estimate but count less. The 2026 IPL is the most recent full-intensity evidence.

---

## 8. Sample-size adjustment: empirical-Bayes shrinkage

Value metrics (B3, W3 and their components) are per-ball averages with noise ∝ 1/√n.

**Normal–normal shrinkage** (the default for per-ball value metrics):
```
θ̂_i     = observed weighted mean for player i (effective n_i = (Σω)²/Σω²)
σ²_i    = s²_ball / n_i                       (s²_ball = within-player ball-level variance)
τ²      = between-player variance of true talent (method-of-moments estimate within role group)
μ_g     = role-group prior mean (e.g., middle-order batters, death pacers, spinners)
θ_i^EB  = μ_g + (τ² / (τ² + σ²_i)) · (θ̂_i − μ_g)
```
**Beta–binomial** shrinkage for rate metrics (dot%, boundary%, dismissal rate), with priors fitted by maximum likelihood within the role group.

- Shrinkage strength comes from the data (τ²), not from a chosen constant.
- **Stabilisation point** n\* (where `τ²/(τ²+σ²)` = 0.5) is reported for every metric. It explains why small-sample players rank lower and anchors the eligibility thresholds in `03 §8`.
- Role groups prevent shrinking a finisher toward an opener's mean. Groups are inferred from data (modal batting position; bowling phase share; pace/spin).

## 9. Uncertainty: match-cluster bootstrap

- Resample **matches** (not balls, since balls within a match are correlated) 2,000 times, with a fixed seed. Recompute baselines → metrics → shrinkage → composite → ranks in each replicate.
- Report per player: a 90% interval for the composite score, the **median rank**, and **P(top-10)**.
- Ordering rule for the final lists: by composite point estimate. If two players' 90% intervals overlap heavily **and** one has a materially higher P(top-10), mention it in the report. Do not reshuffle by hand.

---

## 10. Composite scores (role-specific)

### 10.1 Batting Pressure Reliability Score (BPRS)
Components (all EB-shrunk, then converted to z-scores within the eligible batting pool):

| Component | Measures | Initial weight | Justification |
|---|---|---|---|
| Z(B3) Pressure value | *How good under pressure* (absolute, context-adjusted) | 0.40 | Core of "best-performing under pressure" |
| Z(B4) Pressure WPA | Match-outcome impact in high-leverage balls | 0.20 | Links performance to winning; partly overlaps B3, so a smaller weight |
| Z(B9) Pressure differential | *Compared with their usual level* (brief requirement) | 0.20 | Rewards players who hold or raise their level, and avoids rewarding only great all-round players |
| Z(C3 − C2) Consistency | *Deliver consistently* | 0.20 | Brief explicitly asks for consistency across matches |

### 10.2 Bowling Pressure Reliability Score (WPRS)
Same structure: Z(W3) 0.40, Z(W4) 0.20, Z(W10) 0.20, Z(consistency) 0.20.

### 10.3 How the weights are justified and validated (no tuning to taste)
1. **Fixed a priori** from the brief's wording: performance under pressure (~60% across B3 and B4), relative to usual level (20%), consistency (20%). They are written into `config.yaml` and committed (locally) **before** player-level outputs are viewed.
2. **Reliability check:** compute the split-half (odd/even matches) reliability of each component. A component with reliability < 0.2 is reported as mostly noise and down-weighted under a pre-stated rule (weight × reliability / mean reliability). The rule is stated in advance, not tuned.
3. **Validity check:** does the composite in seasons 2022–2024 predict pressure value in 2025–2026 better than raw pressure SR or economy does? (Out-of-time test; see `08`.)
4. **Sensitivity:** equal weights; performance-only; differential-heavy; PCA-derived weights. We report the overlap of each top 10 with the main list.

### 10.4 Batting and bowling are never merged
All-rounders are evaluated independently in each list. Any "all-round value" discussion is narrative in the RR section and is not part of the ranked scores.

---

## 11. Distributions and normalisation

- Value metrics are per-ball averages and roughly normal after shrinkage, so z-scores are fine.
- Rates near bounds are put on a logit scale before z-scoring.
- Robust z (median/MAD) is a sensitivity option if heavy tails appear.

---

## 12. Outputs per player (feeds the report and the scouting cards)

`player_id, name, role_group, nationality(if known), pressure_balls, pressure_innings/spells, matches, RV_P (raw, EB), CI90, Δ vs baseline, WPA_P, SR_P, dismissal rate, dot%, boundary%, econ_P, consistency stats, composite, median rank, P(top-10), tier mix (% IPL), last appearance date.`
