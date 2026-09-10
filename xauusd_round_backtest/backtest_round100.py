"""
XAUUSD $100 Round-Number Strategy - tick-by-tick backtest.

Faithful re-implementation of the Pine v5 strategy
"XAUUSD Round Number | 10S | 100 + 50 Dual Strategy | 1% Risk"
with only the $100 round leg enabled (round100 = true, round50 = false).

Data: real bid/ask tick data, timestamps already in Asia/Kolkata (IST).
"""

import argparse
import csv
import json
import math
import os
from datetime import datetime

# ----------------------------------------------------------------------------
# Strategy inputs (mirroring the Pine `input.*` defaults)
# ----------------------------------------------------------------------------
INITIAL_CAPITAL = 5000.0
RISK_PERCENT    = 1.0
ENTRY_BUFFER    = 3.15
SL_FROM_ROUND   = 2.0
RR              = 2.0
POINT_VALUE     = 1.0
SETUP_HOUR      = 9
SETUP_MINUTE    = 0
ROUND_STEP      = 100.0


def parse_line(line):
    """'2026.03.02 09:00:00.292,5356.125,5355.275,0.00009,0.00018' -> pieces."""
    ts, ask, bid = line.split(',', 3)[:3]
    return ts, float(ask), float(bid)


def sec_of_day(ts):
    h = int(ts[11:13]); m = int(ts[14:16]); s = int(ts[17:19])
    return h * 3600 + m * 60 + s


