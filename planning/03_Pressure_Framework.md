# 03 — Pressure Framework

**Goal:** a definition of pressure that is measurable, rooted in what actually decides T20 matches, works for **both batting and bowling**, and shows that it *distinguishes pressure situations from ordinary ones*, which the brief explicitly requires.

---

## 1. Working definition

> **Pressure is the degree to which the outcome of the match depends on the next ball(s).** A delivery is high-pressure when (a) the match is still genuinely in the balance, and (b) the result of that ball can move the match's win probability by much more than a typical ball does.

This is the **leverage** concept from sports analytics, applied to T20. It follows that:
- A death-over ball when the chasing side needs 60 off 12 is **low pressure**. The match is already decided.
- A 12th-over ball when the chasing side needs 85 off 50 with 4 wickets left is **high pressure**, even though it is not a death over.
- A first-innings collapse (3 wickets in 15 balls) creates pressure on the incoming batter and opportunity for the bowler, even with no target yet.

Everything is computed **from the data pack's own match states and results**. We use no outside judgement about which matches "felt" big.

---

## 2. Measurable indicators vs subjective interpretations

| Indicator | Measurable from data? | How |
|---|---|---|
| Balls remaining | ✅ | `legal_balls_limit − legal_balls_bowled` (limit = 120 or the DLS revision in balls) |
| Wickets in hand | ✅ | `10 − wickets_fallen` (run-outs count; retired-out counts as fallen for state purposes) |
| Required run rate (chase) | ✅ | `6 × runs_needed / balls_remaining` |
| Required − current run rate gap | ✅ | `RRR − CRR` |
| Runs needed per wicket in hand | ✅ | `runs_needed / wickets_in_hand` |
| First-innings score vs par | ✅ (derived) | Actual score minus *expected score at this state*, from a model of first-innings scores in the pack |
| Recent collapse | ✅ | Wickets in the last 18 legal balls |
| Phase | ✅ | Powerplay 1–6, Middle 7–15, Death 16–20 |
| Match closeness | ✅ | Win probability near 50% |
| Defending target (bowling) | ✅ | Second-innings balls from the bowling side's view |
| Match importance (knockout) | ✅ flag (31 matches) | Used **only as a descriptive or sensitivity overlay**. Sample too small to weight. |
| Tournament stakes (qualification races), crowd, rivalry | ❌ | Subjective or not in the data. **Not used**; mentioned as a limitation. |
| "Big-match temperament" | ❌ | Outcome of the analysis, not an input |

---

## 3. Pressure model A (primary): win-probability leverage

### 3.1 Win-probability (WP) model
Fit a model for **P(batting side wins | state)** at every legal-ball state.

**Second innings (chase) state features:**
- `balls_remaining`, `wickets_in_hand`, `runs_needed`
- `log(RRR)` or `runs_needed / balls_remaining`, with an interaction with `wickets_in_hand`
- competition tier (IPL vs T20I tier, see `04 §6`)

**First innings state features:**
- `balls_remaining`, `wickets_in_hand`, `current_score`
- *projected total*, from a first-innings scoring model (expected remaining runs given balls and wickets)
- The second-innings model is applied at the projected target, which turns first-innings states into a WP.

**Model choice:** logistic regression (GLM) with natural-spline terms and interactions (statsmodels or scikit-learn), or a monotone-constrained gradient-boosting model as a challenger. The final choice depends on calibration and log-loss in **leave-one-season-out cross-validation**. Prefer the simpler model if the performance gap is < 1% log-loss. Training labels: `win_team_id`. Exclude no-results and abandoned matches. Ties and super overs are labelled 0.5, or excluded (sensitivity).

**Validation requirements:**
- Calibration curve (decile reliability) on held-out seasons; Brier score; log-loss vs a naive phase-only baseline.
- Monotonicity sanity checks: WP falls as runs needed rise, and rises with wickets in hand.
- Spot checks on known tight finishes (from the data: matches won by ≤ 5 runs or by 1–2 wickets).

### 3.2 Leverage index (LI)
For each legal-ball state *s*, using the empirical outcome distribution for the next ball (dot, 1, 2, 3, 4, 6, wicket, extras) estimated at similar states (phase × wickets bucket):

```
Swing(s)    = Σ_o  p(o | s) · | WP(s ⊕ o) − WP(s) |
LI(s)       = Swing(s) / mean_over_all_states(Swing)
```

- LI = 1 → an average ball. LI = 3 → the ball carries 3× the usual match impact.
- LI uses the **same value for batter and bowler** on a ball. Pressure is shared by both, which satisfies the brief's requirement that the method works for both.
- Per-ball **Win Probability Added**: `WPA_bat = WP(after) − WP(before)` for the batting side. The bowler gets the negative.

### 3.3 Why leverage beats "death overs"
In implementation we will publish a chart showing the LI distribution by phase. We **expect, but have not yet verified**, that many death-over balls have low LI (decided matches) and some middle-over balls in chases have high LI. If the data does not show this, we will report it honestly.

---

## 4. Pressure model B (cross-check): rule-based Pressure Index (PI)

A transparent, explainable index for the report, and to confirm that rankings are not an artefact of model A.

