"""Detailed profile of the recommended configuration."""
import numpy as np, pandas as pd
from dataclasses import replace
from engine2 import P2, backtest2, stats2
from engine import load_data
from sweep import CSV

WIN = dict(round_step=100., entry_buffer=2.0, sl_from_round=15.0, rr=2.0,
           setup_hour=9, setup_minute=0, valid_bars=48, max_slip=1.0)
df = load_data(CSV)

for tag, a, b in [("2025-01-01 -> 2026-06-09", "2025-01-01", "2026-12-31"),
                  ("2016-2024 OUT-OF-SAMPLE", "2016-01-01", "2025-01-01"),
                  ("FULL 2016-2026", "2016-01-01", "2026-12-31")]:
    d = df[(df.dt >= a) & (df.dt < b)].reset_index(drop=True)
    rows, tr = [], []
    for s in range(8):
        r = backtest2(d, replace(P2(), mc_steps=320, cost_per_unit=0.30, seed=s, **WIN))
        rows.append(stats2(r)); t = r["trades"]; t["seed"] = s; tr.append(t)
    st = pd.DataFrame(rows)
    print(f"\n=== {tag} ===  (mc_steps=320 = harshest realistic resolution, "
          f"$0.30 cost, 8 seeds)")
    print(f"  trades      {st.trades.mean():.0f}")
    print(f"  win rate    {st.win_rate.mean():.2f}%")
    print(f"  profit factor {st.pf.mean():.3f}  (range {st.pf.min():.2f}-{st.pf.max():.2f})")
    print(f"  expectancy  {st.expectancy_r.mean():+.3f} R  (sd {st.expectancy_r.std():.3f})")
    print(f"  net on $5k  ${st.net.mean():,.0f}   ({st.ret_pct.mean():+.1f}%)")
    print(f"  max DD      {st.max_dd_pct.mean():.1f}%")
    print(f"  seeds profitable {(st.net>0).sum()}/8   max losing streak {st.max_loss_streak.mean():.0f}")
    T = pd.concat(tr); T["yr"] = pd.to_datetime(T.entry_time).dt.year
    g = T.groupby(["yr","seed"]).agg(n=("r","size"), expR=("r","mean"),
                                     net=("pnl","sum")).reset_index()
    print("  by year:")
    print(g.groupby("yr")[["n","expR","net"]].mean().round(3).to_string())
    if "2025" in tag:
        print("  by side:")
        print(T.groupby("side").agg(n=("r","size"), expR=("r","mean"))
              .assign(n=lambda x: x.n/8).round(3).to_string())