class Backtest:
    def __init__(self, ref_price='bid', entry_mode='realistic',
                 exit_mode='realistic', roll_exits=True, spread_cost=True):
        # ref_price  : which tick price acts as the 10S bar `open` at 09:00
        # entry_mode : 'realistic' -> longs fill on ask, shorts on bid
        #              'single'    -> both sides use the ref price feed (TV-like)
        # roll_exits : True replicates Pine's re-issuing of strategy.exit with the
        #              *current* day's variables (an overnight position gets its
        #              SL/TP overwritten at the next 09:00 setup).
        self.ref_price   = ref_price
        self.entry_mode  = entry_mode
        self.exit_mode   = exit_mode
        self.roll_exits  = roll_exits
        self.spread_cost = spread_cost

        self.equity_realised = INITIAL_CAPITAL
        self.netprofit = 0.0

        # --- Pine daily state variables (the $100 leg) ---
        self.upper = self.lower = None
        self.buyEntry = self.sellEntry = None
        self.buySL = self.sellSL = None
        self.buyTP = self.sellTP = None
        self.buyQty = self.sellQty = None
        self.setupActive = False
        self.ordersSubmitted = False
        self.tradeTaken = False

        # pending stop orders
        self.pend_buy = False
        self.pend_sell = False

        # open position
        self.pos = None   # dict or None

        self.trades = []
        self.days = []
        self.warnings = []
        self.equity_curve = []
        self.max_equity = INITIAL_CAPITAL
        self.max_dd = 0.0
        self.max_dd_pct = 0.0

    # ------------------------------------------------------------------
    def ref(self, ask, bid):
        if self.ref_price == 'bid':
            return bid
        if self.ref_price == 'ask':
            return ask
        return (ask + bid) / 2.0

    def equity_now(self, ask, bid):
        """strategy.equity == realised equity + open position P&L."""
        eq = self.equity_realised
        if self.pos:
            if self.pos['dir'] == 'long':
                mtm = (bid - self.pos['entry']) * self.pos['qty'] * POINT_VALUE
            else:
                mtm = (self.pos['entry'] - ask) * self.pos['qty'] * POINT_VALUE
            eq += mtm
        return eq

    # ------------------------------------------------------------------
    def do_setup(self, ts, ask, bid, day):
        """09:00 IST daily setup block."""
        # strategy.cancel of any leftover pending orders
        self.pend_buy = False
        self.pend_sell = False

        self.setupActive = False
        self.ordersSubmitted = False
        self.tradeTaken = False

        refOpen = self.ref(ask, bid)

        self.upper = math.ceil(refOpen / ROUND_STEP) * ROUND_STEP
        self.lower = math.floor(refOpen / ROUND_STEP) * ROUND_STEP

        self.buyEntry  = self.upper + ENTRY_BUFFER
        self.sellEntry = self.lower - ENTRY_BUFFER
        self.buySL     = self.upper - SL_FROM_ROUND
        self.sellSL    = self.lower + SL_FROM_ROUND

        buyRisk  = self.buyEntry - self.buySL
        sellRisk = self.sellSL - self.sellEntry

        self.buyTP  = self.buyEntry + buyRisk * RR
        self.sellTP = self.sellEntry - sellRisk * RR

        eq = self.equity_now(ask, bid)
        riskMoney = eq * (RISK_PERCENT / 100.0)
        self.buyQty  = riskMoney / (buyRisk * POINT_VALUE) if buyRisk > 0 else 0.0
        self.sellQty = riskMoney / (sellRisk * POINT_VALUE) if sellRisk > 0 else 0.0

        self.setupActive = True

        if self.upper == self.lower:
            self.warnings.append(
                f"{day}: 09:00 open {refOpen} sits exactly on a $100 round; "
                "upper == lower.")

        self.days.append(dict(
            day=day, setup_ts=ts, ref_open=refOpen, ask=ask, bid=bid,
            spread=round(ask - bid, 3),
            upper=self.upper, lower=self.lower,
            buy_entry=round(self.buyEntry, 3), sell_entry=round(self.sellEntry, 3),
            buy_sl=round(self.buySL, 3), sell_sl=round(self.sellSL, 3),
            buy_tp=round(self.buyTP, 3), sell_tp=round(self.sellTP, 3),
            risk_per_unit=round(buyRisk, 3),
            equity_at_setup=round(eq, 2),
            risk_money=round(riskMoney, 2),
            qty=round(self.buyQty, 4),
            position_open_at_setup=bool(self.pos),
            outcome=None, ))

    # ------------------------------------------------------------------
    def try_submit_orders(self):
        """Pine evaluates this gate on every bar, not only the setup bar."""
        if (self.setupActive and not self.ordersSubmitted
                and not self.tradeTaken and self.pos is None):
            self.pend_buy = True
            self.pend_sell = True
            self.ordersSubmitted = True

    # ------------------------------------------------------------------
    def close_pos(self, ts, price, reason, ask, bid):
        p = self.pos
        if p['dir'] == 'long':
            pnl = (price - p['entry']) * p['qty'] * POINT_VALUE
        else:
            pnl = (p['entry'] - price) * p['qty'] * POINT_VALUE

        self.netprofit += pnl
        self.equity_realised += pnl

        r_mult = pnl / p['risk_money'] if p['risk_money'] else 0.0

        self.trades.append(dict(
            day=p['day'], dir=p['dir'],
            entry_ts=p['ts'], entry=round(p['entry'], 3),
            planned_entry=round(p['planned_entry'], 3),
            entry_slip=round(p['entry'] - p['planned_entry'], 3) if p['dir'] == 'long'
                       else round(p['planned_entry'] - p['entry'], 3),
            sl=round(p['sl'], 3), tp=round(p['tp'], 3),
            qty=round(p['qty'], 4),
            exit_ts=ts, exit=round(price, 3), reason=reason,
            pnl=round(pnl, 2), r=round(r_mult, 3),
            equity_after=round(self.equity_realised, 2),
            hold_sec=self._hold(p['ts'], ts), ))

        self.pos = None
        self._track_dd()

    def _hold(self, a, b):
        fmt = "%Y.%m.%d %H:%M:%S.%f"
        return round((datetime.strptime(b, fmt) - datetime.strptime(a, fmt)).total_seconds(), 1)

    def _track_dd(self):
        eq = self.equity_realised
        self.equity_curve.append(eq)
        if eq > self.max_equity:
            self.max_equity = eq
        dd = self.max_equity - eq
        if dd > self.max_dd:
            self.max_dd = dd
            self.max_dd_pct = dd / self.max_equity * 100.0

    # ------------------------------------------------------------------
    def run(self, path):
        cur_day = None
        setup_done_today = False

        with open(path, 'r', buffering=1 << 22) as fh:
            fh.readline()  # header
            for line in fh:
                if not line or line[0] == 'T':
                    continue
                ts, ask, bid = parse_line(line)
                day = ts[:10]
                sod = sec_of_day(ts)

                if day != cur_day:
                    cur_day = day
                    setup_done_today = False

                # ---- 09:00 IST daily setup -------------------------------
                if (not setup_done_today
                        and sod >= SETUP_HOUR * 3600 + SETUP_MINUTE * 60):
                    setup_done_today = True
                    self.do_setup(ts, ask, bid, day)

                # ---- order submission gate (evaluated every bar) ---------
                self.try_submit_orders()

                # ---- exits first -----------------------------------------
                if self.pos is not None:
                    p = self.pos
                    # Pine re-issues strategy.exit each bar with the CURRENT
                    # day's variables -> an overnight trade inherits new levels.
                    if self.roll_exits:
                        if p['dir'] == 'long':
                            p['sl'], p['tp'] = self.buySL, self.buyTP
                        else:
                            p['sl'], p['tp'] = self.sellSL, self.sellTP

                    if p['dir'] == 'long':
                        exit_px = bid if self.exit_mode == 'realistic' else self.ref(ask, bid)
                        if exit_px <= p['sl']:
                            self.close_pos(ts, exit_px, 'SL', ask, bid)
                        elif exit_px >= p['tp']:
                            # limit order -> fills at the limit price
                            self.close_pos(ts, p['tp'], 'TP', ask, bid)
                    else:
                        exit_px = ask if self.exit_mode == 'realistic' else self.ref(ask, bid)
                        if exit_px >= p['sl']:
                            self.close_pos(ts, exit_px, 'SL', ask, bid)
                        elif exit_px <= p['tp']:
                            self.close_pos(ts, p['tp'], 'TP', ask, bid)

                # ---- entries ---------------------------------------------
                if self.pos is None and (self.pend_buy or self.pend_sell):
                    buy_px  = ask if self.entry_mode == 'realistic' else self.ref(ask, bid)
                    sell_px = bid if self.entry_mode == 'realistic' else self.ref(ask, bid)

                    hit_buy  = self.pend_buy  and buy_px  >= self.buyEntry
                    hit_sell = self.pend_sell and sell_px <= self.sellEntry

                    if hit_buy and hit_sell:
                        self.warnings.append(
                            f"{day} {ts}: both stops triggered on one tick "
                            f"(ask={ask} bid={bid}); took the nearer one.")
                        if (buy_px - self.buyEntry) >= (self.sellEntry - sell_px):
                            hit_sell = False
                        else:
                            hit_buy = False

                    if hit_buy:
                        self.pos = dict(dir='long', ts=ts, entry=buy_px,
                                        planned_entry=self.buyEntry,
                                        sl=self.buySL, tp=self.buyTP,
                                        qty=self.buyQty, day=day,
                                        risk_money=self.buyQty * (self.buyEntry - self.buySL))
                        self.tradeTaken = True
                        self.pend_buy = False
                        self.pend_sell = False        # OCA cancel
                        for d in self.days:
                            if d['day'] == day:
                                d['outcome'] = 'LONG'
                    elif hit_sell:
                        self.pos = dict(dir='short', ts=ts, entry=sell_px,
                                        planned_entry=self.sellEntry,
                                        sl=self.sellSL, tp=self.sellTP,
                                        qty=self.sellQty, day=day,
                                        risk_money=self.sellQty * (self.sellSL - self.sellEntry))
                        self.tradeTaken = True
                        self.pend_sell = False
                        self.pend_buy = False         # OCA cancel
                        for d in self.days:
                            if d['day'] == day:
                                d['outcome'] = 'SHORT'

        # end of data
        self.last_ts, self.last_ask, self.last_bid = ts, ask, bid
        for d in self.days:
            if d['outcome'] is None:
                d['outcome'] = 'NO TRADE'
        return self


