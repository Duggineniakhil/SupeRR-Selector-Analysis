import sys, pandas as pd, numpy as np
D = sys.argv[1]
c = pd.read_csv(f"{D}/competitions.csv"); m = pd.read_csv(f"{D}/matches.csv").merge(c,on='comp_id')
mp = pd.read_csv(f"{D}/competition_team_player_mapping.csv"); b = pd.read_csv(f"{D}/ball_by_ball.csv", low_memory=False)
b=b.merge(m[['match_id','comp_name','match_format','season','stage','knock_out']],on='match_id'); b['ipl']=b.comp_name.str.startswith('IPL')
print("deliveries IPL vs other:", b.ipl.value_counts().to_dict())
nat_teams={'Afghanistan','Australia','Bangladesh','Canada','England','Hong Kong','India','Ireland','Japan','Kuwait','Nepal','Netherlands','New Zealand','Oman','Pakistan','Scotland','Singapore','South Africa','Sri Lanka','United Arab Emirates','United States Of America','West Indies','Zimbabwe'}
a_teams={'Afghanistan A','Bangladesh A','India A','Pakistan A','Sri Lanka A'}
ipl_players=set(mp[mp.comp_name.str.startswith('IPL')].player_id)
nat=mp[mp.team_name.isin(nat_teams|a_teams)].groupby('player_id').team_name.agg(lambda s: sorted(set(s)))
print("IPL players:",len(ipl_players)," with any national/A-team appearance:", len(ipl_players & set(nat.index)))
print("IPL players w/ India or India A:", sum(1 for p in ipl_players if p in nat.index and any(t.startswith('India') for t in nat[p])))
print("IPL players with >1 country:", sum(1 for p in ipl_players if p in nat.index and len({t.replace(' A','') for t in nat[p]})>1))
# second innings chase context prevalence (structure only)
s=b[(b.innings==2)&(b.match_format.notna())].copy()
s['legal']=~s.extras_type.isin(['wide','Overstep','other']); s['tot']=s.runs+s.extras1_runs+s.extras_2_runs
print("2nd-innings deliveries:",len(s))
print("Ball-tracking style fields non-null share (IPL vs other):"); 
for col in ['stroke','delivery_style','over_or_around']: print(col, b.groupby('ipl')[col].apply(lambda x: x.notna().mean().round(3)).to_dict())
print("IPL players per season in mapping:", mp[mp.comp_name.str.startswith('IPL')].groupby('comp_name').player_id.nunique().to_dict())
print("IPL 2026 matches in bbb:", b[b.comp_name=='IPL 2026'].match_id.nunique(), " date range:", m[m.comp_name=='IPL 2026'].match_date.min(), m[m.comp_name=='IPL 2026'].match_date.max())
print("Abandoned/NR matches with bbb:", b[b.match_id.isin(m[m.result.str.contains('No Result|Abandon',case=False)].match_id)].match_id.nunique())
print("impact player rows in bbb-matched IPL 2023+ only?:", pd.read_csv(f"{D}/playing_eleven.csv").merge(m[['match_id','comp_name']]).query('is_impact==1').comp_name.value_counts().to_dict())
