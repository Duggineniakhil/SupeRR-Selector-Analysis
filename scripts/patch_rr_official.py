"""One-off patch: add official-list mode to src/rr_overlay.py (T17 refresh, 17 Nov 2026)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / "src" / "rr_overlay.py"
s = p.read_text(encoding="utf-8")


def rep(a: str, b: str) -> None:
    global s
    assert a in s, a[:80]
    s = s.replace(a, b, 1)


rep('''    squad = ipl26[ipl26.team_id == rc["team_id"]].player_id.unique()''',
    '''    squad = ipl26[ipl26.team_id == rc["team_id"]].player_id.unique()
    # ---- official IPL 2027 retention lists (if recorded) override the 2026 squad + reported statuses
    off_p = root / "research" / "official_2027.json"
    official = json.loads(off_p.read_text(encoding="utf-8")) if off_p.exists() else None
    off_status, unmatched = {}, []
    if official:
        def norm(t):
            return re.sub(r"[^a-z]", "", str(t).lower())
        alias = {"tilakvarma": "nambooritilakvarma", "msdhoni": "mahendrasinghdhoni"}
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
                          if code == "RETAINED" and tm == "Rajasthan Royals"])''')

rep('''         f"**Squad basis:** RR's {rc['squad_comp']} squad from the data pack ({len(squad)} players). "
         "IPL 2027 retention lists were not published on the as-of date, so every squad player is "
         "labelled **[ASSUMPTION: retained]**. "
         + ((root / "research" / "rr_squad_notes.md").read_text(encoding="utf-8").strip()
            if (root / "research" / "rr_squad_notes.md").exists() else ""), ""]''',
    '''         (f"**Squad basis: OFFICIAL IPL 2027 retention lists** ({official['accessed']}; {official['source']}). "
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
             if (root / "research" / "rr_squad_notes.md").exists() else "")), ""]''')

rep('''        sq["status"] = "[ASSUMPTION: retained]"''',
    '''        sq["status"] = "[OFFICIAL: retained]" if official else "[ASSUMPTION: retained]"''')

rep('''        cand = ranks.head(rc["candidates_per_list"]).copy()''',
    '''        cand = ranks.head(rc["candidates_per_list_official"] if official else rc["candidates_per_list"]).copy()''')

rep('''        cand["status_source"] = ["researched (verification log)" if (len(ver) and i in ver.index)
                                 else "rule-based, not individually researched" for i in cand.index]''',
    '''        cand["status_source"] = ["researched (verification log)" if (len(ver) and i in ver.index)
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
                if code == "RELEASED":
                    if players.pack_country.get(i) == "Bangladesh" or "DOUBTFUL" in vs:
                        return "DOUBTFUL"
                    return "AUCTION_POOL"
                return "AUCTION_IF_REGISTERED" if i not in team26.index else "UNVERIFIED"
            cand["status_code"] = [off_code(i) for i in cand.index]
            cand["official_team"] = [off_status.get(i, (None, "—"))[1] for i in cand.index]
            cand["reported"] = "—"
            cand["status_source"] = "official retention lists (17 Nov 2026)"''')

rep('''            in_role = cand[cand.role_group == role]''',
    '''            in_role = cand[cand.role_group == role]
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
                            "DOUBTFUL": f"released by {c.official_team} [OFFICIAL], eligibility doubtful"}[c.status_code]
                    nat = ("overseas" if c.overseas else "Indian" if c.nationality == "India"
                           else "nationality unverified")
                    age = f", age {c.age:.0f}" if pd.notna(c.age) else ""
                    lines.append(f"- **{tag}: {c.display_name}** (official #{int(c['rank'])}, "
                                 f"P(top-10) {c.p_top10:.2f}, {c.robustness}; {nat}{age}) — {cond}.")
                chains_md += lines + [""]
                continue''')

rep('''              md_table(cand[["display_name", "role_group", "rank", "p_top10", "robustness", "actual_pressure_value_raw",
                             "pressure_balls", "nationality", "overseas", "age", "ipl_2026_team", "status_code",
                             "reported", "status_source"]], floatfmt="{:.2f}"), ""]''',
    '''              md_table(cand[[c for c in ["display_name", "role_group", "rank", "p_top10", "robustness",
                                         "actual_pressure_value_raw", "pressure_balls", "nationality", "overseas",
                                         "age", "ipl_2026_team", "official_team", "status_code", "reported",
                                         "status_source"] if c in cand.columns]], floatfmt="{:.2f}"), ""]''')

rep('''        L += [f"## {name.capitalize()}: official top {rc['candidates_per_list']} with availability status", "",''',
    '''        L += [f"## {name.capitalize()}: official top {len(cand)} with availability status", "",''')

if "import json" not in s:
    s = s.replace("import numpy as np", "import json\nimport re\n\nimport numpy as np", 1)
p.write_text(s, encoding="utf-8")

c = ROOT / "config.yaml"
cs = c.read_text(encoding="utf-8")
if "candidates_per_list_official" not in cs:
    cs = cs.replace("  candidates_per_list: 30            # ranked players considered as targets / alternatives",
                    "  candidates_per_list: 30            # ranked players considered as targets / alternatives\n"
                    "  candidates_per_list_official: 60   # deeper once official lists show most top players retained")
    c.write_text(cs, encoding="utf-8")
print("patched")
