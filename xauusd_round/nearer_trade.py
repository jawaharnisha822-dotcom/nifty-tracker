"""Is the 'nearer round number' effect TRADEABLE?

Test 1 - BREAKOUT side filter: place the stop order only on the nearer side,
         only on the farther side, or both (the current design).
Test 2 - MAGNET trade: the touch statistic says price is DRAWN to the nearer
         level. That is a target, not a breakout. Tested separately below.
"""
import numpy as np, pandas as pd
from dataclasses import replace
from multiprocessing import Pool
from engine2 import P2, backtest2, stats2
from engine import load_data
from sweep import CSV

REC = dict(round_step=100., entry_buffer=2.0, sl_mode="atr", atr_len=96,
           atr_mult=4.0, min_risk=17.0, rr=1.5, setup_hour=9)
USR = dict(round_step=100., entry_buffer=3.15, sl_from_round=2.0, rr=2.0, setup_hour=9)
RES, SEEDS = [40, 320], 6
_DF = None
def _init(a, b):
    global _DF
    d = load_data(CSV); _DF = d[(d.dt >= a) & (d.dt < b)].reset_index(drop=True)

def _job(t):
    name, kw, k = t
    p = replace(P2(), mc_steps=k, cost_per_unit=0.30, **kw)
    r = [stats2(backtest2(_DF, replace(p, seed=s))) for s in range(SEEDS)]
    return dict(name=name, k=k,
                n=float(np.mean([x["trades"] for x in r])),
                wr=float(np.mean([x["win_rate"] for x in r])),
                pf=float(np.mean([x["pf"] for x in r])),
                exp_r=float(np.mean([x["expectancy_r"] for x in r])),
                net=float(np.mean([x["net"] for x in r])),
                dd=float(np.mean([x["max_dd_pct"] for x in r])))

CANDS = []
for base_name, base in [("RECOMMENDED", REC), ("YOUR params", USR)]:
    for sel in ("both", "nearer", "farther"):
        CANDS.append((f"{base_name:<12} | {sel:<7}", dict(base, side_select=sel)))

def run(a, b, tag):
    jobs = [(n, kw, k) for n, kw in CANDS for k in RES]
    with Pool(4, initializer=_init, initargs=(a, b)) as pool:
        d = pd.DataFrame(pool.map(_job, jobs, chunksize=1))
    print(f"\n### {tag}")
    fine = d[d.k == 320].set_index("name")
    coarse = d[d.k == 40].set_index("name")
    out = pd.DataFrame({"trades": fine.n.round(0), "WR%": fine.wr.round(1),
                        "PF": fine.pf.round(3), "expR_fine": fine.exp_r.round(3),
                        "expR_coarse": coarse.exp_r.round(3),
                        "net$": fine.net.round(0), "DD%": fine.dd.round(1)})
    print(out.to_string())
    return out

if __name__ == "__main__":
    a = run("2025-01-01", "2026-12-31", "2025-01-01 -> 2026-06-09")
    b = run("2016-01-01", "2025-01-01", "2016-2024 OUT-OF-SAMPLE")
    a.to_csv("results/nearer_trade_new.csv"); b.to_csv("results/nearer_trade_old.csv")
