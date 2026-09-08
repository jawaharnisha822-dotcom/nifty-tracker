"""CONTROL EXPERIMENT: does the ROUND NUMBER matter, or is any grid the same?

Shifts the $100/$50 grid by an offset. If round numbers carry real information,
offset=0 should stand out. If every offset performs alike, the 'round number'
premise is decoration and the result is just a volatility-breakout bracket.
"""
from sweep import *
if __name__ == "__main__":
    grid = []
    for hh, mi in [(9, 0), (21, 30), (0, 0)]:
        for off in [0, 5, 10, 15, 20, 25, 30, 35, 40, 45]:
            grid.append(((("hour", hh), ("min", mi), ("offset", off)),
                         dict(setup_hour=hh, setup_minute=mi, grid_offset=float(off))))
    df = sweep(grid)
    df.to_csv("results/sweep_control.csv", index=False)
    for hh, mi in [(9, 0), (21, 30), (0, 0)]:
        s = df[(df.hour == hh) & (df['min'] == mi)].sort_values("offset")
        print(f"\n### setup {hh:02d}:{mi:02d} — grid offset control")
        print(s[["offset","trades","win_rate","pf","exp_r","net","pos_frac"]]
              .round(3).to_string(index=False))
        real = s[s.offset == 0].exp_r.values[0]
        others = s[s.offset != 0].exp_r
        print(f"  round-number grid: {real:+.3f}R   |   "
              f"mean of 9 shifted grids: {others.mean():+.3f}R "
              f"(range {others.min():+.3f} .. {others.max():+.3f})")
        print(f"  -> round numbers rank {int((others > real).sum())+1} of 10")
