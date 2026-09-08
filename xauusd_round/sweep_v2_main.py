"""Optimise the CORRECTED strategy (engine2), then validate what survives."""
import itertools
import numpy as np, pandas as pd
from sweep2 import sweep2

if __name__ == "__main__":
    grid = []
    for step in (25.0, 50.0, 100.0):
        for buf in (2.0, 3.15, 6.0):
            for sl in (4.0, 8.0, 15.0):
                for rr in (1.0, 1.5, 2.0, 3.0):
                    grid.append(((("step", step), ("buf", buf), ("sl", sl), ("rr", rr)),
                                 dict(round_step=step, entry_buffer=buf,
                                      sl_from_round=sl, rr=rr)))
    print(f"stage A combos: {len(grid)}", flush=True)
    a = sweep2(grid)
    a["risk"] = a.buf + a.sl
    a.to_csv("results/v2_stageA.csv", index=False)
    cols = ["step","buf","sl","risk","rr","trades","win_rate","pf","exp_r","t",
            "net","dd","pos_frac"]
    print("\n### v2 STAGE A - grid/buffer/stop/rr at 09:00 IST (top 20 by expectancy)")
    print(a.nlargest(20, "exp_r")[cols].round(3).to_string(index=False))
    print("\n### same, ranked by t-stat (edge per unit of noise)")
    print(a.nlargest(15, "t")[cols].round(3).to_string(index=False))

    # ---- stage B: take the best shape, sweep the clock ----
    best = a.nlargest(1, "t").iloc[0]
    kw = dict(round_step=float(best.step), entry_buffer=float(best.buf),
              sl_from_round=float(best.sl), rr=float(best.rr))
    print(f"\n### v2 STAGE B - clock sweep for {kw}")
    g2 = [((("hour", h), ("min", m)), dict(setup_hour=h, setup_minute=m, **kw))
          for h in range(24) for m in (0, 30)]
    b = sweep2(g2)
    b.to_csv("results/v2_stageB.csv", index=False)
    b["key"] = b.apply(lambda r: f"{int(r.hour):02d}:{int(r['min']):02d}", axis=1)
    print(b.nlargest(15, "exp_r")[["key","trades","win_rate","pf","exp_r","t",
                                   "net","dd","pos_frac"]].round(3).to_string(index=False))
    n = len(b)
    from math import log, sqrt
    E = sqrt(2*log(n)) - (log(log(n))+log(4*np.pi))/(2*sqrt(2*log(n)))
    print(f"\n  {n} times tested; best t = {b.t.max():.2f}; "
          f"noise would give {E:.2f}. Mean expectancy across all times "
          f"= {b.exp_r.mean():+.4f}R")
