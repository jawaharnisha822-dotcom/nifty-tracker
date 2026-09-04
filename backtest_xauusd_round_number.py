"""
XAUUSD Round Number strategy backtester.

Reimplements the Pine Script strategy "XAUUSD Round Number | 10S | Adjustable
Time | Fixed 1:1 | 1% Risk" in Python/pandas so it can be run against
historical OHLC data exported from a broker/data vendor (e.g. Dukascopy CSV
exports with a "Time (Asia/Kolkata)" column).

Caveat: the original script is designed for a 10-second chart (it looks for
the exact second the setup candle opens). Run on 15-minute bars, entries and
exits are approximated at bar resolution: a stop order is considered filled
the first bar whose high/low crosses the trigger level, and when both the
stop-loss and take-profit levels are touched inside the same bar the
stop-loss is assumed to hit first (the conservative assumption).

Usage:
    python backtest_xauusd_round_number.py path/to/data.csv
"""

import argparse
import math
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Inputs:
    risk_percent: float = 1.0
    entry_buffer: float = 3.15
    sl_from_round: float = 5.0
    rr: float = 1.0
    round_size: float = 100.0
    point_value: float = 1.0
    block_friday: bool = True
    setup_hour: int = 9
    setup_minute: int = 0
    initial_capital: float = 5000.0


@dataclass
class Trade:
    direction: int  # 1 = long, -1 = short
    entry_time: pd.Timestamp
    entry_price: float
    sl: float
    tp: float
    qty: float
    exit_time: pd.Timestamp = None
    exit_price: float = None
    pnl: float = None


def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    time_col = [c for c in df.columns if c.lower().startswith("time")][0]
    df["time"] = pd.to_datetime(df[time_col], format="%Y.%m.%d %H:%M:%S")
    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close"})
    df = df[["time", "open", "high", "low", "close"]].sort_values("time").reset_index(drop=True)
    return df


def run_backtest(df: pd.DataFrame, cfg: Inputs):
    equity = cfg.initial_capital
    trades: list[Trade] = []
    equity_curve = [(df["time"].iloc[0], equity)]

    pending = None       # dict: direction -> (entry, sl, tp) for BUY/SELL pending stop orders
    open_trade: Trade | None = None
    setup_active = False
    trade_taken_today = False
    current_day = None

    for i in range(len(df)):
        t = df["time"].iloc[i]
        o, h, l, c = df["open"].iloc[i], df["high"].iloc[i], df["low"].iloc[i], df["close"].iloc[i]
        day = t.date()
        is_friday = t.weekday() == 4  # Monday=0 ... Friday=4

        if day != current_day:
            current_day = day
            # daily reset happens logically at setup time below; Friday check applies every bar

        is_setup_time = (t.hour == cfg.setup_hour) and (t.minute == cfg.setup_minute)

        if is_setup_time:
            pending = None
            setup_active = False
            trade_taken_today = False

            ref_open = o
            upper_round = math.ceil(ref_open / cfg.round_size) * cfg.round_size
            lower_round = math.floor(ref_open / cfg.round_size) * cfg.round_size

            buy_entry = upper_round + cfg.entry_buffer
            sell_entry = lower_round - cfg.entry_buffer

            buy_sl = upper_round - cfg.sl_from_round
            sell_sl = lower_round + cfg.sl_from_round

            buy_risk = buy_entry - buy_sl
            sell_risk = sell_sl - sell_entry

            buy_tp = buy_entry + buy_risk * cfg.rr
            sell_tp = sell_entry - sell_risk * cfg.rr

            risk_money = equity * (cfg.risk_percent / 100.0)
            buy_qty = risk_money / (buy_risk * cfg.point_value) if buy_risk > 0 else 0.0
            sell_qty = risk_money / (sell_risk * cfg.point_value) if sell_risk > 0 else 0.0

            if not (cfg.block_friday and is_friday):
                setup_active = True
                pending = {
                    "buy": (buy_entry, buy_sl, buy_tp, buy_qty),
                    "sell": (sell_entry, sell_sl, sell_tp, sell_qty),
                }

        if cfg.block_friday and is_friday:
            pending = None
            setup_active = False

        # --- manage open trade exit (checked BEFORE new fills, using this
        # bar's full range, so a trade opened *this* bar is only exit-tested
        # starting next bar - we have no tick data to know whether a level
        # on the entry bar was touched before or after the entry itself) ---
        if open_trade is not None:
            if open_trade.direction == 1:
                hit_sl = l <= open_trade.sl
                hit_tp = h >= open_trade.tp
            else:
                hit_sl = h >= open_trade.sl
                hit_tp = l <= open_trade.tp

            exit_price = None
            if hit_sl and hit_tp:
                exit_price = open_trade.sl  # conservative: SL first
            elif hit_sl:
                exit_price = open_trade.sl
            elif hit_tp:
                exit_price = open_trade.tp

            if exit_price is not None:
                open_trade.exit_time = t
                open_trade.exit_price = exit_price
                if open_trade.direction == 1:
                    pnl = (exit_price - open_trade.entry_price) * open_trade.qty * cfg.point_value
                else:
                    pnl = (open_trade.entry_price - exit_price) * open_trade.qty * cfg.point_value
                open_trade.pnl = pnl
                equity += pnl
                trades.append(open_trade)
                equity_curve.append((t, equity))
                open_trade = None

        # --- manage pending entry orders ---
        if setup_active and pending is not None and open_trade is None and not trade_taken_today:
            buy_entry, buy_sl, buy_tp, buy_qty = pending["buy"]
            sell_entry, sell_sl, sell_tp, sell_qty = pending["sell"]

            hit_buy = h >= buy_entry
            hit_sell = l <= sell_entry

            direction = 0
            if hit_buy and hit_sell:
                # both stop levels touched in the same bar - assume price moved
                # toward whichever level was closer to the bar's open first
                if (buy_entry - o) <= (o - sell_entry):
                    direction = 1
                else:
                    direction = -1
            elif hit_buy:
                direction = 1
            elif hit_sell:
                direction = -1

            if direction == 1:
                open_trade = Trade(1, t, buy_entry, buy_sl, buy_tp, buy_qty)
                pending = None
                trade_taken_today = True
            elif direction == -1:
                open_trade = Trade(-1, t, sell_entry, sell_sl, sell_tp, sell_qty)
                pending = None
                trade_taken_today = True

    return trades, equity, equity_curve


