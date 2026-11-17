# 07 — Execution Roadmap

## 1. Technology stack

| Purpose | Tool | Why |
|---|---|---|
| Data wrangling | **pandas 2.3**, NumPy 2.3 (installed: Python 3.13.4, pandas 2.3.1, NumPy 2.3.1, SciPy 1.16.0) | Already available. 201k rows fit easily in memory. |
| Storage of derived tables | Parquet (pyarrow) | Fast and typed. Kept **local only**. |
| Statistics | **SciPy**, **statsmodels** (GLM, splines, logistic) | Interpretable models and standard errors |
| WP model challenger / calibration | **scikit-learn** (LogisticRegression, HistGradientBoosting with monotonic constraints, `calibration_curve`) | Simple and well tested |
| Visualisation | **Matplotlib** (report figures), **Plotly** (local exploration only) | No public dashboard (confidentiality) |
| Config / reproducibility | `config.yaml`, fixed random seeds, `requirements.txt` | Every threshold is in one place |
| Report | Markdown → DOCX/PDF | |

No deep learning: the problem is small-data and needs to be interpretable.

**Proposed project layout**
```
E:\Rajastan\
  Data Pack\            (raw, read-only, never modified)
  planning\             (these docs)
  scripts\              (profiling scripts already written)
  src\                  (pipeline modules: ingest, state, wp, pressure, metrics, shrink, rank, viz)
  config.yaml
  data_interim\         (parquet; local only, git-ignored)
  outputs\              (aggregated tables, figures, audit_log.md)
  research\             (verification_log.csv, rr_squad_2027.md with citations)
  report\               (final methodology report)
```
Python that reads the data pack runs with `python -I` from outside `Data Pack/`.

## 2. Task plan