def summarise(bt):
    tr = bt.trades
    wins = [t for t in tr if t['pnl'] > 0]
    losses = [t for t in tr if t['pnl'] <= 0]
    gp = sum(t['pnl'] for t in wins)
    gl = abs(sum(t['pnl'] for t in losses))
    n = len(tr)
    return dict(
        trades=n,
        wins=len(wins), losses=len(losses),
        win_rate=round(len(wins) / n * 100, 2) if n else 0.0,
        gross_profit=round(gp, 2), gross_loss=round(gl, 2),
        profit_factor=round(gp / gl, 3) if gl else None,
        net_profit=round(bt.netprofit, 2),
        net_pct=round(bt.netprofit / INITIAL_CAPITAL * 100, 2),
        final_equity=round(bt.equity_realised, 2),
        max_drawdown=round(bt.max_dd, 2),
        max_drawdown_pct=round(bt.max_dd_pct, 2),
        avg_win=round(gp / len(wins), 2) if wins else 0.0,
        avg_loss=round(gl / len(losses), 2) if losses else 0.0,
        expectancy_R=round(sum(t['r'] for t in tr) / n, 3) if n else 0.0,
        tp_hits=sum(1 for t in tr if t['reason'] == 'TP'),
        sl_hits=sum(1 for t in tr if t['reason'] == 'SL'),
        open_at_end=bool(bt.pos),
    )


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('csv')
    ap.add_argument('--ref', default='bid', choices=['bid', 'ask', 'mid'])
    ap.add_argument('--entry', default='realistic', choices=['realistic', 'single'])
    ap.add_argument('--exit', dest='exitm', default='realistic', choices=['realistic', 'single'])
    ap.add_argument('--no-roll-exits', action='store_true')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    bt = Backtest(ref_price=a.ref, entry_mode=a.entry, exit_mode=a.exitm,
                  roll_exits=not a.no_roll_exits).run(a.csv)
    s = summarise(bt)

    print(json.dumps(dict(config=dict(ref=a.ref, entry=a.entry, exit=a.exitm,
                                      roll_exits=not a.no_roll_exits),
                          summary=s, warnings=bt.warnings), indent=2))

    if a.out:
        os.makedirs(a.out, exist_ok=True)
        with open(os.path.join(a.out, 'trades.csv'), 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(bt.trades[0].keys()))
            w.writeheader(); w.writerows(bt.trades)
        with open(os.path.join(a.out, 'daily_setups.csv'), 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(bt.days[0].keys()))
            w.writeheader(); w.writerows(bt.days)
        with open(os.path.join(a.out, 'summary.json'), 'w') as f:
            json.dump(dict(summary=s, warnings=bt.warnings), f, indent=2)
