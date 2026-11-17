import sys, pandas as pd
D=sys.argv[1]
m=pd.read_csv(f"{D}/matches.csv"); b=pd.read_csv(f"{D}/ball_by_ball.csv",low_memory=False)
x=m[m[['first_inn_revised_overs','second_inn_revised_overs','revised_target']].notna().any(axis=1)]
b['tot']=b.runs+b.extras1_runs+b.extras_2_runs
b['legal']=~b.extras_type.isin(['wide','Overstep','other'])
g=b[b.innings<=2].groupby(['match_id','innings']).agg(tot=('tot','sum'),legal=('legal','sum'),wk=('is_wicket','sum')).unstack()
g.columns=[f"{a}{c}" for a,c in g.columns]
print(x[['match_id','first_inn_revised_overs','second_inn_revised_overs','revised_target','win_team_id','result']].merge(g,left_on='match_id',right_index=True,how='left').to_string())
one=b.groupby('match_id').innings.agg(['min','max','nunique']); print(one[one['nunique']==1]['min'].value_counts())
print(m[m.match_id.isin(one[one['nunique']==1].index)].result.value_counts())
