# 01 — Project Strategy

**Project:** SupeRR Selector Season 2 — Round 1: *Identify the Most Reliable Players Under Pressure*
**Audience:** RR Head Coach (Kumar Sangakkara) and Director of Strategy & Analytics (Giles Lindsay)
**Status:** Planning stage. No rankings or findings yet. Every number in these documents comes from the data audit (see `02_Data_Audit_Plan.md`) or is labelled as a plan or assumption.

---

## 1. Competition objective and expected outcome

### 1.1 What the official brief asks for
The brief is the Round 1 PDF in the data pack. Read it as the source of truth: where the master prompt and the PDF differ, the PDF wins.

> Build a data-driven system that measures how batters and bowlers perform in high-pressure match situations **compared with their usual performance levels**. Use your system to identify and rank the players who deliver most consistently when it matters.

**Required submission (from the PDF):**

| # | Component | Exact requirement |
|---|---|---|
| 01 | Player rankings (Unstop dropdowns) | **Two** ordered top-10 lists: 10 batters under pressure and 10 bowlers under pressure, ranked 1 to 10. No repeats within a list. The dropdowns must match the report. |
| 02 | Methodology report (upload) | Must cover: pressure definition; performance measurement (metrics, baselines, rating logic); fair comparisons (sample sizes, eligibility, match contexts, **use of IPL and T20I data**); evidence for the top 10; reliability and limitations (consistency across matches, where the model is less certain). It must be **reproducible**, and rankings must come from the supplied data, **not reputation**. |
| — | Optional | Journey photos or a 30–60 s video. Not evaluated. |

> ⚠️ **Gap between the master prompt and the official brief.** The master prompt asks for one "TOP 10". The official submission needs **two lists: 10 batters and 10 bowlers**. We will produce both. An all-rounder can appear in both lists, because the rule only bans repeats *within* a list. RR squad-fit and auction analysis is **added value in the report**. It must not be the main driver of the official rankings, which are judged on "best-performing under pressure" (see §4 and `06_RR_Auction_Strategy.md`).

### 1.2 Expected outcome
1. A reproducible Python pipeline that turns the data pack into ball-level pressure labels, player-level pressure ratings, uncertainty estimates and two ranked lists.
2. A methodology report (about 10–15 pages plus appendix) that a franchise analyst could audit.
3. An RR auction overlay showing which ranked players are realistically available, which squad needs they fill, and which ones offer value.

---

## 2. What makes an excellent submission (franchise-analytics view)

| Quality | What RR's analytics department would look for | How we deliver it |
|---|---|---|
| A defensible pressure definition | Pressure grounded in match outcomes, not "all death overs are pressure" | Win-probability **leverage** from a model fitted on this data, plus a transparent rule-based index used to cross-check it |
| Fair comparison | Openers are not compared with finishers on raw strike rate. A 20-ball sample is not trusted like a 300-ball sample. | Context-expected baselines, role groups, empirical-Bayes shrinkage, minimum samples set from measured reliability |
| Pressure **vs usual level** | The brief explicitly asks for performance under pressure *relative to the player's own baseline* | A *pressure differential* component alongside absolute pressure performance |
| Consistency | "Deliver most consistently when it matters" | Match-level dispersion, failure rate in pressure innings or spells, and rank-stability probabilities from a match-cluster bootstrap |
| Honesty about uncertainty | Credible intervals, sensitivity scenarios, explicit limitations | Bootstrap CIs, P(top-10) per player, alternative ranking scenarios |
| Decision usefulness | Turns rankings into auction actions | RR squad gap analysis, availability verification, role fit, value tiers |
| Reproducibility | Someone else can rerun it | Versioned scripts, fixed seeds, a config file for every threshold, and a data dictionary |

---

## 3. Core research questions

1. **RQ1 — Definition:** Which measurable match-state variables in the data pack (balls left, wickets in hand, required rate, target, phase, score vs par) best explain how much a single ball can change the result? Can we turn that into a continuous pressure scale?
2. **RQ2 — Validity:** Does our pressure scale separate situations that are genuinely different? Do league-wide dismissal rate, dot-ball rate and scoring rate shift measurably across pressure tiers?
3. **RQ3 — Batting:** Which batters, after adjusting for context and sample size, (a) perform best in high-pressure situations and (b) hold or improve their own baseline under pressure?
4. **RQ4 — Bowling:** The same question for bowlers: limiting runs and taking wickets in high-leverage balls, relative to context and their own baseline.
5. **RQ5 — Reliability:** Are these pressure skills stable? (Split-half and season-to-season repeatability.) If pressure performance is mostly noise, we must say so and lean more on shrunk estimates.
6. **RQ6 — Competition mix:** How should IPL and T20I evidence (including matches against Associate nations and A-team fixtures) be combined fairly?
7. **RQ7 — RR application:** Among reliable pressure performers, who fills RR's verified squad gaps at realistic auction value?

---

## 4. Overall analytical strategy