**Chasing batting side (innings 2):**
```
RRR_gap   = clip((RRR − CRR) / 6, −1, 2)                     # demand above current pace
Wk_press  = clip((runs_needed / wickets_in_hand) / 25, 0, 2)  # runs each remaining wicket must carry
Time      = 1 − balls_remaining/120                           # closeness to the end
Alive     = 1 if 0.05 ≤ WP ≤ 0.95 else 0  (or a soft version from RRR bounds if WP not used)
PI_chase  = Alive · (w1·RRR_gap + w2·Wk_press + w3·Time)
```
**First innings:**
```
Par_gap   = (expected_score_at_state − actual_score) / σ       # below par = pressure on batters
Collapse  = wickets in last 18 legal balls (0..3+, capped)
PI_first  = w1·clip(Par_gap) + w2·Collapse/3 + w3·Time · (wickets_fallen ≥ 4)
```
- Initial weights w = equal (1/3 each), chosen **before** viewing player outputs. They are then tested in sensitivity analysis (±50% each).
- **Validation of PI:** compute rank correlation of PI with LI at ball level. If Spearman is low (< 0.4), the report explains where they disagree.

---

## 5. Pressure classification and intensity

Primary scale = LI (model A). Tiers are set on **quantiles of the LI distribution among legal balls in completed matches**:

| Tier | Rule (initial; finalised after EDA) | Interpretation |
|---|---|---|
| Low | LI < P50 | Ordinary or decided situations |
| Moderate | P50 ≤ LI < P75 | Some match consequence |
| **High** | P75 ≤ LI < P90 | Clear pressure |
| **Extreme** | LI ≥ P90 | Match-defining moments |

- **"Pressure balls"** for ranking = High + Extreme (top 25% of leverage). Sensitivity: top 15% and top 35%.
- **Intensity weighting:** in the main metric each pressure ball is weighted by `min(LI, cap)` (cap ≈ P99) so extreme moments count more without one ball dominating. Sensitivity: unweighted tier membership.
- Format and competition: tier cut-points are computed **within** IPL and within T20I separately (sensitivity: pooled), so that one competition's scoring environment does not define pressure for the other.

### 5.1 Demonstrating separation ("show how it distinguishes pressure from ordinary")
For each tier, report league-wide: dismissal rate per ball, dot%, boundary%, runs per ball, and how these shift against the Low tier, plus the share of balls by phase and innings. Expected evidence: a monotonic change across tiers with bootstrap CIs. This is a **descriptive validation** of the construct.

Also report **predictive relevance**: the share of total match-outcome WP movement that occurs in High and Extreme balls (e.g., "25% of balls carry X% of win-probability movement").

---

## 6. Situation-specific performance segments (descriptive layer)

In addition to the LI tiers, profile each candidate in interpretable situations:

| Code | Situation | Definition |
|---|---|---|
| S1 | Tight chase, death | Innings 2, overs 16–20, RRR 8–14, WP 15–85% |
| S2 | Rebuild after collapse | ≥ 2 wickets in the previous 18 legal balls |
| S3 | Steep chase | Innings 2, RRR ≥ 10 with ≥ 5 overs remaining, WP ≥ 10% |
| S4 | Defending a close total | Bowling innings 2, runs needed ≤ 1.3 × balls remaining, overs 13–20 |
| S5 | First-innings death below par | Innings 1, overs 16–20, score below expected |
| S6 | Knockout matches | `knock_out = 1` (descriptive only; small n) |

These are used for player profiles and narrative, **not** for the core rating, to avoid multiple-comparison cherry-picking.

---

## 7. Batting pressure vs bowling pressure

- **Same ball, same LI.** For the batter, the job is to raise the team's WP. For the bowler, it is to lower it.
- Batting pressure metrics use **balls faced** (legal balls plus no-balls; wides excluded).
- Bowling pressure metrics use **balls bowled** (all deliveries; legal balls for rates) and runs charged to the bowler.
- Non-striker run-outs are attributed to the dismissed batter, not the striker, for dismissal counts. Run-outs are not credited to the bowler.

---

## 8. Minimum samples (initial; finalised from reliability analysis)

| Entity | Eligibility for ranking (provisional) | Rationale |
|---|---|---|
| Batter | ≥ 120 pressure balls faced **and** ≥ 20 innings with ≥ 1 pressure ball | Approximate. Final values set where split-half reliability of the core metric ≥ 0.5, or reported as weaker. |
| Bowler | ≥ 150 pressure legal balls **and** ≥ 20 matches bowling ≥ 1 pressure over | Same |
| Recency | ≥ 1 IPL or T20I appearance since 1 Jan 2025 (**confirmed, decision D2**) | Relevance to the 2027 auction (sensitivity S-J: no recency filter) |
| Selectable | Present in the actual Unstop dropdown (**decision D4**, task T0) | Applied only at final selection. Never assumed. |

The thresholds are **parameters in `config.yaml`** and are reported alongside how many players each one excludes.

---

## 9. Known limitations of the framework

- The WP model ignores venue-specific pitch and dew conditions beyond a coarse venue effect. Team-strength differences are not in the state.
- Leverage is based on the *state*, not on psychological pressure (crowd, stakes). We measure **match-situational** pressure only, and we say so.
- First-innings pressure is less certain than chase pressure, because no target exists and par must be modelled.
- Impact Player rules (IPL 2023+) change par scores. We include season effects in the scoring and par models.
