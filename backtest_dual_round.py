"""
Dual round-number strategy: Round=50 AND Round=100 grids trading the same
$5000 account simultaneously.

Each grid (50 and 100) manages its own independent buy/sell OCA pair (only
whichever direction triggers first is taken, the opposite side is
cancelled) - same as the single-grid strategy. But since every multiple of
100 is also a multiple of 50, the two grids' upper/lower round levels can
coincide on a given day (e.g. ref_open puts both grids' upper level at
4500). When that happens the two grids would place the *identical* stop
order (same price, same direction, same SL/TP since buffer/SL/RR are
shared) - this is de-duplicated into a single order so it can only ever
fire once (not twice, which would silently double the day's risk). Firing
a shared order cancels the OCA partner in *both* grids.

On a day where the grids' levels differ, each grid's own order can fire
independently, so up to 2 trades can happen that day (one per grid).

Usage:
    python backtest_dual_round.py path/to/data.csv
"""

import argparse
import math

import pandas as pd


def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    time_col = [c for c in df.columns if c.lower().startswith("time")][0]
    df["time"] = pd.to_datetime(df[time_col], format="%Y.%m.%d %H:%M:%S")
    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close"})
    return df[["time", "open", "high", "low", "close"]].sort_values("time").reset_index(drop=True)


def run_backtest(df, round_sizes=(50.0, 100.0), buffer=3.15, sl_from_round=2.0, rr=2.0,
                  risk_percent=1.0, point_value=1.0, block_friday=False,
                  setup_hour=9, setup_minute=0, initial_capital=5000.0):
    equity = initial_capital
    trades = []
    open_positions = []  # list of dicts: direction, entry, sl, tp, qty, entry_time, source
    active = {}          # key -> order dict (entry, sl, tp, qty, dir, groups)
    groups = {rs: [] for rs in round_sizes}

    for i in range(len(df)):
        t = df["time"].iloc[i]
        o, h, l, c = df["open"].iloc[i], df["high"].iloc[i], df["low"].iloc[i], df["close"].iloc[i]
        is_friday = t.weekday() == 4
        is_setup = (t.hour == setup_hour) and (t.minute == setup_minute)

        if is_setup:
            active = {}
            groups = {rs: [] for rs in round_sizes}

            if not (block_friday and is_friday):
                risk_money = equity * (risk_percent / 100.0)
                for rs in round_sizes:
                    ref_open = o
                    upper = math.ceil(ref_open / rs) * rs
                    lower = math.floor(ref_open / rs) * rs

                    buy_entry = upper + buffer
                    sell_entry = lower - buffer
                    buy_sl = upper - sl_from_round
                    sell_sl = lower + sl_from_round
                    buy_risk = buy_entry - buy_sl
                    sell_risk = sell_sl - sell_entry
                    buy_tp = buy_entry + buy_risk * rr
                    sell_tp = sell_entry - sell_risk * rr
                    qty = risk_money / (buy_risk * point_value) if buy_risk > 0 else 0.0

                    for direction, entry, slp, tpp in (
                        (1, buy_entry, buy_sl, buy_tp), (-1, sell_entry, sell_sl, sell_tp)
                    ):
                        key = (round(entry, 6), direction)
                        if key in active:
                            active[key]["groups"].add(rs)
                        else:
                            active[key] = dict(entry=entry, sl=slp, tp=tpp, qty=qty,
                                                dir=direction, groups={rs})
                        groups[rs].append(key)

        if block_friday and is_friday:
            active = {}

        # --- exit check for all open positions (before new fills) ---
        still_open = []
        for pos in open_positions:
            if pos["dir"] == 1:
                hit_sl = l <= pos["sl"]
                hit_tp = h >= pos["tp"]
            else:
                hit_sl = h >= pos["sl"]
                hit_tp = l <= pos["tp"]

            exit_price = None
            if hit_sl:
                exit_price = pos["sl"]
            elif hit_tp:
                exit_price = pos["tp"]

            if exit_price is not None:
                pnl = (exit_price - pos["entry"]) * pos["dir"] * point_value * pos["qty"]
                equity += pnl
                trades.append(dict(
                    entry_time=pos["entry_time"], direction="BUY" if pos["dir"] == 1 else "SELL",
                    entry_price=pos["entry"], exit_time=t, exit_price=exit_price,
                    source=pos["source"], pnl=pnl,
                ))
            else:
                still_open.append(pos)
        open_positions = still_open

        # --- entry fills (multiple grids can trigger on different bars/levels) ---
        if active:
            triggered = [k for k, ordr in active.items()
                         if (ordr["dir"] == 1 and h >= ordr["entry"]) or
                            (ordr["dir"] == -1 and l <= ordr["entry"])]
            triggered.sort(key=lambda k: abs(active[k]["entry"] - o))
            for key in triggered:
                if key not in active:
                    continue
                order = active.pop(key)
                source = "+".join(str(int(g)) for g in sorted(order["groups"]))
                open_positions.append(dict(
                    dir=order["dir"], entry=order["entry"], sl=order["sl"], tp=order["tp"],
                    qty=order["qty"], entry_time=t, source=source,
                ))
                for g in order["groups"]:
                    for k2 in groups[g]:
                        if k2 != key and k2 in active:
                            del active[k2]

    return trades, equity


def summarize(trades, final_equity, initial_capital):
    total = len(trades)
    wins = [tr for tr in trades if tr["pnl"] > 0]
    losses = [tr for tr in trades if tr["pnl"] <= 0]
    win_rate = len(wins) / total * 100 if total else 0.0
    gp = sum(tr["pnl"] for tr in wins)
    gl = sum(tr["pnl"] for tr in losses)
    pf = gp / abs(gl) if gl != 0 else float("nan")
    net = final_equity - initial_capital

    peak = initial_capital
    eq = initial_capital
    max_dd = 0.0
    for tr in sorted(trades, key=lambda x: x["exit_time"]):
        eq += tr["pnl"]
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)

    return dict(trades=total, wins=len(wins), losses=len(losses), win_rate=win_rate,
                profit_factor=pf, net_profit=net, return_pct=net / initial_capital * 100,
                max_dd=max_dd, final_equity=final_equity)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--round-sizes", default="50,100")
    parser.add_argument("--buffer", type=float, default=3.15)
    parser.add_argument("--sl", type=float, default=2.0)
    parser.add_argument("--rr", type=float, default=2.0)
    parser.add_argument("--risk-pct", type=float, default=1.0)
    parser.add_argument("--cap", type=float, default=5000.0)
    parser.add_argument("--trades-out", default=None)
    args = parser.parse_args()

    round_sizes = tuple(float(x) for x in args.round_sizes.split(","))
    df = load_data(args.csv_path)
    trades, final_equity = run_backtest(
        df, round_sizes=round_sizes, buffer=args.buffer, sl_from_round=args.sl, rr=args.rr,
        risk_percent=args.risk_pct, block_friday=False, initial_capital=args.cap,
    )
    stats = summarize(trades, final_equity, args.cap)
    for k, v in stats.items():
        print(f"{k}: {v:,.2f}" if isinstance(v, float) else f"{k}: {v}")

    src_counts = pd.Series([tr["source"] for tr in trades]).value_counts()
    print("\nTrade source breakdown:", dict(src_counts))

    if args.trades_out:
        pd.DataFrame(trades).to_csv(args.trades_out, index=False)
        print(f"\nWrote {len(trades)} trades to {args.trades_out}")


if __name__ == "__main__":
    main()
