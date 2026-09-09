"""
MAGNET TEST - the literal reading of the idea.

The touch statistic says price is DRAWN to the nearer $100 level. That is a
TARGET, not a breakout. So: at 09:00 IST enter in the direction of the nearer
round number, take profit AT that round number, and stop out the other way.

Reward is fixed by geometry (= distance to the level). Risk is set as a multiple
`m` of that distance, so R:R = 1/m. With a ~90% hit rate a large m can still pay.
"""
import math
import numpy as np, pandas as pd
from dataclasses import dataclass, replace
from multiprocessing import Pool
from engine import load_data
from sweep import CSV


@dataclass
class MP:
    step: float = 100.0
    setup_hour: int = 9
    setup_minute: int = 0
    stop_mult: float = 2.0        # SL = stop_mult x distance-to-level
    tp_pullback: float = 0.0      # take profit this far BEFORE the level
    min_dist: float = 0.0         # skip if the level is nearer than this
    max_dist: float = 999.0       # skip if the level is further than this
    valid_bars: int = 96          # 24h
    risk_percent: float = 1.0
    initial_capital: float = 5000.0
    cost_per_unit: float = 0.30
    mc_steps: int = 320
    seed: int = 0


def run(df: pd.DataFrame, p: MP) -> dict:
    O, H, L, C = (df[k].to_numpy(float) for k in "ohlc")
    setup = ((df.dt.dt.hour == p.setup_hour) &
             (df.dt.dt.minute == p.setup_minute)).to_numpy()
    n = len(df)
    rng = np.random.default_rng(p.seed)
    K = p.mc_steps
    tg = np.arange(K + 1) / K

    def path(o, h, l, c):
        w = np.concatenate([[0.0], np.cumsum(rng.standard_normal(K))])
        br = w - tg * w[-1]
        x = o + (c - o) * tg + br
        sp = x.max() - x.min()
        if sp > 1e-12 and (h - l) > 1e-12:
            x = o + (c - o) * tg + br * ((h - l) / sp)
        x[x.argmax()] = h; x[x.argmin()] = l
        return x

    equity = p.initial_capital
    realized = 0.0
    trades = []
    pos = None

    for i in range(n):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if pos is not None:
            long = pos["side"] == "long"
            sl, tp = pos["sl"], pos["tp"]
            done = None
            # gap at the open
            if long:
                done = (o, "SL") if o <= sl else ((o, "TP") if o >= tp else None)
            else:
                done = (o, "SL") if o >= sl else ((o, "TP") if o <= tp else None)
            if done is None and not (max(sl, tp) < l or min(sl, tp) > h):
                for a, b in zip(*(lambda x: (x[:-1], x[1:]))(path(o, h, l, c))):
                    if a == b:
                        continue
                    up = b > a
                    lo_, hi_ = (a, b) if up else (b, a)
                    cand = []
                    for price, why in ((sl, "SL"), (tp, "TP")):
                        if lo_ <= price <= hi_:
                            cand.append((abs(price - a), price, why))
                    if cand:
                        cand.sort()
                        done = (cand[0][1], cand[0][2]); break
            if done is None and i >= pos["expire"]:
                done = (c, "EXPIRY")
            if done:
                px, why = done
                sgn = 1.0 if long else -1.0
                pnl = (sgn * (px - pos["entry"]) - p.cost_per_unit) * pos["qty"]
                realized += pnl; equity = p.initial_capital + realized
                trades.append(dict(dt=df.dt.iloc[pos["i"]], side=pos["side"],
                                   entry=pos["entry"], exit=px, reason=why,
                                   pnl=pnl, r=pnl / (pos["risk"] * pos["qty"]),
                                   dist=pos["dist"], equity=equity,
                                   bars=i - pos["i"]))
                pos = None

        if setup[i] and pos is None and i + 1 < n:
            ref = O[i]
            up_ = math.ceil(ref / p.step) * p.step
            dn_ = math.floor(ref / p.step) * p.step
            if up_ == dn_:
                continue
            d_up, d_dn = up_ - ref, ref - dn_
            long = d_up < d_dn
            dist = min(d_up, d_dn)
            if not (p.min_dist <= dist <= p.max_dist):
                continue
            entry = O[i + 1]                      # fill at the next bar's open
            lvl = up_ if long else dn_
            tp = lvl - p.tp_pullback if long else lvl + p.tp_pullback
            reward = abs(tp - entry)
            if reward <= 0.05:
                continue
            risk = p.stop_mult * reward
            sl = entry - risk if long else entry + risk
            qty = equity * (p.risk_percent / 100.0) / risk
            pos = dict(side="long" if long else "short", entry=entry, sl=sl, tp=tp,
                       qty=qty, risk=risk, i=i + 1, dist=dist,
                       expire=i + 1 + p.valid_bars)

    t = pd.DataFrame(trades)
    if len(t) == 0:
        return dict(trades=0, wr=0, pf=float("nan"), exp_r=0, net=0, dd=0)
    pnl = t.pnl.to_numpy()
    gp, gl = pnl[pnl > 0].sum(), abs(pnl[pnl <= 0].sum())
    eq = np.concatenate([[p.initial_capital], p.initial_capital + np.cumsum(pnl)])
    peak = np.maximum.accumulate(eq)
    return dict(trades=len(t), wr=float((pnl > 0).mean() * 100),
                pf=float(gp / gl) if gl > 0 else float("inf"),
                exp_r=float(t.r.mean()), net=float(pnl.sum()),
                dd=float(((peak - eq) / peak * 100).max()),
                tp_rate=float((t.reason == "TP").mean() * 100),
                expiry_rate=float((t.reason == "EXPIRY").mean() * 100),
                df=t)


_DF = None
def _init(a, b):
    global _DF
    d = load_data(CSV); _DF = d[(d.dt >= a) & (d.dt < b)].reset_index(drop=True)

def _job(t):
    key, kw = t
    r = [run(_DF, replace(MP(), seed=s, **kw)) for s in range(5)]
    d = dict(key)
    for m in ("trades", "wr", "pf", "exp_r", "net", "dd", "tp_rate", "expiry_rate"):
        d[m] = float(np.mean([x[m] for x in r]))
    return d

if __name__ == "__main__":
    grid = []
    for sm in (0.5, 1.0, 1.5, 2.0, 3.0):
        for mind in (0.0, 10.0, 20.0):
            for pb in (0.0, 2.0):
                grid.append(((("stop_mult", sm), ("min_dist", mind), ("tp_pullback", pb)),
                             dict(stop_mult=sm, min_dist=mind, tp_pullback=pb)))
    for tag, a, b in [("2025-01-01 -> 2026-06-09", "2025-01-01", "2026-12-31"),
                      ("2016-2024 OUT-OF-SAMPLE", "2016-01-01", "2025-01-01")]:
        with Pool(4, initializer=_init, initargs=(a, b)) as pool:
            d = pd.DataFrame(pool.map(_job, grid, chunksize=1))
        d.to_csv(f"results/magnet_{a[:4]}.csv", index=False)
        print(f"\n### MAGNET trade — {tag}   (top 12 by expectancy)")
        print(d.nlargest(12, "exp_r").round(3).to_string(index=False))
