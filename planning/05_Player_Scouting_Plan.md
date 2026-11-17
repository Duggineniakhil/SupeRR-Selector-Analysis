# 05 — Player Scouting Plan

**Purpose:** turn model output into verified, defensible scouting judgements. Separate **data evidence** (from the pack), **external facts** (cited), and **analyst interpretation** (labelled).

---

## 1. Funnel

```
All players in mapping (1,217 IDs)
  └─ Stage 0: Activity filter      → recent (since 1 Jan 2025) IPL/T20I appearance
  └─ Stage 1: Eligibility          → min pressure balls & innings/spells (03 §8, finalised by reliability)
  └─ Stage 2: Model ranking        → BPRS / WPRS composite + CI + P(top-10)
  └─ Stage 3: Shortlist            → top ~25 batters, ~25 bowlers + "undervalued watchlist" (§4)
  └─ Stage 4: Deep profile         → scouting card per shortlist player (§2)
  └─ Stage 5: Verification         → checklist (§5); fail = flagged/removed
  └─ Stage 6: Final 10 + 10        → model order; only players confirmed in the actual
                                      Unstop dropdown (T0, decision D4); documented exceptions only
  └─ Stage 7: RR overlay           → availability / fit / value (06)
```

## 2. Scouting card template (per shortlisted player)

| Section | Content | Source |
|---|---|---|
| Identity | player_id, name, teams in pack, nationality, age (DOB), batting hand / bowling type | Pack + ESPNcricinfo (cited) |
| Role | Inferred: modal batting position & phase distribution; bowling overs by phase; keeping | Pack (verify externally) |
| Experience | Matches & balls by tier (IPL / T20I-T2 / T3 / A-team); seasons active | Pack |
| Domestic experience | SMAT / other leagues — *only* as qualitative context, cited | External |
| Pressure output | Pressure balls, RV_P / BV_P (EB) ± CI, WPA_P, SR/Econ_P, dismissal/wkt rates | Pack |
| Usual level | Same metrics on non-pressure balls; Δ | Pack |
| Consistency | Success / failure rate across pressure innings/spells; per-season values | Pack |
| Recent form | 2026 IPL & 2026 T20I values vs career-in-pack | Pack |
| Situational splits | S1–S6 situations (03 §6), vs pace / spin, phase | Pack (descriptive, small-n flagged) |
| Strengths / weaknesses | Evidence-backed bullet points, each citing a metric | Pack |
| IPL suitability | IPL sample size, IPL-only rating vs combined | Pack |
| Uncertainty | n, CI width, P(top-10), sensitivity rank range | Pack |
| Availability | Contracted / retained / released / unsold (IPL 2027), injury, NOC | External, dated |

## 3. Interpretation rules

- No claim without a number and its sample size ("SR 162 on 148 pressure balls", not "brilliant finisher").
- Splits with < 60 balls (batting) / < 60 legal balls (bowling) are labelled "indicative".
- Never cite a single match as evidence of reliability.
- Distinguish: *descriptive* ("has been") vs *predictive* ("will be") language — predictive language only with the out-of-time validation result attached.

## 4. Identifying undervalued players (not just famous names)

Flag a player as a **value candidate** if any holds (all from data unless stated):
1. High EB-shrunk pressure rating but low total visibility — e.g., < 25 IPL matches, or mostly T20I-T2/T3 evidence that survives the tier discount.
2. Strong Δ (holds/raises level under pressure) with an average overall profile → specialist value.
3. Uncapped Indian players (no India/India A appearances in pack; nationality verified externally) with eligible pressure samples in IPL.
4. Strong 2026 form with modest 2022–24 record (rising trajectory) — flagged, but trend claims only if season split has adequate n.
5. Previous auction price / unsold status low relative to rating (external, cited) — RR overlay only.

Undervalued players appear in the **official top-10 only if the model ranks them there**; otherwise they go to a separate "watchlist" in the report.

## 5. Player verification checklist (every shortlisted player)

| # | Check | Pass criterion |
|---|---|---|
| V1 | ID integrity | Single player_id; all balls/matches attributed belong to that ID; not one of the 7 shared-name cases, or resolved |
| V2 | Name disambiguation | Display name + team in report; matches Unstop dropdown entry (confirm the dropdown name/spelling) |
| V3 | Nationality | Confirmed from 2 sources (pack appearance + ESPNcricinfo/IPLT20) |
| V4 | Age / DOB | From ESPNcricinfo; date accessed recorded |
| V5 | Role | Pack-inferred role agrees with public role; discrepancies explained |
| V6 | Data sanity | Spot-check 2–3 of the player's pressure innings/spells against public scorecards (totals only) |
| V7 | Recency | Last appearance date in pack; any known long-term injury/retirement (cited) |
| V8 | Auction status | Retained / released / available for IPL 2027 — official source + date; else marked "unverified" |
| V9 | No reputation leakage | Ranking position equals model output; any manual deviation documented with reason |
| V10 | Claim audit | Every sentence in the player's card maps to a table cell or citation |

Output: `research/verification_log.csv` (player_id, check, status, source URL, date, notes).

## 6. Bias guards in scouting

- Review the shortlist **sorted by model**, with names hidden for the first pass where practical (blind review of metric rows), to reduce reputation bias.
- Explicitly review players ranked 11–20 to check the boundary decisions are model-driven.
- Cross-check: are any top-10 players there mainly because of T3/T4 opposition? (tier-mix column).
