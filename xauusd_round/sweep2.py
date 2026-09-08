"""Parallel sweep harness for the CORRECTED engine (engine2)."""
import itertools
from dataclasses import replace
from multiprocessing import Pool
import numpy as np, pandas as pd
from engine2 import P2, backtest2, stats2
from engine import load_data
from sweep import CSV

EVAL = dict(mc_steps=120, cost_per_unit=0.30, seeds=6)
_DF = None

def _init(period):
    global _DF
    df = load_data(CSV)
    a, b = period
    _DF = df[(df.dt >= a) & (df.dt < b)].reset_index(drop=True)

def _run(item):
    key, kw = item
    p = replace(P2(), mc_steps=EVAL["mc_steps"],
                cost_per_unit=EVAL["cost_per_unit"], **kw)
    rows = [stats2(backtest2(_DF, replace(p, seed=s))) for s in range(EVAL["seeds"])]
    r = pd.DataFrame(rows)
    d = dict(key)
    d.update(trades=r.trades.mean(), win_rate=r.win_rate.mean(),
             pf=r.pf.mean(), exp_r=r.expectancy_r.mean(),
             exp_r_sd=r.expectancy_r.std(), net=r.net.mean(),
             worst_net=r.net.min(), dd=r.max_dd_pct.mean(),
             pos_frac=(r.net > 0).mean(), ret_pct=r.ret_pct.mean())
    # t-stat of the expectancy against per-trade noise (SD of R ~ 1.4)
    d["t"] = d["exp_r"] / (1.41 / np.sqrt(max(d["trades"], 1)))
    return d

def sweep2(grid, period=("2025-01-01", "2026-12-31"), procs=4):
    with Pool(procs, initializer=_init, initargs=(period,)) as pool:
        return pd.DataFrame(pool.map(_run, grid, chunksize=1))
