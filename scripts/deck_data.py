"""Collect every number the Round 1 slide deck shows into one JSON (local only: report/deck/).

Run: python -I scripts/deck_data.py
Rankings apply decision D7 (Pakistan nationals excluded from the submitted lists, ranks renumbered),
exactly as src/report_build.top10_table does.
"""
import json
import pickle
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from common import load_config, path  # noqa: E402

TIERS = ["Low", "Moderate", "High", "Extreme"]


def main():
    cfg = load_config()
    interim, outs = path(cfg, "interim"), path(cfg, "outputs")
    out = ROOT / "report" / "deck"
    out.mkdir(parents=True, exist_ok=True)
    D = {}

    d = pd.read_parquet(interim / "rating_balls.parquet")
    x = d[d.is_legal & d.batting_side_won.notna()].copy()
    x["abs_wpa"] = x.wpa_bat.abs()
    balls = x.pressure_tier.value_counts(normalize=True).reindex(TIERS) * 100
    wpa = x.groupby("pressure_tier").abs_wpa.sum().reindex(TIERS) / x.abs_wpa.sum() * 100
    D["concentration"] = {"tiers": TIERS, "balls": balls.round(1).tolist(), "wpa": wpa.round(1).tolist()}
    sh = (x.groupby(["innings", "phase"]).is_pressure.mean() * 100).unstack(0).reindex(["PP", "MID", "DEATH"])
    D["phase"] = {"phases": ["Powerplay (1-6)", "Middle (7-15)", "Death (16-20)"],
                  "inn1": sh[1].round(1).tolist(), "inn2": sh[2].round(1).tolist()}
    death = x[x.phase == "DEATH"]
    D["death_low_pct"] = round(float((death.pressure_tier == "Low").mean() * 100), 1)
    D["n_balls"] = int(len(d))
    D["n_matches"] = int(d.match_id.nunique())

    with open(interim / "reliability.pkl", "rb") as fh:
        rel = pickle.load(fh)
    D["reliability"] = {k: rel[k]["split_half"].set_index("metric").full_sample_reliability.round(2).to_dict()
                        for k in ("bat", "bowl")}

    for k in ("bat", "bowl"):
        t = pd.read_csv(outs / "validation" / f"out_of_time_{k}.csv")
        D[f"oot_{k}"] = [{"name": r["predictor (2022–24)"], "r": round(r["r_w vs pressure value"], 2),
                          "ci": r["r 90% CI"]} for _, r in t.iterrows()]

    players = pd.read_parquet(interim / "players.parquet").set_index("player_id")
    nat = players.pack_country.astype(object).where(players.pack_country.notna(), "")
    for kind in ("batting", "bowling"):
        rk = pd.read_csv(outs / "rankings" / f"{kind}_ratings.csv", index_col=0)
        rob = pd.read_csv(outs / "rankings" / f"{kind}_robustness.csv", index_col=0)
        tb = pd.read_parquet(interim / f"player_{'bat' if kind == 'batting' else 'bowl'}.parquet")
        D[f"pool_{kind}"] = int(len(rk))
        rk = rk[nat.reindex(rk.index).fillna("").ne("Pakistan").to_numpy()].copy()   # D7
        rk["rank"] = range(1, len(rk) + 1)
        t = rk.head(12).copy()
        raw = (tb.sr_P if kind == "batting" else tb.econ_P).reindex(t.index)
        rows = []
        for pid, r in t.iterrows():
            rows.append({"rank": int(r["rank"]), "name": r.display_name, "role": r.role_group.replace("_", " "),
                         "rating": round(r.rating, 3), "baseline": round(r.baseline_ability_B, 3),
                         "all_balls": round(r.all_balls_value_EB, 3),
                         "pressure_value": round(r.actual_pressure_value_raw, 3),
                         "advantage": round(r.pressure_advantage_raw, 3),
                         "pressure_balls": int(r.pressure_balls), "p_top10": round(r.p_top10, 2),
                         "p05": float(r.rank_p05), "p95": float(r.rank_p95),
                         "pct_ipl": round(r.pct_P_balls_ipl, 0),
                         "raw_rate": round(float(raw.get(pid)), 1),
                         "robust_share": round(float(rob.share_scenarios_top10.get(pid, float("nan"))) * 100, 0),
                         "robustness": rob.robustness.get(pid, "")})
        D[kind] = rows
    (out / "deck_data.json").write_text(json.dumps(D, indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote", out / "deck_data.json")


if __name__ == "__main__":
    main()
