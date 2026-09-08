"""
DECISIVE TEST: resolution stability.

A parameter set whose sign flips when you look inside the bar more finely is
not a strategy, it is a measurement artefact. A trustworthy set stays positive
at every intrabar resolution, because its stop sits OUTSIDE the noise band.
"""
import numpy as np, pandas as pd
from dataclasses import replace
from multiprocessing import Pool
from engine import Params, backtest, stats, load_data
from sweep import CSV

CANDS = [
    ("USER  buf3.15 sl2.0  rr2.0 09:00 [100+50]", dict()),
    ("USER params @05:30",              dict(setup_hour=5, setup_minute=30)),
    ("wide  buf3.15 sl15.0 rr1.5 09:00", dict(entry_buffer=3.15, sl_from_round=15.0, rr=1.5)),
    ("wide  buf3.15 sl6.0  rr3.0 09:00", dict(entry_buffer=3.15, sl_from_round=6.0, rr=3.0)),
    ("wide  buf2.0  sl15.0 rr2.0 09:00", dict(entry_buffer=2.0, sl_from_round=15.0, rr=2.0)),
    ("wide  buf5.0  sl15.0 rr1.5 09:00", dict(entry_buffer=5.0, sl_from_round=15.0, rr=1.5)),
    ("wide sl15 rr1.5 $100 ONLY",        dict(entry_buffer=3.15, sl_from_round=15.0,
                                              rr=1.5, round50=False)),
    ("wide sl15 rr1.5 $100 ONLY @05:30", dict(entry_buffer=3.15, sl_from_round=15.0, rr=1.5,
                                              round50=False, setup_hour=5, setup_minute=30)),
]
STEPS = [40, 80, 160, 320]
_DF = None
def _init(a, b):
    global _DF
    d = load_data(CSV); _DF = d[(d.dt >= a) & (d.dt < b)].reset_index(drop=True)

def _job(t):
    name, kw, k = t
    p = replace(Params(), intrabar="mc", mc_steps=k, cost_per_unit=0.30, **kw)
    r = [stats(backtest(_DF, replace(p, seed=s))) for s in range(6)]
    return (name, k, float(np.mean([x["expectancy_r"] for x in r])),
            float(np.mean([x["pf"] for x in r])),
            float(np.mean([x["win_rate"] for x in r])),
            float(np.mean([x["trades"] for x in r])))

def run(a, b, title):
    jobs = [(n, kw, k) for n, kw in CANDS for k in STEPS]
    with Pool(4, initializer=_init, initargs=(a, b)) as pool:
        out = pool.map(_job, jobs, chunksize=1)
    d = pd.DataFrame(out, columns=["name", "k", "exp_r", "pf", "wr", "n"])
    piv = d.pivot(index="name", columns="k", values="exp_r").round(3)
    piv["min"] = piv.min(axis=1)
    piv["STABLE"] = np.where(piv[STEPS].gt(0).all(axis=1), "YES", "no")
    piv["n"] = d.groupby("name").n.mean().round(0)
    print(f"\n### {title}  — expectancy (R) vs intrabar resolution")
    print("    (columns = mc_steps; higher = finer view inside the bar)")
    print(piv.sort_values("min", ascending=False).to_string())
    return piv

if __name__ == "__main__":
    run("2025-01-01", "2026-12-31", "2025-01-01 -> 2026-06-09  (the period you asked for)")
    run("2016-01-01", "2025-01-01", "2016-2024  OUT-OF-SAMPLE")
