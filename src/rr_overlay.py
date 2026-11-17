"""T17 — Rajasthan Royals auction overlay with scenario framing (planning/06; decision D1).

Does NOT change the official rankings. It answers: given the pressure-reliability ratings,
which RR roles are thin, and whom should RR target (with fallbacks) under different
availability scenarios?

1. RR squad profile: the latest confirmed RR squad in the pack (IPL 2026). 2027 retentions were
   unpublished on the as-of date, so every squad player carries the label
   [ASSUMPTION: retained]. Each player is rated with the final estimator (M2, all-balls EB value)
   in each role where they have enough evidence.
2. Need matrix (rules pre-registered in config.yaml `rr_overlay`): per role, count squad players
   who count in the role AND whose rating is ≥ the eligible-pool median → GAP / THIN / COVERED.
3. Availability status per candidate:
     RR_CORE      already in RR's squad → "back / retain", not an auction target
     UNAVAILABLE  retired from IPL, or de facto excluded (Pakistan players)
     DOUBTFUL     availability in question (e.g. Bangladesh players after the Jan 2026 BCCI directive)
     AUCTION_LIKELY  no IPL team in 2026 → would enter the pool if registered
     CONDITIONAL  under contract elsewhere; available only if released
   Top-12 statuses come from the verification log (researched, sourced); ranks 13–30 use
   pack-based rules and are marked "rule-based, not individually researched".
4. Scenario chains per role: primary target → fallback 1 → fallback 2 (in ranking order), so the
   recommendation survives whatever the retention lists show.

Output: outputs/rankings/rr_overlay.md (local only — names), and a name-free summary
        appended to outputs/validation/rr_overlay_summary.md
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

import estimators as E
from common import load_config, md_table, path

STATUS_TEXT = {
    "RR_CORE": "Already at RR: back / retain (benchmark, not an auction target)",
    "UNAVAILABLE": "Not available",
    "DOUBTFUL": "Doubtful availability",
    "AUCTION_LIKELY": "No IPL team in 2026: in auction pool if registered",
    "CONDITIONAL": "Under contract elsewhere: target only if released",
}


def classify_verified(s: str) -> str:
    s = str(s)
    if s.startswith("Already at RR"):
        return "RR_CORE"
    if "NOT AVAILABLE" in s:
        return "UNAVAILABLE"
    if s.startswith("DOUBTFUL"):
        return "DOUBTFUL"
    if s.startswith("Not with an IPL team"):
        return "AUCTION_LIKELY"
    return "CONDITIONAL"


def run(cfg: dict | None = None):
    cfg = cfg or load_config()
    rc = cfg["rr_overlay"]
    interim, out, root = path(cfg, "interim"), path(cfg, "outputs"), path(cfg, "outputs").parent
    d = pd.read_parquet(interim / "rating_balls.parquet")
    players = pd.read_parquet(interim / "players.parquet").set_index("player_id")
    players["pack_country"] = players.pack_country.astype(object).where(players.pack_country.notna(), None)
    mp = pd.read_csv(root / cfg["paths"]["raw"] / "competition_team_player_mapping.csv")
    ipl26 = mp[mp.comp_name == rc["squad_comp"]]
    team26 = ipl26.groupby("player_id").team_name.first()
    squad = ipl26[ipl26.team_id == rc["team_id"]].player_id.unique()
    # ---- official IPL 2027 retention lists (if recorded) override the 2026 squad + reported statuses
    off_p = root / "research" / "official_2027.json"
    official = json.loads(off_p.read_text(encoding="utf-8")) if off_p.exists() else None
    off_status, unmatched = {}, []
    if official:
        def norm(t):
            return re.sub(r"[^a-z]", "", str(t).lower())
        alias = {"tilakvarma": "nambooritilakvarma", "msdhoni": "mahendrasinghdhoni",
                 "klrahul": "lokeshrahul", "patcummins": "patrickcummins", "nitishkumarreddy": "nitishreddy",
                 "willjacks": "williamjacks", "vvyshak": "vyshakkumar", "rajangadbawa": "rajbawa",
                 "msiddharth": "manimaransiddharth", "rsaikishore": "saikishore", "rsmaran": "ravichandransmaran",
                 "rasikhdar": "rasikhsalam", "mattshort": "matthewshort", "zakfoulkes": "zakaryfoulkes",
                 "amghazanfar": "allahghazanfar", "nishantsindhu": "nishantkumarsindhu",
                 "shahrukhkhan": "mshahrukhkhan", "tejasvisinghdahiya": "tejasvidahiya",
                 "onkartarmale": "omkartarmale", "prithvirajyarra": "yarraprithviraj", "mohammedizhar": "mohdizhar"}
        cand_ids: dict = {}
        for pid, r in players.iterrows():
            for nm in {r.player_name, re.sub(r" [(].*[)]$", "", str(r.display_name))}:
                cand_ids.setdefault(norm(nm), []).append(pid)

        def resolve(nm):
            ids = list(dict.fromkeys(cand_ids.get(alias.get(norm(nm), norm(nm)), [])))
            if len(ids) > 1:   # shared name: prefer the player with IPL seasons in the pack
                ids = [i for i in ids if str(players.ipl_seasons.get(i, "") or "")] or ids
            return ids[0] if ids else None
        for team, t in official["teams"].items():
            for key, code in (("retained", "RETAINED"), ("released", "RELEASED")):
                for nm in t.get(key, []):
                    pid = resolve(nm)
                    if pid is None:
                        unmatched.append(f"{nm} ({team}, {key})")
                    else:
                        off_status[pid] = (code, team)
        squad = np.array([pid for pid, (code, tm) in off_status.items()
                          if code == "RETAINED" and tm == "Rajasthan Royals"])
    ver_path = root / "research" / "verification_log.csv"
    ver = pd.read_csv(ver_path).set_index("player_id") if ver_path.exists() else pd.DataFrame()
    ref, seed = pd.Timestamp(cfg["reference_date"]), cfg["pressure"]["seed"]

    L = [f"# RR auction overlay — scenario framing (as of {rc['as_of']})", "",
         "Generated by `src/rr_overlay.py`. **Local only (contains names).** The official rankings are "
         "not changed by anything here (decision D1).", "",
         (f"**Squad basis: OFFICIAL IPL 2027 retention lists** ({official['accessed']}; {official['source']}). "
          f"RR 2027 squad = {len(squad)} retained players matched in the pack "
          f"(purse Rs {official['teams']['Rajasthan Royals']['purse_cr']} crore, "
          f"{official['teams']['Rajasthan Royals']['slots']} slots, "
          f"{official['teams']['Rajasthan Royals']['overseas_slots']} overseas). "
          f"Unmatched names (no data in pack): {', '.join(unmatched) or 'none'}."
          if official else
          f"**Squad basis:** RR's {rc['squad_comp']} squad from the data pack ({len(squad)} players). "
          "IPL 2027 retention lists were not published on the as-of date, so every squad player is "
          "labelled **[ASSUMPTION: retained]**. "
          + ((root / "research" / "rr_squad_notes.md").read_text(encoding="utf-8").strip()
             if (root / "research" / "rr_squad_notes.md").exists() else "")), ""]
    summary = ["# RR overlay — name-free summary", "", f"As of {rc['as_of']}; rules in `config.yaml` `rr_overlay`.", ""]
    need_rows, chains_md = [], []

    for kind, roles in (("bat", rc["bat_roles"]), ("bowl", rc["bowl_roles"])):
        name = "batting" if kind == "bat" else "bowling"
        bv = E.ball_values(d, kind)
        fit = E.train(bv, kind, cfg, ref, seed)
        rating, st = fit["feat"].post_A, fit["stats"]
        tbl = pd.read_parquet(interim / f"player_{kind}.parquet")
        ranks = pd.read_csv(out / "rankings" / f"{name}_ratings.csv", index_col=0)
        rob_p = out / "rankings" / f"{name}_robustness.csv"
        rob = pd.read_csv(rob_p, index_col=0) if rob_p.exists() else pd.DataFrame()
        pool_median = float(rating.reindex(ranks.index).median())
        league = rating[st.neff_A >= rc["min_role_eff_n"]]

        # ---- squad profile
        sq = pd.DataFrame(index=pd.Index(squad, name="player_id"))
        sq["name"] = players.display_name.reindex(sq.index)
        sq["role"] = tbl.role_group.reindex(sq.index)
        sq["eff_n"] = st.neff_A.reindex(sq.index)
        sq["rating"] = rating.reindex(sq.index)
        sq["league_pctile"] = sq.rating.apply(lambda r: (league < r).mean() * 100 if pd.notna(r) else np.nan)
        sq["pressure_balls"] = st.n_P.reindex(sq.index)
        sq["pressure_value_raw"] = st.x_P.reindex(sq.index)
        sq["official_rank"] = ranks["rank"].reindex(sq.index)
        sq["counts_in_role"] = sq.eff_n >= rc["min_role_eff_n"]
        sq["above_pool_median"] = sq.rating >= pool_median
        sq["status"] = "[OFFICIAL: retained]" if official else "[ASSUMPTION: retained]"
        sqv = sq[sq.eff_n.notna() & (sq.eff_n > 0)].sort_values("rating", ascending=False)

        L += [f"## {name.capitalize()}: RR squad profile (M2 rating; league percentile among players with "
              f"n_eff ≥ {rc['min_role_eff_n']})", "",
              md_table(sqv[["name", "role", "eff_n", "rating", "league_pctile", "pressure_balls",
                            "pressure_value_raw", "official_rank", "counts_in_role", "above_pool_median", "status"]],
                       floatfmt="{:.2f}"), ""]

        # ---- need matrix
        for role in roles:
            cnt = int((sq.role.eq(role) & sq.counts_in_role & sq.above_pool_median).sum())
            sev = "GAP" if cnt == 0 else ("THIN" if cnt == 1 else "COVERED")
            need_rows.append({"discipline": name, "role": role, "qualifying_rr_players": cnt, "severity": sev,
                              "rr_players_in_role": int((sq.role.eq(role) & sq.counts_in_role).sum())})

        # ---- candidate statuses
        cand = ranks.head(rc["candidates_per_list_official"] if official else rc["candidates_per_list"]).copy()
        cand["status_code"] = [
            classify_verified(ver.loc[i, "V8_ipl2027_status"]) if (len(ver) and i in ver.index)
            else ("RR_CORE" if i in squad else
                  "UNAVAILABLE" if players.pack_country.get(i) == "Pakistan" else
                  "DOUBTFUL" if players.pack_country.get(i) == "Bangladesh" else
                  "CONDITIONAL" if i in team26.index else "AUCTION_LIKELY")
            for i in cand.index]
        # Reported (not official) retention predictions refine CONDITIONAL into tiers
        rep_p = root / "research" / "reported_retentions.csv"
        rep = pd.read_csv(rep_p).set_index("player_name").report if rep_p.exists() else pd.Series(dtype=str)
        cand["reported"] = cand.display_name.map(rep).fillna("no_report")
        cand.loc[cand.status_code != "CONDITIONAL", "reported"] = "—"
        cand["status_source"] = ["researched (verification log)" if (len(ver) and i in ver.index)
                                 else "rule-based, not individually researched" for i in cand.index]
        if official:
            def off_code(i):
                code, tm = off_status.get(i, (None, None))
                vs = str(ver.loc[i, "V8_ipl2027_status"]) if (len(ver) and i in ver.index) else ""
                if i in squad:
                    return "RR_CORE"
                if "NOT AVAILABLE" in vs or players.pack_country.get(i) == "Pakistan":
                    return "UNAVAILABLE"
                if code == "RETAINED":
                    return "RETAINED"
                if players.pack_country.get(i) == "Bangladesh" or "DOUBTFUL" in vs:
                    return "DOUBTFUL"        # Bangladesh players after the Jan 2026 BCCI directive; Dhoni
                if code == "RELEASED":
                    return "AUCTION_POOL"
                return "AUCTION_IF_REGISTERED" if i not in team26.index else "UNVERIFIED"
            cand["status_code"] = [off_code(i) for i in cand.index]
            cand["official_team"] = [off_status.get(i, (None, "—"))[1] for i in cand.index]
            cand["reported"] = "—"
            cand["status_source"] = "official retention lists (17 Nov 2026)"
        cand["ipl_2026_team"] = team26.reindex(cand.index).fillna("—")
        cand["nationality"] = [ver.loc[i, "nationality"] if (len(ver) and i in ver.index)
                               else (players.pack_country.get(i) if pd.notna(players.pack_country.get(i))
                                     else "unverified") for i in cand.index]
        cand["overseas"] = cand.nationality.ne("India") & cand.nationality.ne("unverified")
        cand["age"] = [ver.loc[i, "age_on_2026-11-17"] if (len(ver) and i in ver.index) else np.nan for i in cand.index]
        cand["robustness"] = rob.robustness.reindex(cand.index).fillna("—") if len(rob) else "—"

        L += [f"## {name.capitalize()}: official top {len(cand)} with availability status", "",
              md_table(cand[[c for c in ["display_name", "role_group", "rank", "p_top10", "robustness",
                                         "actual_pressure_value_raw", "pressure_balls", "nationality", "overseas",
                                         "age", "ipl_2026_team", "official_team", "status_code", "reported",
                                         "status_source"] if c in cand.columns]], floatfmt="{:.2f}"), ""]
        rr_in = cand[cand.status_code == "RR_CORE"]
        L += [f"- RR players already in the official top {rc['candidates_per_list']}: "
              f"{', '.join(f'{n} (#{int(r)})' for n, r in zip(rr_in.display_name, rr_in['rank'])) or 'none'} "
              "→ **back / retain**.", ""]

        # ---- scenario chains per role, ordered by need severity
        sev_order = {"GAP": 0, "THIN": 1, "COVERED": 2}
        for role in sorted(roles, key=lambda r: sev_order[[n for n in need_rows if n["discipline"] == name
                                                            and n["role"] == r][0]["severity"]]):
            sev = [n for n in need_rows if n["discipline"] == name and n["role"] == role][0]["severity"]
            in_role = cand[cand.role_group == role]
            if official:
                avail = pd.concat([in_role[in_role.status_code.isin(["AUCTION_POOL", "AUCTION_IF_REGISTERED"])],
                                   in_role[in_role.status_code == "DOUBTFUL"]])
                kept = in_role[in_role.status_code == "RETAINED"]
                chain = avail.head(rc["scenario_depth"])
                lines = [f"### {name.capitalize()} · {role} — need: **{sev}**", ""]
                if not kept.empty:
                    k0 = kept.iloc[0]
                    lines.append(f"- *Best in role, retained (not available):* {k0.display_name} "
                                 f"(official #{int(k0['rank'])}, {k0.official_team}).")
                if chain.empty:
                    lines.append(f"- No available player of this role in the top {len(cand)}.")
                for k, (pid, c) in enumerate(chain.iterrows()):
                    tag = "Primary target" if k == 0 else f"Fallback {k}"
                    cond = {"AUCTION_POOL": f"released by {c.official_team} [OFFICIAL]",
                            "AUCTION_IF_REGISTERED": "no IPL team in 2026; available if registered",
                            "DOUBTFUL": (f"released by {c.official_team} [OFFICIAL]; " if c.official_team != "—" else "no IPL team; ")
                            + "availability doubtful"}[c.status_code]
                    nat = ("overseas" if c.overseas else "Indian" if c.nationality == "India"
                           else "nationality unverified")
                    age = f", age {c.age:.0f}" if pd.notna(c.age) else ""
                    lines.append(f"- **{tag}: {c.display_name}** (official #{int(c['rank'])}, "
                                 f"P(top-10) {c.p_top10:.2f}, {c.robustness}; {nat}{age}) — {cond}.")
                chains_md += lines + [""]
                continue
            # Realistic: not reported as likely retained (auction-likely, possible release, no report);
            # doubtful-eligibility players go last. Stretch: reported likely retained (only if released).
            realistic = in_role[(in_role.status_code.isin(["AUCTION_LIKELY"]))
                                | ((in_role.status_code == "CONDITIONAL")
                                   & ~in_role.reported.isin(["likely_retained", "unlikely_to_play"]))]
            realistic = pd.concat([realistic, in_role[in_role.status_code == "DOUBTFUL"]])
            stretch = in_role[(in_role.status_code == "CONDITIONAL") & in_role.reported.eq("likely_retained")]
            chain = realistic.head(rc["scenario_depth"])
            lines = [f"### {name.capitalize()} · {role} — need: **{sev}**", ""]
            if not stretch.empty:
                s0 = stretch.iloc[0]
                lines.append(f"- *Stretch (only if released; reported likely retained [REPORTED]):* "
                             f"{s0.display_name} (official #{int(s0['rank'])}, P(top-10) {s0.p_top10:.2f}).")
            if chain.empty:
                lines += ["- No available candidate of this role in the official top "
                          f"{rc['candidates_per_list']}; look deeper in the eligible pool.", ""]
            for k, (pid, c) in enumerate(chain.iterrows()):
                tag = "Realistic target" if k == 0 else f"Fallback {k}"
                cond = {"CONDITIONAL": f"if released by {c.ipl_2026_team}"
                        + (" (reported possible release [REPORTED])" if c.reported == "possible_release" else "")
                        + (" (rumoured trade link with RR [REPORTED])" if c.reported == "rr_trade_rumour" else ""),
                        "AUCTION_LIKELY": "if registered for the auction",
                        "DOUBTFUL": "only if eligibility is confirmed"}[c.status_code]
                lines.append(f"- **{tag}: {c.display_name}** (official #{int(c['rank'])}, P(top-10) {c.p_top10:.2f}, "
                             f"{c.robustness}; {'overseas' if c.overseas else 'Indian' if c.nationality == 'India' else 'nationality unverified'}"
                             f"{f', age {c.age:.0f}' if pd.notna(c.age) else ''}) — {cond}.")
            if len(chain) > 1:
                lines.append(f"- Scenario: if {chain.iloc[0].display_name} is retained, move to "
                             f"{chain.iloc[1].display_name}"
                             + (f"; if both are unavailable, {chain.iloc[2].display_name}." if len(chain) > 2 else "."))
            chains_md += lines + [""]
    need = pd.DataFrame(need_rows)
    L += ["## Need matrix (pre-registered rule)", "", md_table(need, index=False), "",
          "## Scenario chains by role (most severe need first)", "", *chains_md,
          "## Caveats", "",
          "- Cost / price tier is not assessed: no verified auction prices in this analysis.",
          "- Ranks 13–30 statuses are rule-based (IPL 2026 team in the pack; nationality), not individually researched.",
          "- 'Reported likely retained / possible release' come from media predictions dated before the 17 Nov 2026 "
          "deadline (`research/reported_retentions.csv`); 'no report' does not mean available.",
          "- Swap in the official retention lists when published: only the `status_code` column changes; the chains "
          "re-order automatically."]
    (out / "rankings" / "rr_overlay.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    summary += ["## Need matrix", "", md_table(need, index=False), ""]
    (out / "validation" / "rr_overlay_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    return need, L


if __name__ == "__main__":
    run()
