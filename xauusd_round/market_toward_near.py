"""
Test the user's exact rule:

  At 09:00 IST, look at the open. Find the nearer $100 round number.
    - if the nearer level is BELOW  -> go SHORT (toward it)
    - if the nearer level is ABOVE  -> go LONG  (toward it)
  Enter AT THE OPEN of the 09:00 bar (market order, no breakout wait).
  SL: sweep $5 .. $10 fixed dollars.
  TP: 1:2 RR (= 2x the SL distance).
  No other filter, no expiry - position runs until SL or TP is hit.

This is the 'magnet' idea again, but as a MARKET entry (always taken, not
conditional on price reaching a level) instead of a breakout stop order.
"""
import numpy as np, pandas as pd
from dataclasses import dataclass, replace
from multiprocessing import Pool
from engine import load_data
from sweep import CSV


@dataclass
class MK:
    step: float = 100.0
    setup_hour: int = 9
    setup_minute: int = 0
    risk: float = 7.0          # fixed $ stop-loss distance
    rr: float = 2.0
    risk_percent: float = 1.0
    initial_capital: float = 5000.0
    cost_per_unit: float = 0.30
    mc_steps: int = 320
    seed: int = 0


def run(df: pd.DataFrame, p: MK) -> dict:
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
            if long:
                done = (o, "SL") if o <= sl else ((o, "TP") if o >= tp else None)
            else:
                done = (o, "SL") if o >= sl else ((o, "TP") if o <= tp else None)
            if done is None and not (max(sl, tp) < l or min(sl, tp) > h):
                xs = path(o, h, l, c)
                for a, b in zip(xs[:-1], xs[1:]):
                    if a == b:
                        continue
                    lo_, hi_ = (a, b) if b > a else (b, a)
                    cand = []
                    for price, why in ((sl, "SL"), (tp, "TP")):
                        if lo_ <= price <= hi_:
                            cand.append((abs(price - a), price, why))
                    if cand:
                        cand.sort()
                        done = (cand[0][1], cand[0][2]); break
            if done:
                px, why = done
                sgn = 1.0 if long else -1.0
                pnl = (sgn * (px - pos["entry"]) - p.cost_per_unit) * pos["qty"]
                realized += pnl; equity = p.initial_capital + realized
                trades.append(dict(dt=df.dt.iloc[pos["i"]], side=pos["side"],
                                   entry=pos["entry"], exit=px, reason=why,
                                   pnl=pnl, r=pnl / (pos["risk"] * pos["qty"]),
                                   equity=equity, bars=i - pos["i"]))
                pos = None

        if setup[i] and pos is None:
            ref = o
            up_ = np.ceil(ref / p.step) * p.step
            dn_ = np.floor(ref / p.step) * p.step
            if up_ == dn_:
                continue
            long = (up_ - ref) < (ref - dn_)     # nearer level ABOVE -> long
            entry = ref                           # market entry AT THE OPEN
            sl = entry - p.risk if long else entry + p.risk
            tp = entry + p.risk * p.rr if long else entry - p.risk * p.rr
            qty = equity * (p.risk_percent / 100.0) / p.risk
            pos = dict(side="long" if long else "short", entry=entry, sl=sl,
                      tp=tp, qty=qty, risk=p.risk, i=i)
            # same-bar resolution: check gap/path within THIS bar too
            done = None
            if long:
                done = (o, "SL") if o <= sl else ((o, "TP") if o >= tp else None)
            else:
                done = (o, "SL") if o >= sl else ((o, "TP") if o <= tp else None)
            if done is None and not (max(sl, tp) < l or min(sl, tp) > h):
                xs = path(o, h, l, c)
                for a, b in zip(xs[:-1], xs[1:]):
                    if a == b:
                        continue
                    lo_, hi_ = (a, b) if b > a else (b, a)
                    cand = []
                    for price, why in ((sl, "SL"), (tp, "TP")):
                        if lo_ <= price <= hi_:
                            cand.append((abs(price - a), price, why))
                    if cand:
                        cand.sort()
                        done = (cand[0][1], cand[0][2]); break
            if done:
                px, why = done
                sgn = 1.0 if long else -1.0
                pnl = (sgn * (px - pos["entry"]) - p.cost_per_unit) * pos["qty"]
                realized += pnl; equity = p.initial_capital + realized
                trades.append(dict(dt=df.dt.iloc[pos["i"]], side=pos["side"],
                                   entry=pos["entry"], exit=px, reason=why,
                                   pnl=pnl, r=pnl / (pos["risk"] * pos["qty"]),
                                   equity=equity, bars=i - pos["i"]))
                pos = None

    t = pd.DataFrame(trades)
    if len(t) == 0:
        return dict(trades=0, wr=0, pf=float("nan"), exp_r=0, net=0, dd=0, df=t)
    pnl = t.pnl.to_numpy()
    gp, gl = pnl[pnl > 0].sum(), abs(pnl[pnl <= 0].sum())
    eq = np.concatenate([[p.initial_capital], p.initial_capital + np.cumsum(pnl)])
    peak = np.maximum.accumulate(eq)
    return dict(trades=len(t), wr=float((pnl > 0).mean() * 100),
                pf=float(gp / gl) if gl > 0 else float("inf"),
                exp_r=float(t.r.mean()), net=float(pnl.sum()),
                dd=float(((peak - eq) / peak * 100).max()), df=t)


_DF = None
def _init(a, b):
    global _DF
    d = load_data(CSV); _DF = d[(d.dt >= a) & (d.dt < b)].reset_index(drop=True)

def _job(t):
    key, kw, k = t
    r = [run(_DF, replace(MK(), seed=s, mc_steps=k, **kw)) for s in range(6)]
    d = dict(key); d["k"] = k
    for m in ("trades", "wr", "pf", "exp_r", "net", "dd"):
        d[m] = float(np.mean([x[m] for x in r]))
    return d

if __name__ == "__main__":
    grid = [((("risk", r),), dict(risk=r)) for r in (5.0, 6.0, 7.0, 8.0, 9.0, 10.0)]
    RES = [40, 320]
    for tag, a, b in [("2025-01-01 -> 2026-06-09", "2025-01-01", "2026-12-31"),
                      ("2016-2024 OUT-OF-SAMPLE", "2016-01-01", "2025-01-01"),
                      ("FULL 2016-2026", "2016-01-01", "2026-12-31")]:
        jobs = [(k, kw, s) for k, kw in grid for s in RES]
        with Pool(4, initializer=_init, initargs=(a, b)) as pool:
            d = pd.DataFrame(pool.map(_job, jobs, chunksize=1))
        piv = d.pivot(index="risk", columns="k", values="exp_r")
        piv.columns = [f"expR_k{c}" for c in piv.columns]
        fine = d[d.k == 320].set_index("risk")
        piv["trades"] = fine.trades.round(0)
        piv["WR%"] = fine.wr.round(1)
        piv["PF"] = fine.pf.round(3)
        piv["net$"] = fine.net.round(0)
        piv["DD%"] = fine.dd.round(1)
        print(f"\n### {tag}  -  market entry toward nearer $100 level, RR 1:2")
        print(piv.round(3).to_string())
        piv.to_csv(f"results/market_toward_near_{a[:4]}.csv")
