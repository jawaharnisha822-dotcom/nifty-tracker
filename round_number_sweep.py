"""
Fast round-number sweep across instruments.

The row-by-row pandas.iloc loop in backtest_xauusd_round_number.py is
correct but too slow to sweep hundreds/thousands of round-number values
(each full run over 10 years of 15-min gold data takes ~35s). This module
re-implements the exact same strategy logic using raw numpy arrays (no
per-row pandas overhead) so a full sweep finishes in a reasonable time.

Strategy logic is identical to backtest_xauusd_round_number.run_backtest:
setup at a fixed IST time each day, round-number breakout stop entries,
fixed SL/TP bracket at a given Risk:Reward, 1% (default) equity risk
sizing, optional Friday block, and the same "check exits before new fills"
ordering that avoids testing an entry bar's own SL/TP with data that could
have occurred before the entry actually triggered.

Usage:
    python round_number_sweep.py gold.csv --pip 0.01  --sl-pips 3 --buffer-pips 5 --rr 2 \
        --round-min-pips 100 --round-max-pips 100000 --round-step-pips 100

    python round_number_sweep.py audusd.csv --pip 0.0001 --sl-pips 2 --buffer-pips 3.15 --rr 2 \
        --round-min-pips 100 --round-max-pips 100000 --round-step-pips 100
"""

import argparse

import numpy as np
import pandas as pd


