"""T2 — Cleaning: apply the data-quality rules Q1–Q15 from planning/02 §6.

Strategy: add flags and derived columns, do not delete rows. Every rule's effect is counted
in outputs/audit_log.md.
Outputs: data_interim/{balls,matches,playing_eleven,players}.parquet
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from common import load_config, path


# --------------------------------------------------------------------------- matches
def clean_matches(m: pd.DataFrame, c: pd.DataFrame, b: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    tcfg = cfg["tiers"]
    m = m.merge(c[["comp_id", "comp_name", "match_format", "season"]], on="comp_id", how="left")
    m["is_ipl"] = m["comp_name"].str.startswith(tcfg["ipl_name_prefix"]).astype(bool)
    m["is_a_team_event"] = m["comp_id"].isin(tcfg["a_team_comp_ids"])
    top = set(tcfg["top_full_members"])
    both_top = m["home_team"].isin(top) & m["away_team"].isin(top)
    m["tier"] = np.select(
        [m["is_ipl"], m["is_a_team_event"], both_top],
        ["T1_IPL", "T4_A_TEAM", "T2_T20I_TOP"], default="T3_T20I_OTHER")
    m["year"] = m["match_date"].dt.year

    res = m["result"].str.lower()
    m["is_no_result"] = m["win_team_id"].isna() & res.str.contains("no result|abandon", regex=True)
    m["is_tie_or_super_over"] = res.str.contains("tie|super over", regex=True)
    m["is_dls"] = m[["first_inn_revised_overs", "second_inn_revised_overs",
                     "revised_target"]].notna().any(axis=1) | res.str.contains("d/l|dls", regex=True)
    m["has_bbb"] = m["match_id"].isin(b["match_id"].unique())

    # Parse the margin only for validation (outcome itself always comes from win_team_id)
    def margin(s: str):
        mm = re.search(r"(\d+)\s*(run|wicket|wkt)", s, re.I)
        if not mm or "super over" in s.lower():
            return pd.NA, pd.NA
        return int(mm.group(1)), ("runs" if mm.group(2).lower() == "run" else "wickets")

    parsed = m["result"].apply(margin)
    m["margin_n"] = parsed.str[0].astype("Int64")
    m["margin_type"] = parsed.str[1].astype("string")
    return m


# --------------------------------------------------------------------------- balls
def clean_balls(b: pd.DataFrame, m: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    ex = cfg["extras"]
    b = b.copy()
    et = b["extras_type"]
    b["is_wide"] = et.isin(ex["wide"])
    b["is_noball"] = et.isin(ex["noball"])
    b["is_non_delivery"] = et.isin(ex["non_delivery"])
    b["is_legal"] = ~(b["is_wide"] | b["is_noball"] | b["is_non_delivery"])
    b["is_ball_faced"] = ~(b["is_wide"] | b["is_non_delivery"])          # batter faced it

    b["total_runs"] = b["runs"] + b["extras1_runs"] + b["extras_2_runs"]
    # Bowler is charged bat runs + the wide/no-ball extras (extras1). extras_2 on no-balls are
    # byes/leg-byes taken off the no-ball and are not charged to the bowler.
    b["bowler_runs"] = b["runs"] + np.where(b["is_wide"] | b["is_noball"], b["extras1_runs"], 0)

    b["is_boundary"] = b["is_four"] | b["is_six"]
    b["is_bat_dot"] = b["is_ball_faced"] & (b["runs"] == 0)
    b["is_bowler_dot"] = b["is_legal"] & (b["bowler_runs"] == 0)

    b["is_bowler_wicket"] = b["is_wicket"] & b["dismissal_type"].isin(cfg["bowler_wicket_types"])
    b["is_batter_dismissal"] = b["is_wicket"] & ~b["dismissal_type"].isin(
        cfg["batter_dismissal_exclude"])
    b["is_super_over"] = b["innings"] > 2

    ph = cfg["phases"]
    b["phase"] = np.select(
        [b["overid"].between(*ph["powerplay"]), b["overid"].between(*ph["middle"])],
        ["PP", "MID"], default="DEATH")

    b = b.merge(m[["match_id", "comp_id", "match_date", "year", "tier", "is_ipl",
                   "is_no_result", "is_dls", "is_tie_or_super_over", "knock_out",
                   "venue_id", "win_team_id"]], on="match_id", how="left")
    b = b.sort_values(["match_id", "innings", "innings_ball_num"], kind="stable").reset_index(drop=True)
    return b


# --------------------------------------------------------------------------- playing XI
def clean_playing_eleven(p: pd.DataFrame, b: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    key = ["match_id", "team_id", "player_id"]
    dup_mask = p.duplicated(key, keep=False)
    dups = p[dup_mask].copy()
    # Reference batting order observed in ball-by-ball for the striker
    ref = (b.groupby(["match_id", "batting_team_id", "striker_id"])["batting_order"].first()
             .rename("bbb_order").reset_index()
             .rename(columns={"batting_team_id": "team_id", "striker_id": "player_id"}))
    dups = dups.merge(ref, on=key, how="left")
    dups["match_bbb"] = dups["batting_order"].astype("float") == dups["bbb_order"]
    dups["_orig_idx"] = p.index[dup_mask]
    dups = dups.sort_values(key + ["match_bbb"], ascending=[True, True, True, False])
    keep_idx = dups.drop_duplicates(key, keep="first")["_orig_idx"]
    drop_idx = set(dups["_orig_idx"]) - set(keep_idx)
    p_clean = p.drop(index=list(drop_idx)).reset_index(drop=True)
    return p_clean, dups.drop(columns="_orig_idx")


# --------------------------------------------------------------------------- players
def build_players(mp: pd.DataFrame, m: pd.DataFrame, b: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Master player list (one row per player_id) with pack-derived nationality hints."""
    tcfg = cfg["tiers"]
    teams_ipl = set(m.loc[m["is_ipl"], "home_team"]) | set(m.loc[m["is_ipl"], "away_team"])
    mp = mp.copy()
    mp["is_ipl_team"] = mp["team_name"].isin(teams_ipl)
    nat = (mp[~mp["is_ipl_team"]].assign(country=mp["team_name"].str.replace(r" A$", "", regex=True))
             .groupby("player_id")["country"].agg(lambda s: "|".join(sorted(set(s)))))
    agg = mp.groupby("player_id").agg(
        player_name=("player_name", "first"),
        teams=("team_name", lambda s: "|".join(sorted(set(s)))),
        n_comps=("comp_id", "nunique"),
        ipl_seasons=("comp_name", lambda s: "|".join(sorted(x[-4:] for x in set(s)
                                                            if x.startswith(tcfg["ipl_name_prefix"])))),
    )
    agg["pack_country"] = nat
    agg["pack_country"] = agg["pack_country"].astype("string")
    # Shared display names -> add team suffix to disambiguate
    dup_names = agg["player_name"].duplicated(keep=False)
    agg["display_name"] = np.where(
        dup_names, agg["player_name"] + " (" + agg["teams"].str.split("|").str[0] + ")",
        agg["player_name"])
    agg["shared_name"] = dup_names

    # Last appearance in ball-by-ball (as batter, non-striker or bowler)
    last = pd.concat([
        b[["striker_id", "match_date"]].rename(columns={"striker_id": "player_id"}),
        b[["non_striker_id", "match_date"]].rename(columns={"non_striker_id": "player_id"}),
        b[["bowler_id", "match_date"]].rename(columns={"bowler_id": "player_id"}),
    ]).groupby("player_id")["match_date"].max()
    agg["last_bbb_date"] = last
    agg["active_since_cutoff"] = agg["last_bbb_date"] >= pd.Timestamp(cfg["eligibility"]["active_since"])
    return agg.reset_index()


