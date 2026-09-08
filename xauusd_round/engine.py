"""
XAUUSD Round Number Dual Strategy ($100 + $50) - Python backtest engine.

Replicates the Pine v5 strategy "XAUUSD Round Number | 10S | 100 + 50 Dual
Strategy | 1% Risk":

  - At a chosen setup time (IST) read the OPEN of that 15-min bar (`ref`).
  - $100 mode: upper = ceil(ref/100)*100 , lower = floor(ref/100)*100
  - $50  mode: upper = ceil(ref/50)*50   , lower = floor(ref/50)*50
  - BUY  stop = upper + entry_buffer , SL = upper - sl_from_round
  - SELL stop = lower - entry_buffer , SL = lower + sl_from_round
    => risk distance is always (entry_buffer + sl_from_round), both sides
  - TP = entry +/- risk_distance * rr
  - qty = equity * risk_pct/100 / (risk_distance * point_value)
  - BUY/SELL of one round are an OCA pair: one fills -> the other is cancelled
  - Pine only submits while flat (strategy.position_size == 0)
  - Pending orders are cancelled and levels recomputed at the next setup time

Pine execution model reproduced: the script body runs at the CLOSE of a bar,
so orders it places are live from the NEXT bar (process_orders_on_close=false).

INTRABAR RESOLUTION
-------------------
With a $5.15 stop on 15-min gold bars, whether SL or TP is hit first inside a
single bar decides most trades. Three policies are supported:

  'path'         (default) - reconstruct a plausible intrabar path from OHLC:
                 up bar (c>=o) travels o -> l -> h -> c
                 down bar (c<o) travels o -> h -> l -> c
                 Every fill/exit is then resolved in true travel order.
  'mc'           - Monte-Carlo: a random walk constrained to the bar's real
                 O/H/L/C, so price oscillates inside the bar the way it
                 actually does. This is the primary realistic estimate.
  'pessimistic'  - whenever a bar touches both SL and TP, assume SL.
  'optimistic'   - whenever a bar touches both, assume TP.

'path' is the realistic estimate; the other two bracket it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# Parameters
# ----------------------------------------------------------------------------
@dataclass
class Params:
    risk_percent: float = 1.0
    entry_buffer: float = 3.15
    sl_from_round: float = 2.0
    rr: float = 2.0
    round100: bool = True
    round50: bool = True
    setup_hour: int = 9
    setup_minute: int = 0
    point_value: float = 1.0
    initial_capital: float = 5000.0
    # --- realism knobs (not present in the Pine script) ---
    cost_per_unit: float = 0.0      # round-trip $/unit (spread + commission)
    intrabar: str = "path"          # 'path' | 'pessimistic' | 'optimistic'
    compound: bool = True           # size off live equity vs fixed capital
    direction: str = "both"         # 'both' | 'long' | 'short'
    dedupe_levels: bool = False     # skip $50 order when identical to $100
    mc_steps: int = 60              # intrabar sub-steps for the MC model
    seed: int = 0                   # MC seed
    expiry_bars: int = 0            # 0 = live until next setup time
    risk_cap_pct: float = 0.0       # 0 = no cap on qty
    grid_offset: float = 0.0        # CONTROL: shift the grid off round numbers

    def label(self) -> str:
        modes = "+".join([m for m, on in (("100", self.round100),
                                          ("50", self.round50)) if on]) or "none"
        return (f"{self.setup_hour:02d}:{self.setup_minute:02d} "
                f"buf={self.entry_buffer} sl={self.sl_from_round} rr={self.rr} "
                f"[${modes}] {self.direction}")


def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    df["dt"] = pd.to_datetime(df[df.columns[0]], format="%Y.%m.%d %H:%M:%S")
    df = df.rename(columns={"Open": "o", "High": "h", "Low": "l", "Close": "c"})
    return (df[["dt", "o", "h", "l", "c"]].dropna()
              .sort_values("dt").reset_index(drop=True))


class _Order:
    __slots__ = ("tag", "group", "side", "stop", "sl", "tp", "qty",
                 "live_from", "expire_at")

    def __init__(self, tag, group, side, stop, sl, tp, qty, live_from, expire_at):
        self.tag, self.group, self.side = tag, group, side
        self.stop, self.sl, self.tp, self.qty = stop, sl, tp, qty
        self.live_from, self.expire_at = live_from, expire_at


class _Trade:
    __slots__ = ("tag", "group", "side", "qty", "entry_px", "sl", "tp",
                 "entry_i", "risk_dist")

    def __init__(self, tag, group, side, qty, entry_px, sl, tp, entry_i, risk):
        self.tag, self.group, self.side, self.qty = tag, group, side, qty
        self.entry_px, self.sl, self.tp = entry_px, sl, tp
        self.entry_i, self.risk_dist = entry_i, risk


def backtest(df: pd.DataFrame, p: Params) -> dict:
    dt = df["dt"].to_numpy()
    O = df["o"].to_numpy(np.float64)
    H = df["h"].to_numpy(np.float64)
    L = df["l"].to_numpy(np.float64)
    C = df["c"].to_numpy(np.float64)
    hh = df["dt"].dt.hour.to_numpy(np.int16)
    mm = df["dt"].dt.minute.to_numpy(np.int16)
    is_setup = (hh == p.setup_hour) & (mm == p.setup_minute)

    n = len(df)
    risk_dist = p.entry_buffer + p.sl_from_round
    tp_dist = risk_dist * p.rr
    mode = p.intrabar

    equity = p.initial_capital
    realized = 0.0

    pending: list[_Order] = []
    open_trades: list[_Trade] = []
    trades: list[dict] = []

    st = {k: dict(active=False, submitted=False, taken=False, qty=0.0,
                  buy_e=np.nan, sell_e=np.nan, buy_sl=np.nan, sell_sl=np.nan,
                  buy_tp=np.nan, sell_tp=np.nan, upper=np.nan, lower=np.nan)
          for k in (100, 50)}

    def close_trade(t: _Trade, i: int, px: float, reason: str):
        nonlocal realized, equity
        sgn = 1.0 if t.side == "long" else -1.0
        pnl = (sgn * (px - t.entry_px) - p.cost_per_unit) * t.qty * p.point_value
        realized += pnl
        equity = p.initial_capital + realized
        trades.append(dict(
            tag=t.tag, group=t.group, side=t.side,
            entry_time=dt[t.entry_i], exit_time=dt[i],
            entry=t.entry_px, exit=px, sl=t.sl, tp=t.tp, qty=t.qty,
            reason=reason, pnl=pnl, equity=equity,
            r=pnl / (t.risk_dist * t.qty * p.point_value) if t.qty > 0 else 0.0,
            bars_held=i - t.entry_i))

    def open_from(od: _Order, px: float, i: int) -> _Trade:
        exact = abs(px - od.stop) < 1e-9
        if od.side == "long":
            sl = od.sl if exact else px - risk_dist
            tp = od.tp if exact else px + tp_dist
        else:
            sl = od.sl if exact else px + risk_dist
            tp = od.tp if exact else px - tp_dist
        st[od.group]["taken"] = True
        return _Trade(od.tag, od.group, od.side, od.qty, px, sl, tp, i, risk_dist)

    # ---- simple (non-path) exit test, used by the bracketing policies -------
    def simple_exit(t: _Trade, i: int, gap_ok: bool):
        o, h, l = O[i], H[i], L[i]
        if t.side == "long":
            if gap_ok and o <= t.sl:
                return o, "SL"
            if gap_ok and o >= t.tp:
                return o, "TP"
            sl_hit, tp_hit = l <= t.sl, h >= t.tp
        else:
            if gap_ok and o >= t.sl:
                return o, "SL"
            if gap_ok and o <= t.tp:
                return o, "TP"
            sl_hit, tp_hit = h >= t.sl, l <= t.tp
        if sl_hit and tp_hit:
            return (t.sl, "SL") if mode == "pessimistic" else (t.tp, "TP")
        if sl_hit:
            return t.sl, "SL"
        if tp_hit:
            return t.tp, "TP"
        return None

    rng = np.random.default_rng(p.seed)
    K = max(4, p.mc_steps)
    _tgrid = np.arange(K + 1) / K

    def mc_path(o, h, l, c):
        """Random walk with o/c endpoints, rescaled so its range == h-l and
        its extremes land exactly on h and l."""
        w = np.concatenate([[0.0], np.cumsum(rng.standard_normal(K))])
        bridge = w - _tgrid * w[-1]
        x = o + (c - o) * _tgrid + bridge
        span = x.max() - x.min()
        target = h - l
        if span > 1e-12 and target > 1e-12:
            s = target / span
            x = o + (c - o) * _tgrid + bridge * s
        x[x.argmax()] = h
        x[x.argmin()] = l
        return x

    for i in range(n):
        o, h, l, c = O[i], H[i], L[i], C[i]

        # ---- fast skip: nothing can trigger inside this bar ----------------
        if open_trades or pending:
            lo_t, hi_t = np.inf, -np.inf
            for t in open_trades:
                lo_t = min(lo_t, t.sl, t.tp); hi_t = max(hi_t, t.sl, t.tp)
            for od in pending:
                if od.live_from <= i:
                    lo_t = min(lo_t, od.stop); hi_t = max(hi_t, od.stop)
            touched = not (hi_t < l or lo_t > h)
        else:
            touched = False

        if touched and mode not in ("path", "mc"):
            # ---------------- bracketing policies -------------------------
            still = []
            for t in open_trades:
                r = simple_exit(t, i, gap_ok=True)
                if r:
                    close_trade(t, i, r[0], r[1])
                else:
                    still.append(t)
            open_trades = still
            filled = set()
            rest = []
            for od in pending:
                if od.live_from > i:
                    rest.append(od); continue
                if od.group in filled:
                    continue
                px = None
                if od.side == "long":
                    px = o if o >= od.stop else (od.stop if h >= od.stop else None)
                else:
                    px = o if o <= od.stop else (od.stop if l <= od.stop else None)
                if px is None:
                    rest.append(od); continue
                filled.add(od.group)
                t = open_from(od, px, i)
                r = simple_exit(t, i, gap_ok=False)
                if r:
                    close_trade(t, i, r[0], r[1])
                else:
                    open_trades.append(t)
            pending = [x for x in rest if x.group not in filled]

        elif touched:
            # ---------------- realistic intrabar path ---------------------
            # 1) gaps at the bar open, before any intrabar travel
            still = []
            for t in open_trades:
                if t.side == "long":
                    r = (o, "SL") if o <= t.sl else ((o, "TP") if o >= t.tp else None)
                else:
                    r = (o, "SL") if o >= t.sl else ((o, "TP") if o <= t.tp else None)
                if r:
                    close_trade(t, i, r[0], r[1])
                else:
                    still.append(t)
            open_trades = still

            filled = set()
            rest = []
            for od in pending:
                if od.live_from > i:
                    rest.append(od); continue
                gapped = (od.side == "long" and o >= od.stop) or \
                         (od.side == "short" and o <= od.stop)
                if gapped and od.group not in filled:
                    filled.add(od.group)
                    t_new = open_from(od, o, i)
                    open_trades.append(t_new)
                    lo_t = min(lo_t, t_new.sl, t_new.tp)
                    hi_t = max(hi_t, t_new.sl, t_new.tp)
                else:
                    rest.append(od)
            pending = [x for x in rest if x.group not in filled]

            # 2) walk the reconstructed path leg by leg
            if mode == "mc":
                x = mc_path(o, h, l, c)
                legs = zip(x[:-1], x[1:])
            else:
                legs = ((o, l), (l, h), (h, c)) if c >= o else \
                       ((o, h), (h, l), (l, c))
            for a, b in legs:
                if a == b:
                    continue
                if (min(a, b) > hi_t) or (max(a, b) < lo_t):
                    continue
                up = b > a
                cur = a
                while True:
                    best_d, best = np.inf, None
                    for t in open_trades:
                        for price, reason in ((t.sl, "SL"), (t.tp, "TP")):
                            ok = (cur <= price <= b) if up else (b <= price <= cur)
                            if ok:
                                d = abs(price - cur)
                                if d < best_d:
                                    best_d, best = d, ("exit", t, price, reason)
                    for od in pending:
                        if od.live_from > i:
                            continue
                        ok = (cur <= od.stop <= b) if up else (b <= od.stop <= cur)
                        if ok:
                            d = abs(od.stop - cur)
                            if d < best_d:
                                best_d, best = d, ("entry", od, od.stop, "")
                    if best is None:
                        break
                    kind, obj, price, reason = best
                    if kind == "exit":
                        close_trade(obj, i, price, reason)
                        open_trades.remove(obj)
                    else:
                        grp = obj.group
                        t_new = open_from(obj, price, i)
                        open_trades.append(t_new)
                        pending = [x for x in pending if x.group != grp]
                        # the new bracket may sit outside the old trigger range;
                        # widen the skip bounds or later legs would be skipped
                        lo_t = min(lo_t, t_new.sl, t_new.tp)
                        hi_t = max(hi_t, t_new.sl, t_new.tp)
                    cur = price

        # ---- expiry of stale pending orders -------------------------------
        if p.expiry_bars > 0 and pending:
            pending = [x for x in pending if x.expire_at > i]

        # ================= Pine script body (runs at bar close) =============
        if is_setup[i]:
            pending = []                                    # strategy.cancel x4
            ref = o
            base = equity if p.compound else p.initial_capital
            qty = (base * (p.risk_percent / 100.0)) / (risk_dist * p.point_value)
            if p.risk_cap_pct > 0:
                qty = min(qty, base * p.risk_cap_pct / ref)
            for step, enabled in ((100, p.round100), (50, p.round50)):
                s = st[step]
                s["submitted"] = s["taken"] = False
                s["active"] = bool(enabled)
                g = p.grid_offset
                up_ = math.ceil((ref - g) / step) * step + g
                lo_ = math.floor((ref - g) / step) * step + g
                if up_ == lo_:
                    up_, lo_ = ref + step, ref - step
                s.update(upper=up_, lower=lo_, qty=qty,
                         buy_e=up_ + p.entry_buffer,
                         sell_e=lo_ - p.entry_buffer,
                         buy_sl=up_ - p.sl_from_round,
                         sell_sl=lo_ + p.sl_from_round)
                s["buy_tp"] = s["buy_e"] + tp_dist
                s["sell_tp"] = s["sell_e"] - tp_dist

        # order submission - evaluated on every bar, exactly like Pine
        if not open_trades:
            for step in (100, 50):
                s = st[step]
                if not (s["active"] and not s["submitted"] and not s["taken"]):
                    continue
                if step == 50 and p.dedupe_levels and p.round100 and st[100]["active"]:
                    if (abs(s["buy_e"] - st[100]["buy_e"]) < 1e-9 and
                            abs(s["sell_e"] - st[100]["sell_e"]) < 1e-9):
                        s["submitted"] = True
                        continue
                exp = i + 1 + p.expiry_bars if p.expiry_bars > 0 else 10**9
                if p.direction in ("both", "long"):
                    pending.append(_Order(f"BUY{step}", step, "long", s["buy_e"],
                                          s["buy_sl"], s["buy_tp"], s["qty"],
                                          i + 1, exp))
                if p.direction in ("both", "short"):
                    pending.append(_Order(f"SELL{step}", step, "short", s["sell_e"],
                                          s["sell_sl"], s["sell_tp"], s["qty"],
                                          i + 1, exp))
                s["submitted"] = True

    return dict(trades=pd.DataFrame(trades), params=p,
                final_equity=p.initial_capital + realized)


def stats(res: dict) -> dict:
    t, p = res["trades"], res["params"]
    cap = p.initial_capital
    if len(t) == 0:
        return dict(trades=0, wins=0, losses=0, win_rate=0.0, pf=float("nan"),
                    net=0.0, final_equity=cap, max_dd_pct=0.0, expectancy_r=0.0,
                    ret_pct=0.0, max_loss_streak=0, tp=0, sl=0, avg_bars=0.0)
    pnl = t["pnl"].to_numpy()
    gp = pnl[pnl > 0].sum()
    gl = abs(pnl[pnl <= 0].sum())
    eq = np.concatenate([[cap], cap + np.cumsum(pnl)])
    peak = np.maximum.accumulate(eq)
    streak = best = 0
    for x in pnl:
        streak = streak + 1 if x <= 0 else 0
        best = max(best, streak)
    return dict(
        trades=len(t), wins=int((pnl > 0).sum()), losses=int((pnl <= 0).sum()),
        win_rate=float((pnl > 0).mean() * 100.0),
        pf=float(gp / gl) if gl > 0 else float("inf"),
        net=float(pnl.sum()), final_equity=float(cap + pnl.sum()),
        max_dd_pct=float((np.where(peak > 0, (peak - eq) / peak, 0) * 100).max()),
        expectancy_r=float(t["r"].mean()),
        ret_pct=float(pnl.sum() / cap * 100.0),
        max_loss_streak=best,
        tp=int((t["reason"] == "TP").sum()), sl=int((t["reason"] == "SL").sum()),
        avg_bars=float(t["bars_held"].mean()))