| # | Task | Objective | Approach | Output | Depends on | Priority | Validation |
|---|---|---|---|---|---|---|---|
| T1 | Ingestion | Load all CSVs with explicit dtypes | `src/ingest.py`; parse bools and dates; normalise dismissal text; derive pace/spin from bowling_type; bowl_speed 0 → NaN | `interim/*.parquet` | — | P0 | Row counts match the audit (200,999 / 883 / 28,381 …) |
| T2 | Cleaning | Apply the Q1–Q15 rules (`02 §6`) | Flags rather than deletions; exclusion log | `audit_log.md` | T1 | P0 | Every exclusion counted and justified |
| T3 | Match-state rebuild | Score, wickets, legal balls, balls left, target, RRR, CRR, DLS limits, partnership, recent wickets | Cumulative sums ordered by innings_ball_num; legal-ball rules (`02 §3.6`) | `ball_state.parquet` | T2 | P0 | Final totals reproduce result margins (≥ 99%); wickets ≤ 10; legal balls ≤ limit |
| T4 | EDA | Understand distributions by tier, phase, season | Scoring by phase × season × tier; dismissal rates; Impact Player era effect | `outputs/eda/*.png` | T3 | P1 | Plots reviewed; anomalies logged |
| T5 | Expected-runs / par model | First-innings expected remaining runs; wicket run value λ_ctx | Cell means with smoothing, or a Poisson GLM, on (balls left, wickets, tier, season) | `par_model.pkl`, λ table | T3 | P0 | Out-of-season MAE vs naive; monotonic in wickets |
| T6 | Win-probability model | P(win \| state) | Spline logistic GLM; HistGB challenger; leave-one-season-out CV | `wp_model.pkl`, calibration plots | T3, T5 | P0 | Calibration slope ≈ 1, Brier < phase-only baseline; monotonic checks |
| T7 | Pressure labelling | LI, WPA, PI, tiers, situations S1–S6 | `03 §3–6` | `pressure.parquet` | T6 | P0 | Tier separation table; LI vs PI Spearman; WP-movement share in top 25% LI |
| T8 | Context baselines | E[runs], E[out], E[dot], E[4/6], E[conc], E[wkt] per ball | Hierarchical cell means (`04 §2`) | columns on ball table | T7 | P0 | League residuals sum to ≈ 0 per context |
| T9 | Feature engineering | Player × {P, N} metrics B1–B12, W1–W12, C1–C5; recency weights; tier credibility | groupby with weights | `player_bat.parquet`, `player_bowl.parquet` | T8 | P0 | Totals reconcile with simple aggregates (runs, wickets) |
| T10 | Reliability analysis | Split-half and season-to-season reliability; stabilisation n\* | Odd/even matches; Spearman-Brown | `reliability.md` | T9 | P0 | Decides eligibility thresholds and any reliability-based weight adjustment (pre-stated rule) |
| T11 | Shrinkage + composite | EB estimates, z-scores, BPRS / WPRS | `04 §8, §10` | ranked tables | T10 | P0 | Weights locked in config **before** viewing names |
| T12 | Bootstrap uncertainty | CIs, median rank, P(top-10) | 2,000 match-cluster resamples (seeded) | `rank_uncertainty.csv` | T11 | P0 | Runtime acceptable; results stable across 2 seeds |
| T13 | Sensitivity & scenarios | Robustness of the top 10 | `08 §3` scenario grid | `sensitivity.md` (overlap / Kendall τ) | T12 | P0 | Report how many of the top 10 appear in ≥ 80% of scenarios |
| T14 | Out-of-time validation | Is the composite predictive? | Train 2022–24, test 2025–26 pressure value | `validation.md` | T11 | P1 | Composite beats raw SR / economy correlation; honest report if not |
| T15 | Shortlist & scouting cards | Profiles for the top ~25 + watchlist | `05 §2` template | `outputs/cards/*.md` | T12 | P1 | Every claim maps to a table cell |
| T16 | External verification | Identity, nationality, age, IPL 2027 status | ESPNcricinfo / IPLT20 / RR official | `research/verification_log.csv` | T15 | P0 | V1–V10 checklist complete |
| T17 | RR squad analysis | Confirmed 2027 core, need matrix | `06 §2` | `research/rr_squad_2027.md` | T16 | P1 | All squad facts are [CONFIRMED] with dates |
| T18 | Visualisation | Report-grade figures | Matplotlib: tier-separation chart, LI by phase, forest plots (rating ± CI) of top 20, scenario-stability heatmap, scouting radar/bar per pick | `outputs/figures/` | T12–T17 | P1 | Aggregates only; readable in greyscale |
| T19 | Final report | Methodology report + lists | Sections mirror the PDF's required headings | `report/*.docx/pdf` | all | P0 | Reproducible from scripts; peer read-through; dropdown names match the report |
| T20 | Submission QA | Unstop entry | Check spellings and IDs for duplicate-name players; no repeats within a list | Checklist | T19 | P0 | Second-person check |

### 2.1 Progress

| Task | Status (17 Nov 2026) | Evidence |
|---|---|---|
| T1 Ingestion | ✅ Done | `src/ingest.py`; row counts asserted against the audit |
| T2 Cleaning | ✅ Done | `src/clean.py`; `outputs/audit_log.md` (tiers: IPL 371 / T2 339 / T3 143 / A-team 30 matches; 633 players active since 2025) |
| T3 State rebuild | ✅ Done | `src/state.py`; 11/11 checks in `outputs/validation/state_checks.md`; new issues Q16–Q20 in `02 §6.1` |

