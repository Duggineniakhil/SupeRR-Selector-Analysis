"""T3 — Match-state reconstruction for every delivery.

"_before" columns describe the state when the ball is bowled (what pressure models use);
"_after" columns describe the state once it is completed (for WPA later).
Outputs: data_interim/ball_state.parquet, data_interim/innings.parquet,
         outputs/validation/state_checks.md
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import load_config, path

KEY = ["match_id", "innings"]


def inferred_reduced_limit(b: pd.DataFrame, m: pd.DataFrame, cfg: dict) -> pd.Series:
    """Reduced-overs matches where the pack has no revised-overs field (e.g. 15795, 31278, 48514).

    Rule: decided match, no revised fields, innings 1 ended with < 10 wickets and short of
    the default limit by more than one ball (1 missing ball = data gap, not a reduction),
    and innings 2 did not go beyond innings 1's overs → limit = innings-1 legal balls,
    rounded up to a whole over.
    """
    d = cfg["default_ball_limit"]
    reg = b[b.innings <= 2]
    s = reg.groupby(["match_id", "innings"]).agg(legal=("is_legal", "sum"), wk=("is_wicket", "sum"),
                                                 max_over=("overid", "max")).unstack()
    s.columns = [f"{a}{c}" for a, c in s.columns]
    mm = m.set_index("match_id")
    no_rev = mm[["first_inn_revised_overs", "second_inn_revised_overs", "revised_target"]].isna().all(axis=1)
    s = s.join(no_rev.rename("no_rev")).join(mm["is_no_result"])
    cand = (s.no_rev & ~s.is_no_result & (s.wk1 < 10) & (s.legal1 < d - 1)
            & (s.max_over2.fillna(0) <= s.max_over1))
    return (np.ceil(s.loc[cand, "legal1"] / 6) * 6).astype(int)


def ball_limits(m: pd.DataFrame, cfg: dict, inferred: pd.Series | None = None) -> pd.DataFrame:
    """Legal-ball limit per (match, innings). Revised overs in the pack are already in balls."""
    d = cfg["default_ball_limit"]
    inf = (inferred if inferred is not None else pd.Series(dtype=int)).reindex(m["match_id"]).to_numpy()
    first = m["first_inn_revised_overs"].astype("float").fillna(pd.Series(inf, index=m.index))
    lim1 = first.fillna(d)
    lim2 = m["second_inn_revised_overs"].astype("float").fillna(first).fillna(d)
    so = cfg["super_over_ball_limit"]
    rows = []
    for inn, lim in [(1, lim1), (2, lim2), (3, pd.Series(so, index=m.index)),
                     (4, pd.Series(so, index=m.index))]:
        rows.append(pd.DataFrame({"match_id": m["match_id"], "innings": inn,
                                  "ball_limit": lim.astype(int)}))
    return pd.concat(rows, ignore_index=True)


def build_state(b: pd.DataFrame, m: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    b = b.sort_values(KEY + ["innings_ball_num"], kind="stable").reset_index(drop=True)
    g = b.groupby(KEY, sort=False)

    # Cumulative state after each delivery, and shifted to "before"
    b["score_after"] = g["total_runs"].cumsum()
    b["wkts_after"] = g["is_wicket"].cumsum().astype(int)
    b["legal_after"] = g["is_legal"].cumsum().astype(int)
    b["score_before"] = b["score_after"] - b["total_runs"]
    b["wkts_before"] = b["wkts_after"] - b["is_wicket"].astype(int)
    b["legal_before"] = b["legal_after"] - b["is_legal"].astype(int)
    b["wickets_in_hand"] = 10 - b["wkts_before"]

    # Ball limits and balls remaining
    inferred = inferred_reduced_limit(b, m, cfg)
    b = b.merge(ball_limits(m, cfg, inferred), on=KEY, how="left")
    b["limit_inferred"] = b["match_id"].isin(inferred.index)
    b["balls_rem_before"] = b["ball_limit"] - b["legal_before"]
    b["crr_before"] = np.where(b["legal_before"] > 0, 6 * b["score_before"] / b["legal_before"].clip(lower=1), np.nan)

    # Innings summary
    inn = (b.groupby(KEY).agg(batting_team_id=("batting_team_id", "first"),
                              bowling_team_id=("bowling_team_id", "first"),
                              total=("total_runs", "sum"), wkts=("is_wicket", "sum"),
                              legal=("is_legal", "sum"), deliveries=("innings_ball_num", "size"),
                              max_over=("overid", "max"), ball_limit=("ball_limit", "first"))
             .reset_index())
    inn["wkts"] = inn["wkts"].astype(int)
    inn["legal"] = inn["legal"].astype(int)

    # Targets: innings 2 chases innings 1 (revised_target if DLS); innings 4 chases innings 3
    first_tot = inn[inn.innings == 1].set_index("match_id")["total"]
    so_tot = inn[inn.innings == 3].set_index("match_id")["total"]
    rt = m.set_index("match_id")["revised_target"]
    tgt2 = rt.reindex(first_tot.index).fillna(first_tot + 1)
    tgt = pd.concat([
        pd.DataFrame({"match_id": tgt2.index, "innings": 2, "target": tgt2.values}),
        pd.DataFrame({"match_id": so_tot.index, "innings": 4, "target": (so_tot + 1).values}),
    ])
    tgt["target_source"] = np.where(
        (tgt.innings == 2) & tgt.match_id.isin(rt.dropna().index), "revised_target", "first_innings+1")
    inn = inn.merge(tgt, on=KEY, how="left")
    b = b.merge(tgt[KEY + ["target"]], on=KEY, how="left")

    b["is_chase"] = b["innings"].isin([2, 4])
    b["runs_needed_before"] = np.where(b["is_chase"], b["target"] - b["score_before"], np.nan)
    br = b["balls_rem_before"].where(b["balls_rem_before"] > 0)
    b["rrr_before"] = 6 * b["runs_needed_before"] / br
    b["rrr_minus_crr"] = b["rrr_before"] - b["crr_before"]
    b["runs_needed_per_wkt"] = b["runs_needed_before"] / b["wickets_in_hand"].where(b["wickets_in_hand"] > 0)

    # Wickets in the previous N legal balls (collapse indicator)
    w = cfg["collapse_window_legal_balls"]
    recent = np.zeros(len(b), dtype=int)
    for _, idx in b.groupby(KEY, sort=False).indices.items():
        lb = b["legal_before"].to_numpy()[idx]
        wb = b["wkts_before"].to_numpy()[idx]
        start = np.searchsorted(lb, lb - w, side="left")      # first row at legal count lb-w
        recent[idx] = wb - wb[start]
    b[f"wkts_last{w}"] = recent

    # Partnership so far (resets on every wicket)
    pg = b.groupby(KEY + ["wkts_before"], sort=False)
    b["partnership_runs_before"] = pg["total_runs"].cumsum() - b["total_runs"]
    b["partnership_legal_before"] = pg["is_legal"].cumsum() - b["is_legal"].astype(int)

    # Outcome from the batting side's perspective (NaN for no-result / tie)
    won = b["win_team_id"].astype("float")
    tie = b["is_tie_or_super_over"] & (b["innings"] <= 2)
    b["batting_side_won"] = np.where(won.isna() | tie, np.nan,
                                     (won == b["batting_team_id"]).astype(float))

    # Per-innings flags
    inn = inn.merge(m[["match_id", "is_dls", "is_no_result", "win_team_id", "margin_n",
                       "margin_type", "is_tie_or_super_over", "tier"]], on="match_id", how="left")
    inn["ended_early"] = (inn["legal"] < inn["ball_limit"]) & (inn["wkts"] < 10)
    inn["chase_reached"] = np.where(inn["target"].notna(), inn["total"] >= inn["target"], np.nan)
    inn1_trunc = inn[(inn.innings == 1) & inn.ended_early].match_id
    b["inn1_truncated_match"] = b["match_id"].isin(inn1_trunc)

    # Chase target reliability: DLS result with no revised_target, or a target that contradicts
    # the recorded winner (e.g. a superseded revised target), means the chase equation is unknown.
    dls_text = m.set_index("match_id")["result"].str.contains(r"d/l|dls", case=False, regex=True)
    i2 = inn[inn.innings == 2].set_index("match_id")
    decided = i2.win_team_id.notna() & ~i2.is_tie_or_super_over
    contradiction = decided & (i2.chase_reached.astype(bool) != (i2.win_team_id == i2.batting_team_id))
    missing_rt = dls_text.reindex(i2.index).fillna(False) & m.set_index("match_id")["revised_target"].reindex(i2.index).isna()
    # Play continued after the recorded target was passed (e.g. 48610) → the target was superseded
    played_on = b[(b.innings == 2) & (b.runs_needed_before <= 0)].match_id.unique()
    bad = i2.index[contradiction | missing_rt | i2.index.isin(played_on)]
    inn["target_reliable"] = ~(inn.match_id.isin(bad) & (inn.innings == 2))
    inn["limit_inferred"] = inn.match_id.isin(inferred.index)
    b["target_reliable"] = ~(b["match_id"].isin(bad) & (b["innings"] == 2))
    # Usable for win-probability modelling: decided, regular innings, reliable target
    b["wp_usable"] = (b["innings"] <= 2) & b["batting_side_won"].notna() & b["target_reliable"]
    return b, inn


# --------------------------------------------------------------------------- validation
def validate(b: pd.DataFrame, inn: pd.DataFrame, m: pd.DataFrame) -> list[str]:
    L = ["# State reconstruction checks — T3", "", "Generated by `src/state.py`.", ""]

    def chk(name, ok, detail=""):
        L.append(f"- [{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
        return ok

    reg = inn[inn.innings <= 2]
    chk("Rows preserved", len(b) == 200999, f"{len(b)} rows")
    chk("No negative runs", (b.total_runs >= 0).all())
    chk("Wickets never exceed 10", (b.wkts_after <= 10).all(), f"max {b.wkts_after.max()}")
    over_legal = b.groupby(KEY + ["overid"]).is_legal.sum()
    seven = over_legal[over_legal > 6]
    chk("Overs with > 6 legal balls are isolated scoring anomalies (≤ 2)", len(seven) <= 2,
        f"{len(seven)} over(s): {list(seven.index)}; distribution {over_legal.value_counts().sort_index().to_dict()}")
    exceed = reg[reg.legal > reg.ball_limit]
    chk("Legal balls never exceed the innings limit", exceed.empty,
        f"{len(exceed)} innings exceed: {exceed[['match_id','innings','legal','ball_limit']].values.tolist()[:10]}")

    # Margin reconciliation (non-DLS, decided, no super over)
    wide = reg.pivot_table(index="match_id", columns="innings", values=["total", "wkts"], aggfunc="first")
    wide.columns = [f"{a}{c}" for a, c in wide.columns]
    mm = m.set_index("match_id")[["margin_n", "margin_type", "is_dls", "is_tie_or_super_over",
                                  "win_team_id"]].join(wide, how="inner")
    base = mm[~mm.is_dls & ~mm.is_tie_or_super_over & mm.win_team_id.notna() & mm.total2.notna()]
    r = base[base.margin_type == "runs"]
    r_ok = (r.total1 - r.total2) == r.margin_n
    chk("Runs margins reproduced (non-DLS)", r_ok.mean() >= 0.99,
        f"{r_ok.mean():.1%} of {len(r)}; mismatches: {r[~r_ok].index.tolist()}")
    wk = base[base.margin_type == "wickets"]
    w_ok = (10 - wk.wkts2) == wk.margin_n
    chk("Wicket margins reproduced (non-DLS)", w_ok.mean() >= 0.99,
        f"{w_ok.mean():.1%} of {len(wk)}; mismatches: {wk[~w_ok].index.tolist()}")

    # Chase consistency with winner (all decided matches incl. DLS)
    i2 = reg[(reg.innings == 2) & reg.win_team_id.notna() & ~reg.is_tie_or_super_over & reg.target_reliable]
    exp = (i2.win_team_id == i2.batting_team_id)
    cons = (i2.chase_reached.astype(bool) == exp)
    chk("Chasing side reached target iff it won (reliable targets)", cons.all(),
        f"{cons.mean():.1%} of {len(i2)}")
    unrel = reg[(reg.innings == 2) & ~reg.target_reliable].match_id.tolist()
    chk("Unreliable chase targets flagged (excluded from WP modelling)", len(unrel) <= 10,
        f"{len(unrel)} matches: {unrel}")
    inf = reg[(reg.innings == 1) & reg.limit_inferred][["match_id", "ball_limit"]].values.tolist()
    chk("Reduced-overs limits inferred where revised fields are blank", True, f"{inf}")
    lb_all = b[(b.innings <= 2) & b.is_legal]
    chk("Chase balls bowled after target reached (reliable targets)",
        int((lb_all.is_chase & lb_all.target_reliable & (lb_all.runs_needed_before <= 0)).sum()) == 0)
    L.append(f"- WP-usable legal balls: {int((lb_all.wp_usable).sum())} of {len(lb_all)}")

    ee = reg[reg.ended_early]
    L += ["", "## Innings ending before limit with < 10 wickets", "",
          f"- Innings 1: {int((ee.innings==1).sum())} (no-result: {int((ee.innings==1 & ee.is_no_result).sum())}, "
          f"DLS: {int(((ee.innings==1) & ee.is_dls).sum())}); other match ids: "
          f"{ee[(ee.innings==1) & ~ee.is_no_result & ~ee.is_dls].match_id.tolist()}",
          f"- Innings 2: {int((ee.innings==2).sum())}, of which chase reached target: "
          f"{int(((ee.innings==2) & (ee.chase_reached==1)).sum())}, no-result: {int(((ee.innings==2) & ee.is_no_result).sum())}",
          ""]
    L += ["## State column coverage (innings 1–2, legal balls)", ""]
    lb = b[(b.innings <= 2) & b.is_legal]
    for col in ["balls_rem_before", "rrr_before", "runs_needed_before", "crr_before", "wkts_last18",
                "batting_side_won"]:
        L.append(f"- {col}: non-null {lb[col].notna().mean():.1%}; "
                 f"min {np.nanmin(lb[col]):.2f}, median {np.nanmedian(lb[col]):.2f}, max {np.nanmax(lb[col]):.2f}")
    L.append(f"- Balls with balls_rem_before ≤ 0 (bowled beyond limit): {int((lb.balls_rem_before <= 0).sum())}")
    L.append(f"- Chase balls with runs_needed_before ≤ 0 (target already reached): "
             f"{int((lb.is_chase & (lb.runs_needed_before <= 0)).sum())}")
    return L


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    interim = path(cfg, "interim")
    b = pd.read_parquet(interim / "balls.parquet")
    m = pd.read_parquet(interim / "matches.parquet")
    bs, inn = build_state(b, m, cfg)
    bs.to_parquet(interim / "ball_state.parquet", index=False)
    inn.to_parquet(interim / "innings.parquet", index=False)
    vdir = path(cfg, "outputs") / "validation"
    vdir.mkdir(exist_ok=True)
    lines = validate(bs, inn, m)
    (vdir / "state_checks.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return bs, inn, lines


if __name__ == "__main__":
    run()
