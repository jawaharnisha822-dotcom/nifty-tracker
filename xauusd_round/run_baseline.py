import pandas as pd, numpy as np
from engine import Params, load_data, backtest, stats

CSV = "/root/.claude/uploads/4c4bebeb-eddd-5720-9f96-808b17f47cbb/bc24cd40-XAUUSD_15_Mins_Bid_2016.01.01_2026.06.09_1.csv"
df = load_data(CSV)
print("bars:", len(df), df.dt.min(), "->", df.dt.max())

# sanity: is there a 09:00 IST bar most weekdays?
s = df[(df.dt.dt.hour==9)&(df.dt.dt.minute==0)]
print("09:00 IST bars:", len(s), s.dt.min(), s.dt.max())
print("per-year 09:00 bars:\n", s.dt.dt.year.value_counts().sort_index())

def show(name, res):
    st = stats(res)
    print(f"\n=== {name} ===")
    print(f"  {res['params'].label()}")
    for k,v in st.items():
        print(f"   {k:>16}: {v:,.2f}" if isinstance(v,float) else f"   {k:>16}: {v}")
    return st

for tag, sub in [("2025+ (2025-01-01 -> 2026-06-09)", df[df.dt>="2025-01-01"]),
                 ("FULL 2016-2026", df)]:
    sub = sub.reset_index(drop=True)
    p = Params()  # user's exact settings
    show(f"USER PARAMS | {tag} | zero cost | pessimistic", backtest(sub, p))
    show(f"USER PARAMS | {tag} | $0.30 cost | pessimistic",
         backtest(sub, Params(cost_per_unit=0.30)))
    show(f"USER PARAMS | {tag} | zero cost | OPTIMISTIC",
         backtest(sub, Params(intrabar="optimistic")))
