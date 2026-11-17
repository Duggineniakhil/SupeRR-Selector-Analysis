import sys, pandas as pd, numpy as np
D = sys.argv[1]
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60); pd.set_option('display.max_rows', 200)
files = ['competitions','teams','matches','playing_eleven','competition_team_player_mapping','ball_by_ball']
dfs = {f: pd.read_csv(f"{D}/{f}.csv", low_memory=False) for f in files}
for f, df in dfs.items():
    print(f"\n######## {f}: shape={df.shape}  full-dup-rows={df.duplicated().sum()}")
    s = pd.DataFrame({'dtype': df.dtypes.astype(str), 'nulls': df.isna().sum(), 'nunique': df.nunique(),
                      'sample': [df[c].dropna().unique()[:4].tolist() for c in df.columns]})
    print(s.to_string())
