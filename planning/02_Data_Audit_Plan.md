# 02 — Data Audit Plan (and initial audit findings)

All facts below come from actually profiling the files with the scripts in `scripts/` (`profile_data.py`, `profile_deep.py`, `profile_semantics.py`, `profile_coverage.py`). They describe the data pack only; they are not cricket findings.

Data location: `E:\Rajastan\Data Pack\` (plus a `__MACOSX/` folder and a `.DS_Store` file, which are archive artefacts and can be ignored).

---

## 1. File inventory

| File | Format | Size | Rows | Cols | Grain |
|---|---|---|---|---|---|
| `Round 1 Problem Statement _ SupeRR Selector Season 2.docx.pdf` | PDF (2 pages) | 254 KB | — | — | Official brief |
| `ball_by_ball.csv` | CSV | 41.07 MB | 200,999 | 33 | One delivery (including extras) |
| `matches.csv` | CSV | 124 KB | 883 | 22 | One match |
| `competitions.csv` | CSV | 7.6 KB | 141 | 4 | One competition |
| `teams.csv` | CSV | 6.9 KB | 353 | 3 | One competition × team |
| `playing_eleven.csv` | CSV | 966 KB | 28,381 | 9 | One match × team × squad player |
| `competition_team_player_mapping.csv` | CSV | 463 KB | 6,413 | 6 | One competition × team × player |

No file contains exact duplicate rows.

---

## 2. Coverage: competitions, seasons, periods

- **Date range:** 22 Jan 2022 → 1 Nov 2026.
- **Formats:** `match_format` ∈ {`T20I` (134 comps), `T20` (7 comps)}.
  - `T20` = IPL 2022, 2023, 2024, 2025, 2026 (comp_ids 1358, 1715, 2193, 2725, 3298), **Mens T20 Emerging Teams Asia Cup 2024** (2670) and **Asia Cup Rising Stars 2025** (3289). The last two are **A-team / emerging** events (India A, Pakistan A, Sri Lanka A, Bangladesh A, Afghanistan A), not IPL.
- `season` is a **string**. It includes split seasons `2022/23`, `2023/24`, `2024/25`. Derive the year from `match_date`, not `season`.
- **Matches per calendar year:** about 74 IPL matches each year (full seasons), plus 66–137 other matches.
- **Deliveries:** IPL 87,687 (44%); T20I and A-team 113,312 (56%).
- **IPL 2026** has 74 matches with ball-by-ball data, 28 Mar → 31 May 2026. This is the most recent IPL evidence.
- **Notable absences:** the competitions list has **no ICC Men's T20 World Cup** (2022, 2024 or 2026). T20I coverage is a *subset* of bilateral and tri-series, Asia Cup 2022 and 2025, and Asia Cup qualifiers. It is not all T20Is. The report must state this.
- 3 competitions have no matches (Afghanistan v Sri Lanka 2026, UAE in Nepal 2026, India in Bangladesh 2025).
- 16 matches in `matches.csv` have **no ball-by-ball rows**. All ball-by-ball matches exist in `matches.csv`.
- Teams (38): 10 IPL franchises; full members; Associates (Canada, Hong Kong, Japan, Kuwait, Nepal, Netherlands, Oman, Scotland, Singapore, UAE, USA, Ireland*, Zimbabwe*); and A teams. (*Full members in the ICC sense, but generally weaker T20 opponents. We will use a strength tier instead of the ICC label.)
- RR = `team_id 3`.

---

## 3. Column dictionaries (discovered, with inferred semantics)

### 3.1 `competitions.csv`
| Column | Type | Notes |
|---|---|---|
| comp_id | int | PK |
| comp_name | str | Contains year; "IPL YYYY" pattern for IPL |
| match_format | str | T20I / T20 |
| season | str | "2022", "2022/23", … |

### 3.2 `teams.csv`
| comp_id | int | FK → competitions |
|---|---|---|
| team_id | int | 38 distinct teams |
| team_name | str | |

### 3.3 `matches.csv`
| Column | Type | Nulls | Notes |
|---|---|---|---|
| match_id | int | 0 | PK; join key to ball-by-ball / playing XI |
| comp_id | int | 0 | FK |
| match_number | int | 0 | Within competition |
| match_date | date str | 0 | Local date |
| stage | str | 0 | League 620, Others 226 (bilateral series), Final 12, Qualifier 10, Super 4 6, Eliminator 5, Semi Final 4 |
| venue_id | int | 0 | 98 venues — **no venue name**, only id + country |
| venue_country | str | 0 | 17 countries; India 425 |
| home/away_team_id, home/away_team | int/str | 0 | |
| home/away_team_captain_id | float | 44 / 45 | Missing for some matches |
| toss_win_team_id, toss_opted | float/str | 15 | |
| man_of_the_match | int | 0 | **0 = missing** (13.5% of matches) |
| first_inn_revised_overs, second_inn_revised_overs | float | 858 | **Units are balls** (114 = 19 overs, 84 = 14 overs) |
| revised_target | float | 860 | DLS / reduced-match target |
| knock_out | int | 0 | 1 = knockout (31 matches: IPL playoffs, A-team and Asia Cup finals and semis, tri-series finals) |
| win_team_id | float | 41 | Null = No Result (21), Abandoned (19), Tied (1). Super-over wins have a winner. |
| result | str | 0 | Free text with **very inconsistent formatting** ("Won by N Runs", "won by Nruns", "Wkts", DLS variants, super-over text) |

### 3.4 `playing_eleven.csv`
| Column | Type | Nulls | Notes |
|---|---|---|---|
| match_id, team_id, player_id | int | 0 | |
| batting_order | float | 8,678 | Null for non-playing squad members |
| is_played | bool | 0 | False = squad member **not** playing (8,667 rows; IPL squads are listed in full) |
| is_captain, is_wk | bool/obj | 8,667 | Null where is_played = False |
| is_impact | int | 0 | 1 = Impact Player **brought in** (558 rows, IPL 2023–26) |
| is_impact_off | int | 0 | 1 = player **substituted off** (558) |
- **40 duplicate (match, team, player) keys** with conflicting batting orders (e.g., match 13613). Needs dedup rules.
- Rows per team-match range 10–27 (XI plus squad).

### 3.5 `competition_team_player_mapping.csv`
comp_id, comp_name, team_id, team_name, player_id, player_name. 1,217 player_ids, 1,210 names. Every player in ball-by-ball and playing XI appears here. **This is the master player list.**

### 3.6 `ball_by_ball.csv` (33 columns)
| Column | Type | Nulls | Inferred meaning (validated where stated) |
|---|---|---|---|
| match_id | int | 0 | FK |
| innings | int | 0 | 1, 2; **3 and 4 = super overs** (6 matches, 38 balls) |
| overid | int | 0 | Over number 1–20 (1-based) |
| over_ball_num | int | 0 | Delivery index within the over, **including extras** (up to 13) |
| innings_ball_num | int | 0 | Running delivery count in the innings (including extras, max 136). **Use this for ordering.** |
| batting_team_id, bowling_team_id | int | 0 | |
| striker_id/name, non_striker_id/name, bowler_id/name | int/str | 0 | No id maps to two names |
| batting_type | str | 0 | RHB/LHB |
| bowling_type | str | 0 | 12 categories (Right-arm Fast … Left-arm Chinaman) |
| batting_order | int | 0 | Striker's batting position 1–13 (13 is possible because of Impact Player) |
| runs | int | 0 | **Runs off the bat only.** It is 0 on all wides, byes and leg-byes. |
| is_four, is_six | bool | 0 | Boundary flags. 20 deliveries have runs = 4 without is_four (all-run or overthrow) and 25 have runs = 5. |
| is_wicket | bool | 0 | 10,881 wickets |
| dismissal_type_id / dismissal_type | float/str | 190,118 | Caught 7,557; Bowled 1,775; LBW 709; RunOut 600; Stump 214; Hit Wicket 17; Retire Out 6; Obstructing 3 (spelt two ways) |
| dismissed_player_id | float | | It can be the non-striker (277 cases: run-outs) |
| extras_type | str | 189,167 | wide 7,714; legbyes 2,748; **Overstep** (no-ball) 576; byes 529; **other** 264; Penalty 1 |
| extras1_runs | int | 0 | Extras runs on the delivery (1 for a wide or no-ball, plus any extra runs) |
| extras_2_runs | int | 0 | Additional extras (rare: 1 or 4 on no-ball and "other" deliveries) |
| pace_or_spin | str | 0 | Pace/Spin. 129 rows mislabel off-break or SLA bowlers as Pace. |
| bowl_speed | float | 0 | **0 = missing** (38.7% of rows) |
| stroke | str | 3.1% | 30 shot types |
| delivery_style | str | 0.2% | 34 types (Yorker, Slower Bouncer, Googly …) |
| over_or_around, on_or_off | str | ~0.2% / 0 | |
| delivery_ist_time | str | 0 | Timestamp. The first ball of each match is a placeholder "00:00:00". **Do not use it to order deliveries.** |

**Validated semantics (critical for state reconstruction):**
- **Total runs per delivery = `runs + extras1_runs + extras_2_runs`.** Rebuilt innings totals reproduce the official winning margin in **99.2% of 366** runs-margin results without a revised target. The 3 mismatches are DLS results that have no `revised_target`. For 419 wickets-margin results, the wickets margin matches in **99.8%**.
- **Legal ball = extras_type not in {wide, Overstep, other}.** Treating "other" as a no-ball gives 31,757 complete 6-legal-ball overs. Counting it as legal produces 235 seven-ball overs. **"other" behaves like a no-ball.** Penalty runs (1 row) are not a delivery.
- **Bowler-conceded runs = runs + extras on wides and no-balls.** Byes and leg-byes are not charged to the bowler.
- **Bowler wickets** exclude RunOut, Retire Out and Obstructing the field.
- **Balls faced by the batter:** every delivery except wides.

---

## 4. Relationships

```
competitions (comp_id) 1──* matches (comp_id)
competitions (comp_id) 1──* teams (comp_id, team_id)
competitions (comp_id) 1──* competition_team_player_mapping (comp_id, team_id, player_id)
matches (match_id)     1──* playing_eleven (match_id, team_id, player_id)
matches (match_id)     1──* ball_by_ball (match_id)
ball_by_ball.{striker_id, non_striker_id, bowler_id, dismissed_player_id} ──► mapping.player_id
```
All foreign keys resolve (0 orphans in either direction, apart from the 16 matches without ball-by-ball data and the 3 competitions without matches).

---

## 5. Player identity

- `player_id` is the reliable key. **Never join on names.**
- **Shared names with different IDs** (must be handled carefully on the Unstop dropdown and in the report):

| Name | IDs (team context) | Assessment |
|---|---|---|
| Abdul Samad | 7446 (SRH, LSG — Indian); 6922 (Pakistan, Pakistan A) | Different people |
| Haider Ali | 7338 (Pakistan, Pakistan A); 28756 (UAE) | Different people |
| Rashid Khan | 4722 (Afghanistan, GT); 20172 (Nepal) | Different people |
| Bashir Ahmad | 29833 (Afghanistan); 39479 (Afghanistan A) | **Unclear — verify** |
| Mohammad Ali | 3083; 20229 (both Pakistan) | **Unclear — verify** |
| Muhammad Farooq | 27373; 28978 (both UAE) | **Unclear — verify** |
| Basil Hameed | 8638; 39444 (both UAE) | **Possibly one person with two IDs — verify** |

- **No nationality, date of birth or playing-role field exists.** We can infer some of these:
  - Of 477 IPL players, 250 also appear for a national or A team in the pack (86 of them for India or India A). No player appears for two countries.
  - **227 IPL players have no national or A-team appearance** in the pack (likely uncapped Indians, or overseas players whose national series are not covered). Their nationality must be researched.
  - The role (batter, bowler, all-rounder, wicketkeeper) can be inferred from balls faced and bowled, batting position and the `is_wk` flag. Age needs external research.

---

## 6. Data-quality issues and handling

| # | Issue | Size | Handling |
|---|---|---|---|
| Q1 | Super-over innings (3/4) | 38 balls, 6 matches | Exclude from rating baselines. Optionally report them as descriptive extreme-pressure evidence. |
| Q2 | No-result / abandoned matches that have ball-by-ball data | 24 matches | Exclude from win-probability training (no outcome). Keep balls for non-outcome metrics only if the innings is meaningful (sensitivity check). |
| Q3 | Reduced-overs / DLS matches | ~25 matches | Use revised overs (in balls) and the revised target for second-innings state. If the revision is ambiguous, drop the match from win-probability fitting. |
| Q4 | Messy result text | 670 distinct strings | Do not parse it for outcomes. Use `win_team_id`, and use text only to flag super-over ties. |
| Q5 | Playing XI duplicate keys | 40 rows | Keep the row whose batting order matches ball-by-ball. Otherwise take the first, and log it. |
| Q6 | bowl_speed = 0 placeholder | 38.7% | Treat as NaN. Not used in core metrics. |
| Q7 | pace_or_spin mislabels | 129 rows | Derive pace/spin from `bowling_type`. |
| Q8 | delivery_ist_time placeholder | first ball | Order by (match_id, innings, innings_ball_num). |
| Q9 | Dismissal-type spelling variants | 3 rows | Normalise. |
| Q10 | MoM = 0 | 13.5% | Not used. |
| Q11 | Duplicate-name IDs | 7 names | Keep IDs separate. Use a display name with a team suffix. |
| Q12 | Retired-out / retired-hurt | 6 rows | Retired out is not a bowler wicket. Treat it as a dismissal for the batter? → decision: exclude it from dismissal counts (tactical retirements are not failures). |
| Q13 | Incomplete T20I universe (no World Cups) | — | Disclose it. Weight competitions by tier. Run an IPL-only sensitivity check. |
| Q14 | Impact Player | 558 subs | Counts as normal participation. Affects batting-order depth (positions up to 12–13). |
| Q15 | Innings ending early (chase completed or all out) | 356 innings with <20 overs and <10 wickets | Expected (successful chases, DLS). It must not be read as a data truncation. Check a sample manually. |

---

### 6.1 Issues found during T3 (state rebuild), with resolutions

| # | Issue | Matches | Resolution |
|---|---|---|---|
| Q16 | Rain-shortened matches with **blank** revised-overs fields | 15795 (12 ov), 31278 (16 ov), 48514 (12 ov), 23674 (17 ov) | Limit inferred from innings-1 legal balls, rounded up to a whole over (`state.inferred_reduced_limit`) |
| Q17 | Chase target unknown or superseded (a DLS result with no `revised_target`, or play continuing past the recorded target) | 20182, 23674, 24822, 28334, 48610 | `target_reliable = False`. These innings are excluded from win-probability modelling (`wp_usable`). |
| Q18 | One delivery missing from the innings | 14130 (both innings 119 legal balls; margin off by 1), 14164 | Kept. The effect on state is negligible. Logged. |
| Q19 | 7-legal-ball over (scoring anomaly) | 41509 inn 1 over 12 | Kept as recorded |
| Q20 | Wicket margin mismatch | 20190 | Kept. One wicket discrepancy, logged. |

Result after fixes: 11/11 state checks pass (`outputs/validation/state_checks.md`). **188,218 of 192,411** regular-innings legal balls are usable for win-probability modelling.

## 7. Sample volume (for planning thresholds)

- Batters: 326 with ≥100 balls faced (all contexts); 171 with ≥300; 122 with ≥500.
- Bowlers: 309 with ≥120 legal balls; 183 with ≥300; 101 with ≥600.
- Pressure subsets will be much smaller (perhaps 15–30% of balls, depending on the definition). The minimum samples (`03 §8`) are finalised from the reliability and stabilisation analysis (`04 §8`, `07 T10`).

---

## 8. Directly available vs requires external research

| Information | In pack? | Source if not |
|---|---|---|
| Ball-level outcomes, match state, target, result | ✅ (state must be rebuilt) | — |
| Phase, wickets, required rate, DLS revisions | ✅ (derived) | — |
| Bowling type, batting hand, delivery style, stroke | ✅ | — |
| Venue identity | ⚠️ id + country only | Not needed for core analysis. Venue scoring effects are estimated from venue_id. |
| Player nationality (Indian or overseas) | ⚠️ partial (inferred for about half of IPL players) | ESPNcricinfo / IPLT20.com profiles |
| Age, date of birth | ❌ | ESPNcricinfo |
| Playing role and keeping | ⚠️ inferred | Verify externally |
| IPL 2027 retention / release list, RR purse | ❌ | Official IPL / RR announcements (Nov 2026) |
| Auction format (mega or mini), slot and overseas limits, base prices | ❌ | Official IPL communication |
| Injuries, availability (international calendar), NOC status | ❌ | Official board and franchise news |
| Previous auction prices (value-for-money) | ❌ | Public auction records |
| Domestic T20 (SMAT) and other leagues | ❌ | Out of scope for ratings. Optional qualitative context only. |

---

## 9. Remaining audit tasks (in implementation)

1. Rebuild the state for every legal ball and assert invariants: the score is monotonic, wickets ≤ 10, legal balls ≤ 120 (or the revised limit), and the final score equals the recorded margin.
2. Manually check 10 random matches against public scorecards (top-level totals only).
3. Resolve the 4 "unclear" duplicate-name cases.
4. Document every exclusion with counts in `outputs/audit_log.md`.