| T5 Par / ERR model | ✅ Done | `src/models_par.py`; `outputs/validation/err_model.md`. Three candidates were compared by leave-one-season-out CV. **Selected: DLS-style resource curve** `(env/160)·Z_w·(1−e^(−k_w·b))` (LOSO MAE 16.63 vs naive 17.34). The spline GLM was rejected because it failed the monotonicity gate (implausible extrapolation, negative wicket values), even though its MAE was similar. Scoring environment `env_par` = shrunk tier × season mean first-innings total (IPL 171 → 196, 2022 → 2026). |
| T6 Win-probability | ✅ Done | `src/models_wp.py`; `outputs/validation/wp_model.md`. **Selected: spline logistic GLM for both innings.** It passes the monotonicity gate on 100,800 / 61,200 state grids and beats the HGB challenger on LOSO log-loss. Chase: log-loss 0.387 (phase-only baseline 0.602), AUC 0.91, calibration slope 1.04. First innings: log-loss 0.629 (baseline 0.666), AUC 0.71, slope 1.01. Innings-break continuity gap: median 0.03. A feasibility cap (WP ≤ 0.01 when runs needed > 6 × balls left) handles extras-only states. Per-delivery `wp_before` / `wp_after` are in `data_interim/wp.parquet` (99.8% coverage). |

| T7 Pressure labelling | ✅ Done | `src/pressure.py`; `outputs/validation/pressure_validation.md`; `data_interim/pressure.parquet` (LI, leverage weight, tier, WPA, PI, S1–S6 per delivery). Pressure balls (top 25% LI) carry 49.8% of win-probability movement. See `03 §8a` for the construct evidence and the definition changes. |

Run: `python -I src/run_pipeline.py` from the project root (about 15 s). Outputs go to `data_interim/` (local only, git-ignored).

## 3. Suggested sequence (critical path)
T1 → T2 → T3 → T5 → T6 → T7 → T8 → T9 → T10 → T11 → T12 → T13 → T15 → T16 → T19 → T20.
In parallel once T3 is done: T4 (EDA). In parallel with modelling: start T17 (RR squad facts) early, because it depends only on external sources.

## 4. Decisions log (confirmed by the participant, 17 Nov 2026)

| # | Question | Decision | Effect on plan |
|---|---|---|---|
| D1 | Official lists vs RR overlay | **Pure pressure rank.** The two Unstop top-10 lists are ordered only by BPRS / WPRS. RR fit, availability and value appear only in the report's RR section (`06`). | `06` must never reorder the lists. T19 checks this. |
| D2 | Recency / activity filter | **Active since 1 Jan 2025.** A player needs ≥ 1 IPL or T20I appearance (in the pack) on or after 2025-01-01. Older matches still count, down-weighted by the recency half-life. | Applied at Stage 0 (`05 §1`) and `03 §8`. The "no filter" run stays as sensitivity scenario S-J. |
| D3 | T20I weighting | **Tiered discount.** T1 IPL = full weight; T2/T3/T4 discounted by the tier credibility factor (`04 §6`). IPL-only is a sensitivity scenario (S-E). | As in `04 §6`. |
| D4 | Unstop dropdown pool | **Verify from the actual submission form. Do not invent or assume the eligible player pool.** | New blocking task **T0** (below). Until it is done, rankings are computed over the data-pack eligible pool and labelled *provisional*. No player is finalised until confirmed in the form. |

**Still open (not blocking now):** confirm that ESPNcricinfo / IPLT20.com / official RR channels are acceptable external sources. The participant signs off on the final picks.

### T0 — Verify the Unstop dropdown pool (blocking for T19 and T20)
- **Objective:** know exactly which players can be selected, and how their names are spelt.
- **Approach:** the participant opens the Unstop submission form and records the batter and bowler dropdown options (export, screenshot or copy). We store them in `research/unstop_dropdown_pool.csv`, then match them to `player_id` by name + team. Any ambiguous match (shared names: Abdul Samad, Rashid Khan, Haider Ali, Mohammad Ali, Muhammad Farooq, Bashir Ahmad, Basil Hameed) is resolved manually and logged.
- **Output:** the mapping table, plus a list of model-ranked players **not** in the dropdown and dropdown players **not** in the data pack.
- **Rule if a ranked player is missing from the dropdown:** they are not submitted. The next-ranked player who is in the dropdown takes the slot, and the report notes this. Nothing is assumed in advance.
- **Validation:** every final pick has a confirmed dropdown entry with the matching spelling.
- **Priority:** P0 (must be done before T19 and T20; it does not block modelling T1–T14).
