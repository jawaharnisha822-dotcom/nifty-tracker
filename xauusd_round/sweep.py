"""Parallel parameter sweep with multi-seed Monte-Carlo intrabar evaluation."""
import itertools, os, sys, json
from dataclasses import replace
from multiprocessing import Pool
import numpy as np, pandas as pd
from engine import Params, backtest, stats, load_data

CSV = ("/root/.claude/uploads/4c4bebeb-eddd-5720-9f96-808b17f47cbb/"
       "bc24cd40-XAUUSD_15_Mins_Bid_2016.01.01_2026.06.09_1.csv")

# Evaluation standard used for ALL optimisation:
#   mc_steps=120  -> ~7.5-second intrabar resolution (conservative)
#   cost 0.30     -> typical XAUUSD spread + commission, round trip
#   6 seeds       -> guards against one lucky random path
EVAL = dict(mc_steps=120, cost_per_unit=0.30, seeds=6)

_DF = None
def _init(period):
    global _DF
    df = load_data(CSV)
    a, b = period
    _DF = df[(df.dt >= a) & (df.dt < b)].reset_index(drop=True)

def _run(item):
    key, kw = item
    p = replace(Params(), intrabar="mc",
                mc_steps=EVAL["mc_steps"], cost_per_unit=EVAL["cost_per_unit"], **kw)
    rows = [stats(backtest(_DF, replace(p, seed=s))) for s in range(EVAL["seeds"])]
    r = pd.DataFrame(rows)
    d = dict(key)
    d.update(trades=r.trades.mean(), win_rate=r.win_rate.mean(),
             pf=r.pf.mean(), pf_sd=r.pf.std(),
             exp_r=r.expectancy_r.mean(), exp_r_sd=r.expectancy_r.std(),
             net=r.net.mean(), net_sd=r.net.std(), worst_net=r.net.min(),
             dd=r.max_dd_pct.mean(), pos_frac=(r.net > 0).mean(),
             ret_pct=r.ret_pct.mean())
    return d

def sweep(grid_items, period=("2025-01-01", "2026-12-31"), procs=4):
    with Pool(procs, initializer=_init, initargs=(period,)) as pool:
        out = pool.map(_run, grid_items, chunksize=1)
    return pd.DataFrame(out)

def fmt(df, by="exp_r", n=25, cols=None):
    cols = cols or [c for c in df.columns if c not in
                    ("net_sd","pf_sd","exp_r_sd","worst_net")]
    d = df.sort_values(by, ascending=False).head(n).copy()
    for c in ("trades","win_rate","pf","exp_r","net","dd","pos_frac","ret_pct"):
        if c in d: d[c] = d[c].round(3)
    return d[cols].to_string(index=False)