def summarize(trades: list[Trade], final_equity: float, equity_curve, cfg: Inputs):
    total = len(trades)
    wins = [tr for tr in trades if tr.pnl > 0]
    losses = [tr for tr in trades if tr.pnl <= 0]
    win_rate = (len(wins) / total * 100.0) if total else 0.0
    gross_profit = sum(tr.pnl for tr in wins)
    gross_loss = sum(tr.pnl for tr in losses)
    profit_factor = (gross_profit / abs(gross_loss)) if gross_loss != 0 else float("nan")
    net_profit = final_equity - cfg.initial_capital
    ret_pct = net_profit / cfg.initial_capital * 100.0

    peak = cfg.initial_capital
    max_dd = 0.0
    for _, eq in equity_curve:
        peak = max(peak, eq)
        dd = peak - eq
        max_dd = max(max_dd, dd)

    return {
        "Setup Time": f"{cfg.setup_hour:02d}:{cfg.setup_minute:02d} IST",
        "Initial Capital": cfg.initial_capital,
        "Final Equity": final_equity,
        "Trades": total,
        "Wins": len(wins),
        "Losses": len(losses),
        "Win Rate": win_rate,
        "Profit Factor": profit_factor,
        "Net Profit": net_profit,
        "Return %": ret_pct,
        "Max Drawdown": max_dd,
    }


def main():
    parser = argparse.ArgumentParser(description="Backtest the XAUUSD Round Number strategy")
    parser.add_argument("csv_path", help="Path to OHLC CSV file (Time, Open, High, Low, Close)")
    parser.add_argument("--setup-hour", type=int, default=9)
    parser.add_argument("--setup-minute", type=int, default=0)
    parser.add_argument("--trades-out", default=None, help="Optional path to write per-trade CSV")
    args = parser.parse_args()

    cfg = Inputs(setup_hour=args.setup_hour, setup_minute=args.setup_minute)
    df = load_data(args.csv_path)
    trades, final_equity, equity_curve = run_backtest(df, cfg)
    stats = summarize(trades, final_equity, equity_curve, cfg)

    for k, v in stats.items():
        if isinstance(v, float):
            print(f"{k}: {v:,.2f}")
        else:
            print(f"{k}: {v}")

    if args.trades_out:
        rows = [{
            "entry_time": tr.entry_time, "direction": "BUY" if tr.direction == 1 else "SELL",
            "entry_price": tr.entry_price, "sl": tr.sl, "tp": tr.tp, "qty": tr.qty,
            "exit_time": tr.exit_time, "exit_price": tr.exit_price, "pnl": tr.pnl,
        } for tr in trades]
        pd.DataFrame(rows).to_csv(args.trades_out, index=False)
        print(f"\nWrote {len(rows)} trades to {args.trades_out}")


if __name__ == "__main__":
    main()
