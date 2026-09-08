"""
FINAL VALIDATION on the corrected engine (engine2).

A configuration is only trusted if it is positive:
  * at every intrabar resolution (40 / 120 / 320 sub-steps), AND
  * in BOTH volatility regimes (2016-2024 quiet, 2025-2026 violent).

An ATR-scaled stop is included because a FIXED dollar stop cannot be correct in
both eras: median 15-min range was $0.93 in 2018 and $9.89 in 2026.
"""
import numpy as np, pandas as pd
from dataclasses import replace
from multiprocessing import Pool
from engine2 import P2, backtest2, stats2
from engine import load_data
from sweep import CSV

CANDS = [
    # name                                    kwargs
    ("F0 user-equivalent: $100 buf3.15 sl2 rr2 @09", dict(round_step=100., entry_buffer=3.15, sl_from_round=2., rr=2., setup_hour=9)),
    ("F1 fixed $100 buf2 sl8  rr3.0 @09",     dict(round_step=100., entry_buffer=2.,  sl_from_round=8.,  rr=3.,  setup_hour=9)),
    ("F2 fixed $100 buf2 sl8  rr3.0 @06",     dict(round_step=100., entry_buffer=2.,  sl_from_round=8.,  rr=3.,  setup_hour=6)),
    ("F3 fixed $100 buf2 sl15 rr2.0 @09",     dict(round_step=100., entry_buffer=2.,  sl_from_round=15., rr=2.,  setup_hour=9)),
    ("F4 fixed $100 buf6 sl15 rr1.5 @09",     dict(round_step=100., entry_buffer=6.,  sl_from_round=15., rr=1.5, setup_hour=9)),
    ("A1 ATR  $100 x1.0 rr2.0 @09",           dict(round_step=100., sl_mode="atr", atr_mult=1.0, rr=2.,  setup_hour=9)),
    ("A2 ATR  $100 x1.5 rr2.0 @09",           dict(round_step=100., sl_mode="atr", atr_mult=1.5, rr=2.,  setup_hour=9)),
    ("A3 ATR  $100 x2.0 rr2.0 @09",           dict(round_step=100., sl_mode="atr", atr_mult=2.0, rr=2.,  setup_hour=9)),
    ("A4 ATR  $100 x3.0 rr2.0 @09",           dict(round_step=100., sl_mode="atr", atr_mult=3.0, rr=2.,  setup_hour=9)),
    ("A5 ATR  $100 x2.0 rr3.0 @09",           dict(round_step=100., sl_mode="atr", atr_mult=2.0, rr=3.,  setup_hour=9)),
    ("A6 ATR  $100 x2.0 rr1.5 @09",           dict(round_step=100., sl_mode="atr", atr_mult=2.0, rr=1.5, setup_hour=9)),
    ("A7 ATR  $50  x2.0 rr2.0 @09",           dict(round_step=50.,  sl_mode="atr", atr_mult=2.0, rr=2.,  setup_hour=9)),
    ("A8 ATR  $100 x2.0 rr2.0 @06",           dict(round_step=100., sl_mode="atr", atr_mult=2.0, rr=2.,  setup_hour=6)),
    ("A9 ATR  $100 x1.5 rr3.0 @09",           dict(round_step=100., sl_mode="atr", atr_mult=1.5, rr=3.,  setup_hour=9)),
]
RES, SEEDS = [40, 120, 320], 5
_DF = None
def _init(a, b):
    global _DF
    d = load_data(CSV); _DF = d[(d.dt >= a) & (d.dt < b)].reset_index(drop=True)

def _job(t):
    name, kw, k = t
    p = replace(P2(), mc_steps=k, cost_per_unit=0.30, **kw)
    r = [stats2(backtest2(_DF, replace(p, seed=s))) for s in range(SEEDS)]
    return dict(name=name, k=k,
                exp_r=float(np.mean([x["expectancy_r"] for x in r])),
                pf=float(np.mean([x["pf"] for x in r])),
                wr=float(np.mean([x["win_rate"] for x in r])),
                dd=float(np.mean([x["max_dd_pct"] for x in r])),
                n=float(np.mean([x["trades"] for x in r])))

def run(a, b, tag):
    jobs = [(n, kw, k) for n, kw in CANDS for k in RES]
    with Pool(4, initializer=_init, initargs=(a, b)) as pool:
        d = pd.DataFrame(pool.map(_job, jobs, chunksize=1))
    piv = d.pivot(index="name", columns="k", values="exp_r")
    piv.columns = [f"{tag}{c}" for c in piv.columns]
    fine = d[d.k == 320].set_index("name")
    piv[f"{tag}_pf"] = fine.pf
    piv[f"{tag}_wr"] = fine.wr
    piv[f"{tag}_dd"] = fine.dd
    piv[f"{tag}_n"] = fine.n
    return piv

if __name__ == "__main__":
    new = run("2025-01-01", "2026-12-31", "NEW")
    print("### 2025-01-01 -> 2026-06-09   (expectancy R at 3 resolutions)")
    print(new.sort_values("NEW320", ascending=False).round(3).to_string(), flush=True)

    old = run("2016-01-01", "2025-01-01", "OLD")
    print("\n### 2016-2024 OUT-OF-SAMPLE")
    print(old.sort_values("OLD320", ascending=False).round(3).to_string())

    m = new.join(old)
    m["WORST"] = m[["NEW40","NEW120","NEW320","OLD40","OLD120","OLD320"]].min(axis=1)
    m.to_csv("results/final_validation.csv")
    print("\n### VERDICT — worst case across 3 resolutions x 2 eras")
    cols = ["NEW320","OLD320","WORST","NEW_pf","OLD_pf","NEW_wr","NEW_dd","NEW_n","OLD_n"]
    print(m.sort_values("WORST", ascending=False)[cols].round(3).to_string())
    surv = m[m.WORST > 0]
    print(f"\n{len(surv)} of {len(m)} configurations are positive everywhere.")
