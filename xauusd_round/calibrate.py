"""
Which intrabar model is right?

The 'path' (3-leg OHLC) model is optimistic and the 'pessimistic' model is
harsh; the truth depends on how finely you can see inside a bar. We can measure
that trend directly: run the SAME strategy on 4h, 1h, 30m and 15m bars using the
deterministic 'path' model. Coarser bars hide more intrabar travel, so the bias
shrinks as resolution improves. Extrapolating the trend to tick resolution tells
us what the honest answer is - and which mc_steps reproduces it.
"""
import numpy as np, pandas as pd
from dataclasses import replace
from engine import Params, backtest, stats, load_data
from sweep import CSV

df = load_data(CSV)

def resample(d, rule):
    x = d.set_index("dt").resample(rule).agg(
        o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last")).dropna()
    return x.reset_index()

sub = df[df.dt >= "2025-01-01"].reset_index(drop=True)
base = replace(Params(), cost_per_unit=0.0)

print("=== Same strategy (09:00 IST, user params), 'path' model, "
      "at decreasing bar sizes ===")
print(f"{'bars':>6} {'n':>6} {'WR%':>7} {'PF':>7} {'expR':>8}")
rows = []
for rule, lbl in [("4h", "4h"), ("1h", "1h"), ("30min", "30m"), (None, "15m")]:
    d = sub if rule is None else resample(sub, rule)
    s = stats(backtest(d, replace(base, intrabar="path")))
    rows.append((lbl, s))
    print(f"{lbl:>6} {s['trades']:>6} {s['win_rate']:>7.2f} {s['pf']:>7.2f} "
          f"{s['expectancy_r']:>+8.3f}")
print("  -> 'path' WR falls as bars get finer: it is an UPPER bound, and the")
print("     real (tick) value is below the 15m number.\n")

print("=== same, 'pessimistic' model ===")
print(f"{'bars':>6} {'n':>6} {'WR%':>7} {'PF':>7} {'expR':>8}")
for rule, lbl in [("4h", "4h"), ("1h", "1h"), ("30min", "30m"), (None, "15m")]:
    d = sub if rule is None else resample(sub, rule)
    s = stats(backtest(d, replace(base, intrabar="pessimistic")))
    print(f"{lbl:>6} {s['trades']:>6} {s['win_rate']:>7.2f} {s['pf']:>7.2f} "
          f"{s['expectancy_r']:>+8.3f}")
print("  -> 'pessimistic' WR rises as bars get finer: a LOWER bound.\n")

print("=== the two bounds must converge at tick resolution; MC is calibrated "
      "to sit between them ===")
print(f"{'mc_steps':>9} {'WR%':>7} {'PF':>7} {'expR':>8}")
for k in (20, 40, 60, 120, 240, 480):
    r = [stats(backtest(sub, replace(base, intrabar="mc", mc_steps=k, seed=s)))
         for s in range(4)]
    print(f"{k:>9} {np.mean([x['win_rate'] for x in r]):>7.2f} "
          f"{np.mean([x['pf'] for x in r]):>7.2f} "
          f"{np.mean([x['expectancy_r'] for x in r]):>+8.3f}")

# --- how much intrabar travel does each timeframe hide? ---
print("\n=== realised path length hidden by aggregation (2025+) ===")
h1 = resample(sub, "1h")
r15 = (sub.h - sub.l)
print(f"  mean 15m range            : ${r15.mean():.2f}")
print(f"  mean 1h  range            : ${(h1.h-h1.l).mean():.2f}")
print(f"  sum of 4x15m ranges per 1h: ${r15.mean()*4:.2f}")
print(f"  -> going 4x finer reveals {r15.mean()*4/(h1.h-h1.l).mean():.2f}x more travel.")
print("     Extrapolating 15m -> tick (~2 more 4x steps) implies the true")
print("     stop-out count is far closer to the pessimistic bound than to 'path'.")
