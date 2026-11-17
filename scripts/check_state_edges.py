import pandas as pd
I="data_interim"
b=pd.read_parquet(f"{I}/ball_state.parquet"); inn=pd.read_parquet(f"{I}/innings.parquet"); m=pd.read_parquet(f"{I}/matches.parquet")
ol=b.groupby(["match_id","innings","overid"]).is_legal.sum()
print("7-legal and 0-legal overs:", ol[(ol>6)|(ol==0)].to_dict())
for k in ol[(ol>6)|(ol==0)].index:
    print(b[(b.match_id==k[0])&(b.innings==k[1])&(b.overid==k[2])][["over_ball_num","innings_ball_num","extras_type","runs","total_runs","is_wicket"]].to_string())
ids=[14130,14164,15795,31278,48514]
print(inn[inn.match_id.isin(ids)][["match_id","innings","total","wkts","legal","max_over","ball_limit","target"]].to_string())
print(m[m.match_id.isin(ids+[20190])][["match_id","comp_name","result","first_inn_revised_overs","revised_target"]].to_string())
# overs missing within innings?
ov=b[b.innings<=2].groupby(["match_id","innings"]).overid.agg(["min","max","nunique"])
gap=ov[(ov["max"]-ov["min"]+1)!=ov["nunique"]]; print("innings with missing overs:", len(gap)); print(gap.head(20))
# runs needed <=0
x=b[b.is_chase&(b.runs_needed_before<=0)&(b.innings==2)]; print(x[["match_id","overid","over_ball_num","score_before","target","is_dls"]].to_string())
# DLS without revised target
d=m[m.is_dls & m.revised_target.isna() & ~m.is_no_result][["match_id","first_inn_revised_overs","second_inn_revised_overs","result"]]
print(d.merge(inn[inn.innings==2][["match_id","total","legal","target"]],on="match_id",how="left").merge(inn[inn.innings==1][["match_id","total","legal"]],on="match_id",suffixes=("2","1")).to_string())
