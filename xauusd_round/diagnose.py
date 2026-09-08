"""Structural diagnostics on the strategy as written."""
import numpy as np, pandas as pd
from dataclasses import replace
from engine import Params, backtest, stats, load_data
from sweep import CSV

df = load_data(CSV)
sub = df[df.dt >= "2025-01-01"].reset_index(drop=True)

# ---- 1. how far are the entry levels from the 09:00 open? ----
s = sub[(sub.dt.dt.hour == 9) & (sub.dt.dt.minute == 0)].copy()
for step in (100, 50):
    up = np.ceil(s.o / step) * step
    lo = np.floor(s.o / step) * step
    s[f"d_up{step}"] = up + 3.15 - s.o
    s[f"d_dn{step}"] = s.o - (lo - 3.15)
print("=== Distance from 09:00 open to the entry stop ($) — 2025+ ===")
print(s[["d_up100","d_dn100","d_up50","d_dn50"]].describe().round(2).to_string())

# ---- 2. group / side / year breakdown at the user's params ----
allt = []
for sd in range(6):
    t = backtest(sub, replace(Params(), intrabar="mc", mc_steps=120,
                              cost_per_unit=0.30, seed=sd))["trades"]
    t["seed"] = sd
    allt.append(t)
T = pd.concat(allt)
print("\n=== By round group (avg per seed) ===")
g = T.groupby(["group","seed"]).agg(n=("pnl","size"), net=("pnl","sum"),
                                    wr=("pnl", lambda x:(x>0).mean()*100)).reset_index()
print(g.groupby("group")[["n","net","wr"]].mean().round(2).to_string())
print("\n=== By side ===")
g = T.groupby(["side","seed"]).agg(n=("pnl","size"), net=("pnl","sum"),
                                   wr=("pnl", lambda x:(x>0).mean()*100)).reset_index()
print(g.groupby("side")[["n","net","wr"]].mean().round(2).to_string())
print("\n=== By year (expectancy in R) ===")
T["yr"] = pd.to_datetime(T.entry_time).dt.year
g = T.groupby(["yr","seed"]).agg(n=("r","size"), expR=("r","mean"),
                                 wr=("pnl", lambda x:(x>0).mean()*100)).reset_index()
print(g.groupby("yr")[["n","expR","wr"]].mean().round(3).to_string())

# ---- 3. how often do BUY100 and BUY50 sit at the identical price? ----
dup_b = (np.ceil(s.o/100)*100 == np.ceil(s.o/50)*50).mean()
dup_s = (np.floor(s.o/100)*100 == np.floor(s.o/50)*50).mean()
print(f"\n=== Level collision (double risk on one level) ===")
print(f"  BUY100 == BUY50  on {dup_b*100:.1f}% of days")
print(f"  SELL100 == SELL50 on {dup_s*100:.1f}% of days")
print(f"  at least one side collides: {((np.ceil(s.o/100)*100==np.ceil(s.o/50)*50)|(np.floor(s.o/100)*100==np.floor(s.o/50)*50)).mean()*100:.1f}%")