```
Data pack ──► Clean and validate ──► Rebuild ball-by-ball match state
                                     (score, wickets, balls left, target, RRR, par)
                     │
                     ▼
         Win-probability model (fitted on the pack, validated out of season)
                     │
       ┌─────────────┴──────────────┐
       ▼                            ▼
 Leverage index (LI)        Rule-based Pressure Index (cross-check)
       └─────────────┬──────────────┘
                     ▼
     Pressure tiers: Low / Moderate / High / Extreme
                     ▼
   Expected-outcome baselines (context models: phase × wickets × format tier × bowling type)
                     ▼
 Player metrics: performance above expected under pressure, own-baseline differential,
                 WPA in high-leverage balls, consistency, sample size
                     ▼
   Empirical-Bayes shrinkage + match-cluster bootstrap ──► rating with CI, P(top-10)
                     ▼
   Role-specific composite (batting and bowling kept separate) ──► sensitivity scenarios
                     ▼
   Official top-10 batters + top-10 bowlers      RR auction overlay (availability, fit, value)
```

**Guiding decision:** the official lists rank on **pressure performance reliability only**, so they are defensible to the judges. The RR layer is a separate section that discusses auction availability, squad fit and value without reordering the official lists. (**Confirmed** by the participant as decision D1; see the decisions log in `07_Execution_Roadmap.md §4`. Also confirmed: D2, players must be active since 1 Jan 2025; D3, a tiered T20I discount; D4, the eligible pool is verified from the actual Unstop form and never assumed.)

---

## 5. Expected deliverables

| Deliverable | Format | Stage |
|---|---|---|
| Eight planning documents (this set) | Markdown | Now |
| Cleaned analytical tables (ball-state, innings, spells) | Parquet (local only) | Build |
| Win-probability model plus calibration report | Python module + figures | Build |
| Pressure labels per ball plus validation charts | Parquet + PNG | Build |
| Player rating tables (batting and bowling) with CIs | CSV (aggregates only) | Analysis |
| Sensitivity and rank-stability report | Markdown + figures | Validation |
| Player verification log (identity, nationality, availability) | CSV with source URLs | Research |
| RR squad gap analysis and auction overlay | Markdown | Strategy |
| **Final methodology report** | PDF/DOCX | Submission |
| **Two ranked top-10 lists** | Entered on Unstop | Submission |

---

## 6. Key differentiators

1. **Pressure = leverage, not phase.** A death-over ball in a 60-run blowout is not pressure. A 14th-over ball with 9 per over needed and 4 wickets left is. We measure this with a win-probability model fitted on this data pack.
2. **Two cross-checking pressure definitions.** A model-based definition (leverage) and an interpretable rule-based index (required-rate gap, wickets in hand, closeness). Rankings must hold under both.
3. **Context-expected baselines.** "Runs above expected" and "economy below expected" control for phase, wickets, format and opposition tier. A 140 strike rate at 8 down in a chase is valued differently from 140 in the powerplay.
4. **"Usual level" made explicit.** Each player gets a pressure differential against their own non-pressure baseline, as the brief asks, combined with absolute pressure quality so that a poor player who is "equally poor under pressure" is not rewarded.
5. **Reliability-driven sample thresholds.** Minimum samples and shrinkage strength come from measured split-half reliability, not arbitrary cut-offs.
6. **Rank uncertainty published.** Every top-10 player gets a bootstrap probability of being top 10, which we use to break near-ties honestly.
7. **Win Probability Added (WPA) in high-leverage moments.** This connects player actions directly to match outcomes.
8. **Opposition-strength tiering.** T20Is against Associates and A-team or emerging tournaments are tiered and adjusted so that results there do not inflate ratings.
9. **RR auction lens.** Verified availability, role-gap mapping and value tiers, with confirmed facts kept separate from assumptions.

---

## 7. Weaknesses in conventional approaches and our fixes

| Conventional approach | Weakness | Our improvement |
|---|---|---|
| "Death overs = pressure" | Treats dead-rubber death overs like tight finishes. Ignores middle-over chase collapses. | Leverage-weighted, state-based pressure |
| Raw strike rate or average in chases | Mixes easy chases with hard ones. Not-outs inflate averages. | Context-expected runs, dismissal-rate modelling, required-rate-aware evaluation |
| Ranking by raw pressure stats | Small samples dominate the top (the "3 innings, SR 220" problem) | Empirical-Bayes shrinkage, reliability-based minimums, bootstrap CIs |
| One universal score | Merges batting and bowling, or openers and finishers | Separate batting and bowling models; role-group priors |
| Arbitrary weights | Weights tuned until the list "looks right" | Weights fixed before seeing names, justified by reliability and validity, then stress-tested |
| IPL and T20I pooled naively | A T20I against an Associate side ≠ an IPL knockout | Competition tiers plus opposition adjustment; IPL-only sensitivity run |
| Reputation-led picks | Explicitly penalised by the brief | Every pick traced to supplied-data evidence |
| Point estimates only | False precision | CIs, P(top-10), and a stated level of certainty per pick |

---

## 8. Constraints and compliance

- The data pack is competition-confidential. Keep all raw data and derived ball-level tables local. Never commit them to a public repository and never expose them on a public dashboard. Final charts show aggregates only.
- External information (nationality, age, retention status, auction rules) must be cited with source and date in the verification log.
- The participant must review and own the final selections and reasoning. AI-assisted analysis is the working draft, not the final judgement.