# --------------------------------------------------------------------------- run
def run(cfg: dict | None = None) -> dict[str, pd.DataFrame]:
    cfg = cfg or load_config()
    interim = path(cfg, "interim")
    rd = lambda n: pd.read_parquet(interim / f"raw_{n}.parquet")
    c, m, p, mp, b = (rd("competitions"), rd("matches"), rd("playing_eleven"),
                      rd("competition_team_player_mapping"), rd("ball_by_ball"))

    m2 = clean_matches(m, c, b, cfg)
    b2 = clean_balls(b, m2, cfg)
    p2, p_dups = clean_playing_eleven(p, b)
    players = build_players(mp, m2, b2, cfg)

    m2.to_parquet(interim / "matches.parquet", index=False)
    b2.to_parquet(interim / "balls.parquet", index=False)
    p2.to_parquet(interim / "playing_eleven.parquet", index=False)
    players.to_parquet(interim / "players.parquet", index=False)

    write_audit(cfg, m2, b2, p, p2, p_dups, players)
    return {"matches": m2, "balls": b2, "playing_eleven": p2, "players": players}


def write_audit(cfg, m, b, p_raw, p, p_dups, players) -> None:
    out = path(cfg, "outputs")
    L = ["# Audit log — T1/T2 (ingestion & cleaning)", "",
         "Generated by `src/clean.py`. Rows are **flagged, not deleted** (except playing-XI duplicates).", ""]
    L += ["## Matches", "",
          f"- Total matches: {len(m)}; with ball-by-ball: {int(m.has_bbb.sum())}; without: {int((~m.has_bbb).sum())}",
          f"- Tier counts: {m.tier.value_counts().to_dict()}",
          f"- No-result / abandoned: {int(m.is_no_result.sum())} (with bbb: {int((m.is_no_result & m.has_bbb).sum())})",
          f"- Tie / super-over results: {int(m.is_tie_or_super_over.sum())}",
          f"- DLS / reduced matches: {int(m.is_dls.sum())}",
          f"- Knockouts: {int(m.knock_out.sum())}",
          f"- Man-of-the-match missing (0 → NA): {int(m.man_of_the_match.isna().sum())}",
          f"- Margin parsed (validation only): runs {int((m.margin_type=='runs').sum())}, wickets {int((m.margin_type=='wickets').sum())}", ""]
    tier_balls = b.groupby("tier").size().to_dict()
    L += ["## Ball-by-ball", "",
          f"- Rows: {len(b)}; tier split: {tier_balls}",
          f"- Super-over rows (Q1, excluded from ratings): {int(b.is_super_over.sum())}",
          f"- Rows in no-result matches (Q2): {int(b.is_no_result.sum())}",
          f"- Rows in DLS matches (Q3): {int(b.is_dls.sum())}",
          f"- Wides {int(b.is_wide.sum())}, no-balls (Overstep+other) {int(b.is_noball.sum())}, penalty rows {int(b.is_non_delivery.sum())}",
          f"- Legal balls: {int(b.is_legal.sum())}; balls faced: {int(b.is_ball_faced.sum())}",
          f"- Wickets {int(b.is_wicket.sum())}; bowler wickets {int(b.is_bowler_wicket.sum())}; batter dismissals (ex. Retire Out) {int(b.is_batter_dismissal.sum())}",
          f"- bowl_speed missing (0 → NaN, Q6): {b.bowl_speed.isna().mean():.1%}",
          f"- pace_or_spin relabelled from bowling_type (Q7): {int((b.pace_or_spin != b.pace_or_spin_raw).sum())} rows",
          f"- Dismissal spelling fixes applied (Q9): {cfg['dismissal_type_fixes']}", ""]
    L += ["## Playing XI", "",
          f"- Raw rows {len(p_raw)} → cleaned {len(p)} (removed {len(p_raw)-len(p)} duplicate (match,team,player) rows, Q5)",
          f"- Duplicate keys resolved: {p_dups[['match_id','team_id','player_id']].drop_duplicates().shape[0]} "
          f"(kept row matching ball-by-ball batting order where possible; matches affected: {sorted(p_dups.match_id.unique().tolist())})", ""]
    sh = players[players.shared_name][["player_id", "player_name", "teams"]]
    L += ["## Players", "",
          f"- Player IDs: {len(players)}; with a national/A-team appearance in pack: {int(players.pack_country.notna().sum())}",
          f"- Active since {cfg['eligibility']['active_since']} (decision D2, bbb appearance): {int(players.active_since_cutoff.sum())}",
          f"- Shared names (Q11) — kept as separate IDs, display names suffixed:", ""]
    L += [f"  - {r.player_id}: {r.player_name} — {r.teams}" for r in sh.itertuples()]
    (out / "audit_log.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run()
