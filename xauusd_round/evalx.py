"""Multi-seed evaluation helpers with realistic-cost handling."""
import numpy as np, pandas as pd
from engine import Params, backtest, stats
from dataclasses import replace

CSV = "/root/.claude/uploads/4c4bebeb-eddd-5720-9f96-808b17f47cbb/bc24cd40-XAUUSD_15_Mins_Bid_2016.01.01_2026.06.09_1.csv"

def mc_eval(df, p: Params, seeds=8):
    """Average a parameter set over `seeds` Monte-Carlo intrabar realisations."""
    rows = []
    for s in range(seeds):
        rows.append(stats(backtest(df, replace(p, intrabar="mc", seed=s))))
    r = pd.DataFrame(rows)
    out = {f"{k}": float(r[k].mean()) for k in
           ("trades","win_rate","pf","net","ret_pct","max_dd_pct",
            "expectancy_r","max_loss_streak","avg_bars")}
    out["pf_sd"] = float(r["pf"].std())
    out["net_sd"] = float(r["net"].std())
    out["exp_r_sd"] = float(r["expectancy_r"].std())
    out["worst_net"] = float(r["net"].min())
    out["best_net"] = float(r["net"].max())
    out["pos_frac"] = float((r["net"] > 0).mean())
    return out

def line(tag, d):
    return (f"{tag:<42} n={d['trades']:>5.0f} WR={d['win_rate']:>5.1f}% "
            f"PF={d['pf']:.2f}±{d['pf_sd']:.2f} E={d['expectancy_r']:+.3f}R"
            f"±{d['exp_r_sd']:.3f} net=${d['net']:>9,.0f} DD={d['max_dd_pct']:>5.1f}% "
            f"win-seeds={d['pos_frac']*100:.0f}%")
