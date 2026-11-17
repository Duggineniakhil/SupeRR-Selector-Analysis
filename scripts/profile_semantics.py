import sys, re, pandas as pd, numpy as np
D = sys.argv[1]
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60); pd.set_option('display.max_rows', 300)
c = pd.read_csv(f"{D}/competitions.csv"); m = pd.read_csv(f"{D}/matches.csv").merge(c,on='comp_id')
p = pd.read_csv(f"{D}/playing_eleven.csv"); mp = pd.read_csv(f"{D}/competition_team_player_mapping.csv")
b = pd.read_csv(f"{D}/ball_by_ball.csv", low_memory=False)
print("ALL COMPS:"); print(c.sort_values(['season','comp_name'])[['comp_id','comp_name','match_format','season']].to_string(index=False))
print("'other' extras sample:"); print(b[b.extras_type=='other'][['match_id','innings','overid','over_ball_num','runs','extras1_runs','extras_2_runs','is_wicket']].head(8).to_string())
print("'Overstep' extras2>0 sample:"); print(b[(b.extras_type=='Overstep')&(b.extras_2_runs>0)][['runs','extras1_runs','extras_2_runs']].head(5).to_string())
b['tot']=b.runs+b.extras1_runs+b.extras_2_runs
b['legal']=~b.extras_type.isin(['wide','Overstep','other'])
lo=b.groupby(['match_id','innings','overid']).legal.sum(); print("legal balls per over dist:", lo.value_counts().sort_index().to_dict())
b['legal2']=~b.extras_type.isin(['wide','Overstep'])
lo2=b.groupby(['match_id','innings','overid']).legal2.sum(); print("legal (other counted legal) per over dist:", lo2.value_counts().sort_index().to_dict())
# validate totals vs margins
inn=b[b.innings<=2].groupby(['match_id','innings']).agg(tot=('tot','sum'),wk=('is_wicket','sum')).unstack()
inn.columns=[f"{a}{b_}" for a,b_ in inn.columns]; inn=inn.reset_index().merge(m[['match_id','result','revised_target','win_team_id']],on='match_id')
def margin(r):
    s=str(r); mm=re.search(r'by\s+(\d+)\s*(run|wicket|wkt)',s,re.I)
    return (int(mm.group(1)), 'runs' if mm.group(2).lower()=='run' else 'wkts') if mm else (None,None)
inn[['mN','mT']]=inn.result.apply(lambda s: pd.Series(margin(s)))
r=inn[(inn.mT=='runs')&inn.revised_target.isna()&~inn.result.str.contains('Super',case=False)]
r=r.assign(diff=r.tot1-r.tot2-r.mN); print("runs-margin check: n=",len(r)," exact match share:", (r['diff']==0).mean().round(3)); print(r[r['diff']!=0][['match_id','tot1','tot2','mN','result']].head(8).to_string())
w=inn[(inn.mT=='wkts')]; w=w.assign(chk=(10-w.wk2)==w.mN, reached=w.tot2>w.tot1); print("wkts-margin check n=",len(w)," wk match:", w.chk.mean().round(3), " chase total>first:", w.reached.mean().round(3))
print(w[~w.chk][['match_id','wk2','mN','result']].head(5).to_string())
# DLS units
print("revised overs values:", sorted(m.first_inn_revised_overs.dropna().unique()), sorted(m.second_inn_revised_overs.dropna().unique()))
# P11 semantics
pm=p.merge(m[['match_id','comp_name']],on='match_id')
print("is_played False rows by comp type:", pm[~pm.is_played].comp_name.str.contains('IPL').value_counts().to_dict())
x=pm[pm.match_id==pm[pm.comp_name.str.contains('IPL 2026')].match_id.iloc[0]]; print(x.to_string())
print("dup p11 key sample:"); d=p[p.duplicated(['match_id','team_id','player_id'],keep=False)].sort_values(['match_id','player_id']); print(d.head(6).to_string())
# man of match
print("MoM==0 share:", (m.man_of_the_match==0).mean().round(3))
print("Others stage comps:", m[m.stage=='Others'].comp_name.str.replace(r'\d{4}.*','',regex=True).value_counts().head(10).to_dict())
print("knockout comps:", m[m.knock_out==1][['comp_name','stage']].value_counts().to_dict())
# bowl speed coverage by IPL / year
bm=b.merge(m[['match_id','comp_name','season']],on='match_id'); bm['ipl']=bm.comp_name.str.contains('IPL')
print("bowl_speed>0 share by ipl/season:"); print(bm[bm.pace_or_spin=='Pace'].assign(s=lambda d:d.bowl_speed>0).groupby(['ipl','season']).s.mean().round(2).unstack())
# RR players per season
rr=mp[mp.team_id==3]; print("RR squad sizes:", rr.groupby('comp_name').size().to_dict())
print("RR 2026 squad:", rr[rr.comp_name=='IPL 2026'].player_name.tolist())
# volumes
leg=bm[~bm.extras_type.isin(['wide'])]
bf=leg.groupby('striker_id').size(); print("batters balls faced >=100:", (bf>=100).sum(), ">=300:", (bf>=300).sum(), ">=500:",(bf>=500).sum())
bb=bm[bm.extras_type.isna()|bm.extras_type.isin(['byes','legbyes'])].groupby('bowler_id').size(); print("bowlers legal balls >=120:", (bb>=120).sum(), ">=300:", (bb>=300).sum(), ">=600:",(bb>=600).sum())
# players by team type (A teams)
print("Team names:", sorted(m.home_team.unique().tolist()+m.away_team.unique().tolist()) and sorted(set(m.home_team)|set(m.away_team)))
# super over check
print("super over innings matches:", b[b.innings>2].match_id.unique().tolist())
# batting_order in bbb vs p11
print("bbb batting_order range", b.batting_order.min(), b.batting_order.max())
