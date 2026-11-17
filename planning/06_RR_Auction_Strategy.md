# 06 — RR Auction Strategy Framework

**Role of this layer:** The official Unstop lists rank *pressure performance*. This document is the RR auction overlay in the report: given those rankings, **who should RR back, for which role, and at what priority**. It **never** reorders the official lists (decision D1, confirmed; see `07 §4`).

**Evidence labels used throughout:**
- **[DATA]** = derived from the data pack
- **[CONFIRMED]** = official source (IPL/BCCI/RR), with URL and date
- **[REPORTED]** = credible media, not official
- **[ASSUMPTION]** = our working assumption, to be replaced

---

## 1. Starting point: what the pack tells us about RR

- RR = `team_id 3`. Squads appear in the mapping for IPL 2022 to 2026 **[DATA]**.
- The IPL 2026 RR squad in the pack has 27 players **[DATA]**: Ravindra Jadeja, Adam Milne, Sandeep Sharma, Dasun Shanaka, Shimron Hetmyer, Jofra Archer, Sam Curran, Riyan Parag, Tushar Deshpande, Yashasvi Jaiswal, Dhruv Jurel, Sushant Mishra, Nandre Burger, Ravi Bishnoi, Kuldeep Sen, Donovan Ferreira, Yudhvir Singh, Shubham Dubey, Kwena Maphaka, Yash Punja, Lhuan Pretorius, Emanjot Singh Chahal, Aman Rao Perala, Vignesh Puthur, Vaibhav Sooryavanshi, Ravi Singh, Brijesh Sharma.
- ⚠️ **This is the 2026 squad, not the 2027 squad.** The IPL 2027 retention and release list, remaining purse, auction type (mini or mega), and overseas and squad-size limits are **not in the pack**. All of them must be **[CONFIRMED]** from official sources before any squad-gap claim. The retention window for an auction in the 2026–27 off-season may already have closed by now (17 Nov 2026). Verifying this is task #1 of the RR research.

## 2. Squad assessment framework

### 2.1 Build the "confirmed 2027 core"
`core_2027 = IPL 2026 RR squad − released − traded out + traded in` (each change **[CONFIRMED]**).

### 2.2 Profile the core using pack data (2025–26 weighted)
For each core player, compute from the pack:

| Dimension | Metric [DATA] | Gap signal |
|---|---|---|
| Top-order batting | Powerplay RV, balls faced in positions 1–3 | Few high-RV options |
| Middle-order / anchor under pressure | RV_P in overs 7–15, Δ | Negative Δ or low RV_P |
| **Finishing** | RV_P and WPA in overs 16–20 batting, positions 5–8 | Fewer than 2 reliable finishers |
| Pace (new ball) | Powerplay BV | |
| **Death bowling** | BV_P in overs 16–20, W9 extras rate | Fewer than 2 reliable death bowlers |
| Spin (middle overs) | BV_P in overs 7–15 by spinners | |
| Left/right balance | batting_type mix in the top 7; left-arm options | |
| Keeping | is_wk history | Backup keeper |
| Indian / overseas | Nationality (verified) | Overseas slots left; Indian quality depth |

Output: an **RR need matrix**. Each role gets a severity score (0 = covered, 1 = thin, 2 = gap) and a short evidence note. The severity rules are fixed in advance (e.g., "gap = fewer than 2 core players with eligible, above-median pressure rating in that role").

### 2.3 Role redundancy
Flag shortlisted players whose role duplicates a covered core strength (e.g., another left-handed top-order batter if two already exist). They may still rank in the official list, but get lower **RR priority**.

## 3. Auction availability and eligibility

| Check | Source |
|---|---|
| Player not retained by any franchise / in the IPL 2027 auction pool | Official auction list **[CONFIRMED]**. Until it is published: "registered/expected", or **[ASSUMPTION]** |
| Overseas availability (international calendar overlap, NOC) | Board announcements **[REPORTED]**/**[CONFIRMED]** |
| Any player-level auction restriction (e.g., IPL rules on players who withdrew previously) | IPL player regulations **[CONFIRMED]** |
| Already at RR | Not an auction target. Mark as "retain/back", not "buy" |

Players in the official top 10 who are not available are kept in the list (it is a performance ranking). In the RR overlay they are marked **"Not available – benchmark"**.

## 4. Value-for-money framework

`RR Priority = f(Pressure rating tier, Role need severity, Availability, Expected cost tier, Risk)`

| Factor | Measure |
|---|---|
| Pressure rating | Composite + P(top-10) from `04` |
| Need fit | RR need-matrix severity for the player's role |
| Cost tier | Previous auction price / base price / capped-uncapped status **[CONFIRMED/REPORTED]**: Low / Mid / High |
| Risk | Sample uncertainty (CI width), age, injury history, availability, reliance on lower-tier evidence |
| Scarcity | How many alternative candidates of similar rating exist for the same role |

**Decision bands:** *Priority Target* (high fit + high rating + available), *Value Target* (good rating, low cost tier, fills a need), *Contingency* (backup if targets go early), *Benchmark only* (not available or no need).

**Auction scenarios** (for the report): (A) the primary target is bought by another team → name the next-best alternative in the same role with a rating comparison; (B) prices run high → value-tier substitutes; (C) Indian vs overseas slot constraints.

## 5. Per-player recommendation template

For each recommended player:
1. **Why RR should consider them**: a one-line thesis tied to evidence.
2. **Squad requirement addressed**: the need-matrix role and its severity.
3. **Role they would perform**: batting position or phase; bowling phase and overs.
4. **Why they are a reliable pressure performer**: RV_P/BV_P with CI, Δ vs baseline, consistency rate, n.
5. **Potential risks**: sample size, tier mix, age, form trend, injury, availability, role overlap.
6. **Why they are a better investment than alternatives**: a comparison table with 2–3 alternatives in the same role (rating, CI, cost tier, risk).

## 6. Guardrails

- No player is recommended **only** because of a high pressure score. A need fit or a value argument is required.
- No squad, retention or price claim without a citation and date.
- Rumours stay labelled **[REPORTED]**, and decisions are not built on them alone.
- The final picks are the participant's own decision. This overlay is decision support.
