"""
(a) Can a volatility-scaled stop WITH A FLOOR beat the fixed $17 stop in both eras?
    Plain ATR(14) failed out-of-sample because in 2016-24 it produced a ~$2 stop,
    which is inside that era's noise too. risk = max(min_risk, atr_mult*ATR)
    should fix that while still scaling up if gold gets wilder.
(b) Detailed profile of the winning fixed configuration.
"""
import numpy as np, pandas as pd
from dataclasses import replace
from multiprocessing import Pool
from engine2 import P2, backtest2, stats2
from engine import load_data
from sweep import CSV

RES, SEEDS = [40, 320], 4
_DF = None
def _init(a, b):
    global _DF
    d = load_data(CSV); _DF = d[(d.dt >= a) & (d.dt < b)].reset_index(drop=True)

def grid():
    g = []
    for alen in (14, 96):
        for am in (2.0, 3.0, 4.0):
            for mr in (0.0, 10.0, 17.0):
                for rr in (1.5, 2.0):
                    g.append(((("alen",alen),("amult",am),("minrisk",mr),("rr",rr)),
                              dict(sl_mode="atr", atr_len=alen, atr_mult=am,
                                   min_risk=mr, rr=rr, round_step=100.,
                                   entry_buffer=2.0, setup_hour=9)))
    return g

def _job(t):
    key, kw, k = t
    p = replace(P2(), mc_steps=k, cost_per_unit=0.30, **kw)
    r = [stats2(backtest2(_DF, replace(p, seed=s))) for s in range(SEEDS)]
    d = dict(key); d["k"] = k
    d["exp_r"] = float(np.mean([x["expectancy_r"] for x in r]))
    d["pf"] = float(np.mean([x["pf"] for x in r]))
    d["n"] = float(np.mean([x["trades"] for x in r]))
    d["dd"] = float(np.mean([x["max_dd_pct"] for x in r]))
    return d

def run(a, b, tag):
    jobs = [(k, kw, s) for k, kw in grid() for s in RES]
    with Pool(4, initializer=_init, initargs=(a, b)) as pool:
        d = pd.DataFrame(pool.map(_job, jobs, chunksize=2))
    idx = ["alen","amult","minrisk","rr"]
    piv = d.pivot_table(index=idx, columns="k", values="exp_r")
    piv.columns = [f"{tag}{c}" for c in piv.columns]
    piv[f"{tag}_pf"] = d[d.k == 320].set_index(idx).pf
    piv[f"{tag}_n"] = d[d.k == 320].set_index(idx).n
    return piv

if __name__ == "__main__":
    new = run("2025-01-01", "2026-12-31", "NEW")
    old = run("2016-01-01", "2025-01-01", "OLD")
    m = new.join(old)
    m["WORST"] = m[["NEW40","NEW320","OLD40","OLD320"]].min(axis=1)
    m.to_csv("results/atr_floor.csv")
    print("### ATR stop WITH a minimum-risk floor — top 15 by worst case")
    print(m.sort_values("WORST", ascending=False).head(15).round(3).to_string())
    s = m[m.WORST > 0]
    print(f"\n{len(s)} of {len(m)} survive both eras at both resolutions.")
    print("\n(reference: fixed $100/buf2/sl15/rr2 @09 scored WORST = +0.068)")
