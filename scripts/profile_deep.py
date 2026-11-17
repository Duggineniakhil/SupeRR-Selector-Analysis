import sys, pandas as pd, numpy as np
D = sys.argv[1]
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60); pd.set_option('display.max_rows', 300)
c = pd.read_csv(f"{D}/competitions.csv"); m = pd.read_csv(f"{D}/matches.csv"); t=pd.read_csv(f"{D}/teams.csv")
p = pd.read_csv(f"{D}/playing_eleven.csv"); mp = pd.read_csv(f"{D}/competition_team_player_mapping.csv")
b = pd.read_csv(f"{D}/ball_by_ball.csv", low_memory=False)
print("== competitions by format x season"); print(pd.crosstab(c.season, c.match_format))
print("non-standard seasons:", c[~c.season.astype(str).str.fullmatch(r'\d{4}')][['comp_name','season']].to_string())
print("T20 (non-T20I) comps:"); print(c[c.match_format=='T20'].to_string())
m = m.merge(c, on='comp_id', how='left')
m['match_date']=pd.to_datetime(m.match_date)
print("== matches by format/season"); print(pd.crosstab(m.match_date.dt.year, m.match_format))
print("date range", m.match_date.min(), m.match_date.max())
print("== stage"); print(m.stage.value_counts()); print("knock_out", m.knock_out.value_counts().to_dict())
print("== venue_country"); print(m.venue_country.value_counts().to_dict())
print("== results without winner:"); print(m[m.win_team_id.isna()].result.value_counts().head(15))
print("result samples:", m.result.str.extract(r'(Won by .*|Tie.*|No Result.*|Abandon.*|Super.*)')[0].str.replace(r'\d+','N',regex=True).value_counts().to_dict())
print("== revised (DLS) matches"); print(m[m.first_inn_revised_overs.notna()|m.revised_target.notna()][['match_id','first_inn_revised_overs','second_inn_revised_overs','revised_target','result']].head(10).to_string())
print("matches w/o bbb:", len(set(m.match_id)-set(b.match_id)), " bbb matches not in matches:", len(set(b.match_id)-set(m.match_id)))
print("comps in matches not in competitions:", set(m.comp_id)-set(c.comp_id), "comps with no matches:", c[~c.comp_id.isin(m.comp_id)].comp_name.tolist())
# bbb
print("== innings counts"); print(b.innings.value_counts())
print("over_ball_num dist"); print(b.over_ball_num.value_counts().sort_index().to_dict())
print("extras_type"); print(b.extras_type.value_counts(dropna=False).to_dict())
print("extras1 vs type"); print(pd.crosstab(b.extras_type.fillna('NaN'), b.extras1_runs))
print("extras2 vs type"); print(pd.crosstab(b.extras_type.fillna('NaN'), b.extras_2_runs))
print("runs vs is_four/six"); print(pd.crosstab(b.runs, [b.is_four,b.is_six]))
print("runs on wides?"); print(pd.crosstab(b.extras_type.fillna('NaN'), b.runs))
print("dismissal_type"); print(b.dismissal_type.value_counts(dropna=False).to_dict())
print("dismissal_type_id map"); print(b.groupby('dismissal_type').dismissal_type_id.unique().to_dict())
print("is_wicket vs dismissal null:"); print(pd.crosstab(b.is_wicket, b.dismissal_type.isna()))
print("dismissed != striker (non-runout):", ((b.dismissed_player_id.notna())&(b.dismissed_player_id!=b.striker_id)).sum(), (b.dismissed_player_id.notna()&(b.dismissed_player_id==b.non_striker_id)).sum())
print("bowling_type"); print(b.bowling_type.value_counts().to_dict())
print("pace_or_spin x bowling_type"); print(pd.crosstab(b.bowling_type,b.pace_or_spin))
print("bowl_speed zero share:", (b.bowl_speed==0).mean().round(3), " stroke null share", b.stroke.isna().mean().round(3))
print("stroke values:", b.stroke.value_counts().head(32).to_dict())
print("delivery_style values:", b.delivery_style.value_counts().to_dict())
# id-name consistency
for idc,nc in [('striker_id','striker_name'),('bowler_id','bowler_name')]:
    g=b.groupby(idc)[nc].nunique(); print(idc,'ids with >1 name:', (g>1).sum(), b[b[idc].isin(g[g>1].index)][[idc,nc]].drop_duplicates().head(8).values.tolist())
    g=b.groupby(nc)[idc].nunique(); print(nc,'names with >1 id:', (g>1).sum(), b[b[nc].isin(g[g>1].index)][[idc,nc]].drop_duplicates().head(10).values.tolist())
g=mp.groupby('player_name').player_id.nunique(); print('mapping names >1 id:', mp[mp.player_name.isin(g[g>1].index)][['player_id','player_name','team_name']].drop_duplicates().values.tolist())
g=mp.groupby('player_id').player_name.nunique(); print('mapping ids >1 name:', mp[mp.player_id.isin(g[g>1].index)][['player_id','player_name']].drop_duplicates().values.tolist())
# player coverage
allp=set(b.striker_id)|set(b.bowler_id)|set(b.non_striker_id)
print("bbb players not in mapping:", len(allp-set(mp.player_id)), " P11 players not in mapping:", len(set(p.player_id)-set(mp.player_id)))
# duplicates in bbb on key
k=['match_id','innings','overid','over_ball_num']; print("dup bbb keys:", b.duplicated(k).sum())
print("dup p11 keys:", p.duplicated(['match_id','team_id','player_id']).sum())
# innings completeness
inn = b.groupby(['match_id','innings']).agg(balls=('innings_ball_num','max'), maxover=('overid','max'), runs=('runs','sum'), ex=('extras1_runs','sum'), ex2=('extras_2_runs','sum'), wk=('is_wicket','sum'))
print(inn.describe().T)
print("innings with maxover<20 and wk<10 (possible truncated/DLS/chase-won):", ((inn.maxover<20)&(inn.wk<10)).sum())
per_match = b.groupby('match_id').innings.nunique().value_counts(); print("innings per match", per_match.to_dict())
# legal ball count per over
leg = b[~b.extras_type.isin(['wide','noball','Overstep'])] if True else b
# impact players
print("p11 is_played", p.is_played.value_counts().to_dict(), "impact", p.is_impact.value_counts().to_dict(), "impact_off", p.is_impact_off.value_counts().to_dict())
pm = p.merge(m[['match_id','match_format','season','comp_name']], on='match_id')
print(pd.crosstab(pm.comp_name.str.contains('IPL'), [pm.is_played, pm.is_impact]))
print("p11 rows per team-match:", p.groupby(['match_id','team_id']).size().describe().to_dict())
print("p11 matches not in matches:", len(set(p.match_id)-set(m.match_id)))
# bbb per format/season
bm = b.merge(m[['match_id','match_format','comp_name','match_date']], on='match_id')
bm['year']=bm.match_date.dt.year; bm['ipl']=bm.comp_name.str.contains('IPL')
print(pd.crosstab(bm.year, bm.ipl, values=bm.match_id, aggfunc='nunique'))
print("delivery time start check", b.delivery_ist_time.str[11:19].eq('00:00:00').mean())
# team ids for IPL
print(m[m.comp_name.str.contains('IPL')][['home_team_id','home_team']].drop_duplicates().sort_values('home_team_id').values.tolist())