def load_ohlc(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    time_col = [c for c in df.columns if c.lower().startswith("time")][0]
    df["time"] = pd.to_datetime(df[time_col], format="%Y.%m.%d %H:%M:%S")
    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close"})
    return df[["time", "open", "high", "low", "close"]].sort_values("time").reset_index(drop=True)


def run_backtest_fast(o, h, l, c, hour, minute, weekday, *,
                       risk_percent, entry_buffer, sl_from_round, rr, round_size,
                       point_value, block_friday, setup_hour, setup_minute, initial_capital):
    n = len(o)
    is_setup = (hour == setup_hour) & (minute == setup_minute)
    is_friday = weekday == 4

    equity = initial_capital
    peak_equity = initial_capital
    max_dd = 0.0

    pend_be = pend_se = pend_bsl = pend_ssl = pend_btp = pend_stp = pend_bq = pend_sq = 0.0
    pending = False
    setup_active = False
    trade_taken_today = False

    pos_dir = 0
    pos_entry = pos_sl = pos_tp = pos_qty = 0.0

    n_trades = n_wins = n_losses = 0
    gross_profit = 0.0
    gross_loss = 0.0

    for i in range(n):
        oi, hi, li = o[i], h[i], l[i]

        if is_setup[i]:
            pending = False
            setup_active = False
            trade_taken_today = False

            ref_open = oi
            up = np.ceil(ref_open / round_size) * round_size
            lo = np.floor(ref_open / round_size) * round_size

            be = up + entry_buffer
            se = lo - entry_buffer
            bsl = up - sl_from_round
            ssl = lo + sl_from_round
            brisk = be - bsl
            srisk = ssl - se
            btp = be + brisk * rr
            stp = se - srisk * rr

            risk_money = equity * (risk_percent / 100.0)
            bq = risk_money / (brisk * point_value) if brisk > 0 else 0.0
            sq = risk_money / (srisk * point_value) if srisk > 0 else 0.0

            if not (block_friday and is_friday[i]):
                setup_active = True
                pending = True
                pend_be, pend_se, pend_bsl, pend_ssl = be, se, bsl, ssl
                pend_btp, pend_stp, pend_bq, pend_sq = btp, stp, bq, sq

        if block_friday and is_friday[i]:
            pending = False
            setup_active = False

        # --- exit check (before new fills, so this bar's own new entry is
        # never exit-tested until the next bar) ---
        if pos_dir != 0:
            if pos_dir == 1:
                hit_sl = li <= pos_sl
                hit_tp = hi >= pos_tp
            else:
                hit_sl = hi >= pos_sl
                hit_tp = li <= pos_tp

            exit_price = None
            if hit_sl:
                exit_price = pos_sl
            elif hit_tp:
                exit_price = pos_tp

            if exit_price is not None:
                pnl = (exit_price - pos_entry) * pos_dir * point_value * pos_qty
                equity += pnl
                peak_equity = max(peak_equity, equity)
                max_dd = max(max_dd, peak_equity - equity)
                n_trades += 1
                if pnl > 0:
                    n_wins += 1
                    gross_profit += pnl
                else:
                    n_losses += 1
                    gross_loss += pnl
                pos_dir = 0

        # --- pending entry fill ---
        if setup_active and pending and pos_dir == 0 and not trade_taken_today:
            hit_buy = hi >= pend_be
            hit_sell = li <= pend_se

            direction = 0
            if hit_buy and hit_sell:
                if (pend_be - oi) <= (oi - pend_se):
                    direction = 1
                else:
                    direction = -1
            elif hit_buy:
                direction = 1
            elif hit_sell:
                direction = -1

            if direction == 1:
                pos_dir, pos_entry, pos_sl, pos_tp, pos_qty = 1, pend_be, pend_bsl, pend_btp, pend_bq
                pending = False
                trade_taken_today = True
            elif direction == -1:
                pos_dir, pos_entry, pos_sl, pos_tp, pos_qty = -1, pend_se, pend_ssl, pend_stp, pend_sq
                pending = False
                trade_taken_today = True

    win_rate = (n_wins / n_trades * 100.0) if n_trades else 0.0
    profit_factor = (gross_profit / abs(gross_loss)) if gross_loss != 0 else float("nan")
    net_profit = equity - initial_capital
    return_pct = net_profit / initial_capital * 100.0

    return dict(
        trades=n_trades, wins=n_wins, losses=n_losses, win_rate=win_rate,
        profit_factor=profit_factor, net_profit=net_profit, return_pct=return_pct,
        max_dd=max_dd, final_equity=equity,
    )


def sweep(csv_path, pip, sl_pips, buffer_pips, rr, round_min_pips, round_max_pips,
          round_step_pips, risk_percent=1.0, block_friday=False, setup_hour=9,
          setup_minute=0, initial_capital=5000.0, point_value=1.0):
    df = load_ohlc(csv_path)
    o = df.open.values.astype("float64")
    h = df.high.values.astype("float64")
    l = df.low.values.astype("float64")
    c = df.close.values.astype("float64")
    hour = df.time.dt.hour.values
    minute = df.time.dt.minute.values
    weekday = df.time.dt.weekday.values

    sl_from_round = sl_pips * pip
    entry_buffer = buffer_pips * pip

    results = []
    for round_pips in range(round_min_pips, round_max_pips + 1, round_step_pips):
        round_size = round_pips * pip
        res = run_backtest_fast(
            o, h, l, c, hour, minute, weekday,
            risk_percent=risk_percent, entry_buffer=entry_buffer, sl_from_round=sl_from_round,
            rr=rr, round_size=round_size, point_value=point_value, block_friday=block_friday,
            setup_hour=setup_hour, setup_minute=setup_minute, initial_capital=initial_capital,
        )
        res["round_pips"] = round_pips
        res["round_size"] = round_size
        results.append(res)

    return pd.DataFrame(results), df


def main():
    parser = argparse.ArgumentParser(description="Sweep round-number size for the Round Number strategy")
    parser.add_argument("csv_path")
    parser.add_argument("--pip", type=float, required=True, help="Price value of 1 pip for this instrument (e.g. 0.01 for XAUUSD, 0.0001 for AUDUSD)")
    parser.add_argument("--sl-pips", type=float, required=True)
    parser.add_argument("--buffer-pips", type=float, required=True)
    parser.add_argument("--rr", type=float, default=2.0)
    parser.add_argument("--round-min-pips", type=int, default=100)
    parser.add_argument("--round-max-pips", type=int, default=100000)
    parser.add_argument("--round-step-pips", type=int, default=100)
    parser.add_argument("--risk-pct", type=float, default=1.0)
    parser.add_argument("--cap", type=float, default=5000.0)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    res, _ = sweep(
        args.csv_path, args.pip, args.sl_pips, args.buffer_pips, args.rr,
        args.round_min_pips, args.round_max_pips, args.round_step_pips,
        risk_percent=args.risk_pct, initial_capital=args.cap,
    )

    if args.out:
        res.to_csv(args.out, index=False)
        print(f"Wrote {len(res)} rows to {args.out}")

    valid = res[res.trades >= 20]
    print(f"\nTotal round_size values tested: {len(res)}")
    print(f"Values with >=20 trades: {len(valid)}")
    if len(valid):
        print("\nTop 10 by Profit Factor (min 20 trades):")
        print(valid.sort_values("profit_factor", ascending=False).head(10).to_string(index=False))


if __name__ == "__main__":
    main()
