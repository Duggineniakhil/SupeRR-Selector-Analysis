"""T1 — Ingestion: load every raw CSV with explicit types and light normalisation.

No rows are dropped here. Output: data_interim/raw_*.parquet
"""
from __future__ import annotations

import pandas as pd

from common import load_config, path

EXPECTED_ROWS = {  # from planning/02 audit
    "competitions": 141,
    "teams": 353,
    "matches": 883,
    "playing_eleven": 28381,
    "competition_team_player_mapping": 6413,
    "ball_by_ball": 200999,
}


def _bool(s: pd.Series) -> pd.Series:
    """Map true/false strings or bools to pandas nullable boolean."""
    if s.dtype == bool:
        return s.astype("boolean")
    return s.map({True: True, False: False, "True": True, "False": False,
                  "true": True, "false": False}).astype("boolean")


def load_raw(cfg: dict) -> dict[str, pd.DataFrame]:
    raw = path(cfg, "raw")
    out: dict[str, pd.DataFrame] = {}

    c = pd.read_csv(raw / "competitions.csv", dtype={"season": "string"})
    c["comp_name"] = c["comp_name"].astype("string")
    c["match_format"] = c["match_format"].astype("string")
    out["competitions"] = c

    out["teams"] = pd.read_csv(raw / "teams.csv")

    m = pd.read_csv(raw / "matches.csv")
    m["match_date"] = pd.to_datetime(m["match_date"], format="%Y-%m-%d")
    for col in ["home_team_captain_id", "away_team_captain_id", "toss_win_team_id",
                "first_inn_revised_overs", "second_inn_revised_overs", "revised_target",
                "win_team_id"]:
        m[col] = m[col].astype("Int64")
    m["man_of_the_match"] = m["man_of_the_match"].replace(0, pd.NA).astype("Int64")
    m["knock_out"] = m["knock_out"].astype(bool)
    out["matches"] = m

    p = pd.read_csv(raw / "playing_eleven.csv")
    p["batting_order"] = p["batting_order"].astype("Int64")
    for col in ["is_played", "is_captain", "is_wk"]:
        p[col] = _bool(p[col])
    p["is_impact"] = p["is_impact"].astype(bool)
    p["is_impact_off"] = p["is_impact_off"].astype(bool)
    out["playing_eleven"] = p

    out["competition_team_player_mapping"] = pd.read_csv(
        raw / "competition_team_player_mapping.csv")

    b = pd.read_csv(raw / "ball_by_ball.csv", low_memory=False)
    for col in ["is_four", "is_six", "is_wicket"]:
        b[col] = b[col].astype(bool)
    for col in ["dismissal_type_id", "dismissed_player_id"]:
        b[col] = b[col].astype("Int64")
    b["dismissal_type"] = b["dismissal_type"].replace(cfg["dismissal_type_fixes"])
    b["bowl_speed"] = b["bowl_speed"].where(b["bowl_speed"] > 0)       # 0 = missing
    b["pace_or_spin_raw"] = b["pace_or_spin"]
    b["pace_or_spin"] = b["bowling_type"].isin(cfg["spin_bowling_types"]).map(
        {True: "Spin", False: "Pace"})                                    # fixes 129 mislabels
    out["ball_by_ball"] = b

    for name, df in out.items():
        assert len(df) == EXPECTED_ROWS[name], f"{name}: {len(df)} rows != {EXPECTED_ROWS[name]}"
    return out


def run(cfg: dict | None = None) -> dict[str, pd.DataFrame]:
    cfg = cfg or load_config()
    dfs = load_raw(cfg)
    interim = path(cfg, "interim")
    for name, df in dfs.items():
        df.to_parquet(interim / f"raw_{name}.parquet", index=False)
    return dfs


if __name__ == "__main__":
    for k, v in run().items():
        print(f"{k:35s} {v.shape}")
