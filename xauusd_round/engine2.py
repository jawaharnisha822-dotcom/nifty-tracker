"""
XAUUSD Round-Number Breakout - CORRECTED strategy engine (v2).

Fixes the defects found in the original Pine script (see BUGS.md):

  B1  Global OCA. The original made BUY/SELL an OCA pair *within* each round
      set, so a $100 trade and a $50 trade could be open simultaneously - 2%
      risk instead of 1%, and sometimes long+short at the same time. v2 keeps
      exactly one position at a time.
  B2  Level collision. When the reference open sits in the upper half of a
      $100 block, ceil(o/50)*50 == ceil(o/100)*100: the $100 and $50 orders
      are the SAME price, so the script doubled up on one signal. v2 uses a
      single round grid.
  B3  Deferred submission. Pine gates order entry on position_size == 0, so if
      yesterday's trade was still open at setup time, today's orders were
      placed at some arbitrary later moment using stale 09:00 levels. v2
      submits only in the setup window, or not at all.
  B4  No expiry. A 09:00 order could still trigger 18 hours later. v2 expires
      pending orders after `valid_bars`.
  B5  Gap risk. SL/TP were hard-coded to the round number, so a gap fill made
      the real risk larger than the 1% the size was computed for. v2 re-anchors
      the bracket to the actual fill and rejects fills worse than `max_slip`.
  B6  Fill detection. `opentrades.entry_id(opentrades-1)` misidentifies which
      order filled when two fill on the same bar, so the opposite pending
      order was never cancelled. Not applicable under global OCA.
  B7  Sizing off `strategy.equity` (which includes open P&L) made position size
      depend on another trade's floating P&L. v2 sizes off closed equity.
  B8  A fixed $5.15 risk distance is *inside* the intrabar noise band of
      2025-26 gold. v2 supports an ATR-scaled stop so risk tracks volatility.

Uses the same Monte-Carlo intrabar model as engine.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class P2:
    risk_percent: float = 1.0
    round_step: float = 100.0        # single grid: 100 / 50 / 25
    entry_buffer: float = 3.15
    sl_mode: str = "fixed"           # 'fixed' | 'atr'
    sl_from_round: float = 2.0       # fixed mode: SL = round -/+ this
    atr_mult: float = 1.0            # atr mode: risk_dist = atr_mult * ATR
    atr_len: int = 14
    min_risk: float = 0.0            # floor on the risk distance
    rr: float = 2.0
    setup_hour: int = 9
    setup_minute: int = 0
    valid_bars: int = 48             # order lifetime (48 x 15m = 12h)
    max_slip: float = 1.0            # reject a fill this far past the stop
    breakeven_at_r: float = 0.0      # 0 = off
    direction: str = "both"
    point_value: float = 1.0
    initial_capital: float = 5000.0
    cost_per_unit: float = 0.30
    mc_steps: int = 120
    seed: int = 0
    compound: bool = True
    skip_monday: bool = False
    side_select: str = "both"       # 'both' | 'nearer' | 'farther'
                                    # which round level to trade, by its
                                    # distance from the setup open

    def label(self):
        sl = (f"sl={self.sl_from_round}" if self.sl_mode == "fixed"
              else f"atr x{self.atr_mult}")
        return (f"${self.round_step:.0f}grid {self.setup_hour:02d}:"
                f"{self.setup_minute:02d} buf={self.entry_buffer} {sl} "
                f"rr={self.rr} valid={self.valid_bars}b {self.direction}")


def atr(df: pd.DataFrame, length: int) -> np.ndarray:
    h, l, c = df.h.to_numpy(), df.l.to_numpy(), df.c.to_numpy()
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1.0 / length, adjust=False).mean().to_numpy()


def backtest2(df: pd.DataFrame, p: P2) -> dict:
    dt = df.dt.to_numpy()
    O, H, L, C = (df[k].to_numpy(np.float64) for k in "ohlc")
    A = atr(df, p.atr_len)
    hh = df.dt.dt.hour.to_numpy(np.int16)
    mm = df.dt.dt.minute.to_numpy(np.int16)
    dow = df.dt.dt.dayofweek.to_numpy(np.int16)
    is_setup = (hh == p.setup_hour) & (mm == p.setup_minute)
    if p.skip_monday:
        is_setup &= (dow != 0)

    n = len(df)
    rng = np.random.default_rng(p.seed)
    K = max(4, p.mc_steps)
    tg = np.arange(K + 1) / K

    def mc_path(o, h, l, c):
        w = np.concatenate([[0.0], np.cumsum(rng.standard_normal(K))])
        br = w - tg * w[-1]
        x = o + (c - o) * tg + br
        span = x.max() - x.min()
        if span > 1e-12 and (h - l) > 1e-12:
            x = o + (c - o) * tg + br * ((h - l) / span)
        x[x.argmax()] = h
        x[x.argmin()] = l
        return x

    equity = p.initial_capital
    realized = 0.0
    trades = []
    pend = []          # list of dicts: side, stop, risk, qty, expire
    pos = None         # dict: side, qty, entry, sl, tp, i, risk, be_done

    def do_close(px, i, reason):
        nonlocal pos, realized, equity
        sgn = 1.0 if pos["side"] == "long" else -1.0
        pnl = (sgn * (px - pos["entry"]) - p.cost_per_unit) * pos["qty"] * p.point_value
        realized += pnl
        equity = p.initial_capital + realized
        trades.append(dict(side=pos["side"], entry_time=dt[pos["i"]], exit_time=dt[i],
                           entry=pos["entry"], exit=px, qty=pos["qty"], reason=reason,
                           pnl=pnl, r=pnl / (pos["risk"] * pos["qty"] * p.point_value),
                           equity=equity, bars_held=i - pos["i"]))
        pos = None

    def do_fill(od, px, i):
        """B5: re-anchor the bracket to the ACTUAL fill, so risk stays 1%."""
        nonlocal pos
        risk = od["risk"]
        if od["side"] == "long":
            sl, tp = px - risk, px + risk * p.rr
        else:
            sl, tp = px + risk, px - risk * p.rr
        pos = dict(side=od["side"], qty=od["qty"], entry=px, sl=sl, tp=tp,
                   i=i, risk=risk, be_done=False)
        return sl, tp

    for i in range(n):
        o, h, l, c = O[i], H[i], L[i], C[i]

        # ---------- does anything sit inside this bar? ----------
        lo_t, hi_t = np.inf, -np.inf
        if pos:
            lo_t = min(lo_t, pos["sl"], pos["tp"]); hi_t = max(hi_t, pos["sl"], pos["tp"])
        for od in pend:
            if od["live"] <= i:
                lo_t = min(lo_t, od["stop"]); hi_t = max(hi_t, od["stop"])

        if hi_t >= l and lo_t <= h:
            # ---- gaps at the open, before intrabar travel ----
            if pos:
                if pos["side"] == "long":
                    r = (o, "SL") if o <= pos["sl"] else ((o, "TP") if o >= pos["tp"] else None)
                else:
                    r = (o, "SL") if o >= pos["sl"] else ((o, "TP") if o <= pos["tp"] else None)
                if r:
                    do_close(r[0], i, r[1])
            if pos is None:
                for od in list(pend):
                    if od["live"] > i:
                        continue
                    gap = (od["side"] == "long" and o >= od["stop"]) or \
                          (od["side"] == "short" and o <= od["stop"])
                    if not gap:
                        continue
                    # B5: reject a fill too far past the trigger
                    if abs(o - od["stop"]) <= p.max_slip:
                        _sl, _tp = do_fill(od, o, i)
                        lo_t = min(lo_t, _sl, _tp); hi_t = max(hi_t, _sl, _tp)
                    # a trigger that gapped past max_slip is treated as fired
                    # but unfilled: both sides of the OCA pair are pulled.
                    pend = []                       # B1: global OCA
                    break

            # ---- walk the reconstructed intrabar path ----
            x = mc_path(o, h, l, c)
            for a, b in zip(x[:-1], x[1:]):
                if a == b or min(a, b) > hi_t or max(a, b) < lo_t:
                    continue
                up = b > a
                cur = a
                while True:
                    bd, best = np.inf, None
                    if pos:
                        for price, reason in ((pos["sl"], "SL"), (pos["tp"], "TP")):
                            if (cur <= price <= b) if up else (b <= price <= cur):
                                d = abs(price - cur)
                                if d < bd:
                                    bd, best = d, ("x", None, price, reason)
                    else:
                        for od in pend:
                            if od["live"] > i:
                                continue
                            if (cur <= od["stop"] <= b) if up else (b <= od["stop"] <= cur):
                                d = abs(od["stop"] - cur)
                                if d < bd:
                                    bd, best = d, ("e", od, od["stop"], "")
                    if best is None:
                        break
                    kind, od, price, reason = best
                    if kind == "x":
                        do_close(price, i, reason)
                    else:
                        _sl, _tp = do_fill(od, price, i)
                        lo_t = min(lo_t, _sl, _tp); hi_t = max(hi_t, _sl, _tp)
                        pend = []                   # B1: global OCA
                    cur = price
                # breakeven stop - measured against the leg endpoint, which is
                # the furthest price reached on this leg
                if pos and p.breakeven_at_r > 0 and not pos["be_done"]:
                    mv = (b - pos["entry"]) if pos["side"] == "long" else (pos["entry"] - b)
                    if mv >= p.breakeven_at_r * pos["risk"]:
                        pos["sl"] = pos["entry"]
                        pos["be_done"] = True
                        lo_t = min(lo_t, pos["sl"]); hi_t = max(hi_t, pos["sl"])

        # ---------- B4: expiry ----------
        if pend:
            pend = [od for od in pend if od["expire"] > i]

        # ---------- setup (script body, at bar close) ----------
        if is_setup[i]:
            pend = []
            ref = o
            risk = (p.entry_buffer + p.sl_from_round if p.sl_mode == "fixed"
                    else p.atr_mult * A[i])
            risk = max(risk, p.min_risk)
            if risk > 0 and pos is None:            # B3: submit only at setup
                base = equity if p.compound else p.initial_capital
                qty = base * (p.risk_percent / 100.0) / (risk * p.point_value)
                step = p.round_step
                up_ = math.ceil(ref / step) * step
                lo_ = math.floor(ref / step) * step
                if up_ == lo_:                      # exactly on the round number
                    up_, lo_ = ref + step, ref - step
                # which side is nearer to the setup open?
                near = "long" if (up_ - ref) < (ref - lo_) else "short"
                far = "short" if near == "long" else "long"
                allow = {"both": {"long", "short"},
                         "nearer": {near}, "farther": {far}}[p.side_select]
                if p.direction in ("both", "long") and "long" in allow:
                    pend.append(dict(side="long", stop=up_ + p.entry_buffer, risk=risk,
                                     qty=qty, live=i + 1, expire=i + 1 + p.valid_bars))
                if p.direction in ("both", "short") and "short" in allow:
                    pend.append(dict(side="short", stop=lo_ - p.entry_buffer, risk=risk,
                                     qty=qty, live=i + 1, expire=i + 1 + p.valid_bars))

    return dict(trades=pd.DataFrame(trades), params=p,
                final_equity=p.initial_capital + realized)


def stats2(res: dict) -> dict:
    t, p = res["trades"], res["params"]
    cap = p.initial_capital
    if len(t) == 0:
        return dict(trades=0, win_rate=0.0, pf=float("nan"), net=0.0,
                    final_equity=cap, max_dd_pct=0.0, expectancy_r=0.0,
                    ret_pct=0.0, max_loss_streak=0, avg_bars=0.0)
    pnl = t.pnl.to_numpy()
    gp, gl = pnl[pnl > 0].sum(), abs(pnl[pnl <= 0].sum())
    eq = np.concatenate([[cap], cap + np.cumsum(pnl)])
    peak = np.maximum.accumulate(eq)
    streak = best = 0
    for x in pnl:
        streak = streak + 1 if x <= 0 else 0
        best = max(best, streak)
    return dict(
        trades=len(t), win_rate=float((pnl > 0).mean() * 100),
        pf=float(gp / gl) if gl > 0 else float("inf"),
        net=float(pnl.sum()), final_equity=float(cap + pnl.sum()),
        max_dd_pct=float((np.where(peak > 0, (peak - eq) / peak, 0) * 100).max()),
        expectancy_r=float(t.r.mean()), ret_pct=float(pnl.sum() / cap * 100),
        max_loss_streak=best, avg_bars=float(t.bars_held.mean()))
