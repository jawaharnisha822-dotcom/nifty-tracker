"""
XAUUSD Round Number strategy - tick-level backtester.

This is the canonical version of the strategy: it consumes raw tick data
(Ask/Bid columns) instead of OHLC bars, so entries and exits are simulated
against the real Ask/Bid at the moment a level is crossed - no same-bar
ambiguity like the 15-minute-bar approximation in
backtest_xauusd_round_number.py.

Strategy parameters (fixed, matching the validated run):
    SL from round number : $5.00
    Entry buffer          : $3.15
    Risk : Reward          : 1 : 1.1
    Setup time             : 09:00 IST
    Friday trading         : allowed (no Friday block)
    Risk per trade         : 1% of equity

Input CSV must have a "Time (Asia/Kolkata)" column plus "Ask" and "Bid"
columns (Dukascopy tick export format). Large files are streamed in
chunks so this can run against multi-GB tick history without loading it
all into memory at once.

Usage:
    python backtest_xauusd_tick.py path/to/ticks.csv
    python backtest_xauusd_tick.py path/to/ticks.csv --window-days 14 --cap 5000
"""

import argparse

import numpy as np
import pandas as pd


def load_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    chunk.columns = [c.strip() for c in chunk.columns]
    chunk["t"] = pd.to_datetime(chunk["Time (Asia/Kolkata)"], format="%Y.%m.%d %H:%M:%S.%f")
    chunk["Ask"] = chunk["Ask"].astype("float32")
    chunk["Bid"] = chunk["Bid"].astype("float32")
    return chunk[["t", "Ask", "Bid"]]


class StrategyState:
    """Round-number breakout strategy, carried across chunks so a
    position/pending order opened in one chunk can be resolved in the next.
    """

    def __init__(self, cap=5000.0, risk_pct=1.0, buf=3.15, sl_from=5.0, rr=1.1,
                 rnd=100.0, setup_h=9, setup_m=0):
        self.eq = cap
        self.cap = cap
        self.risk_pct = risk_pct
        self.buf = buf
        self.sl_from = sl_from
        self.rr = rr
        self.rnd = rnd
        self.setup_h = setup_h
        self.setup_m = setup_m
        self.pend = None
        self.pos = None
        self.last_setup_minute = None
        self.trades = []

    def process(self, df: pd.DataFrame):
        ask = df.Ask.values
        bid = df.Bid.values
        ts = df["t"]
        hh = ts.dt.hour.values
        mm = ts.dt.minute.values

        for i in range(len(df)):
            minute_key = (ts.iloc[i].date(), hh[i], mm[i])
            is_setup = (hh[i] == self.setup_h and mm[i] == self.setup_m
                        and minute_key != self.last_setup_minute)

            if is_setup:
                self.last_setup_minute = minute_key
                self.pend = None
                if self.pos is None:
                    ref_open = (ask[i] + bid[i]) / 2
                    up = np.ceil(ref_open / self.rnd) * self.rnd
                    lo = np.floor(ref_open / self.rnd) * self.rnd
                    be_level = up + self.buf
                    se_level = lo - self.buf
                    bsl = up - self.sl_from
                    ssl = lo + self.sl_from
                    brisk = be_level - bsl
                    srisk = ssl - se_level
                    self.pend = dict(
                        be=be_level, se=se_level, bsl=bsl, ssl=ssl,
                        btp=be_level + brisk * self.rr,
                        stp=se_level - srisk * self.rr,
                        bq=(self.eq * self.risk_pct / 100) / brisk if brisk > 0 else 0,
                        sq=(self.eq * self.risk_pct / 100) / srisk if srisk > 0 else 0,
                    )

            a = ask[i]
            b = bid[i]

            if self.pos is not None:
                if self.pos["dir"] == 1:
                    hit_sl = b <= self.pos["sl"]
                    hit_tp = b >= self.pos["tp"]
                    real_price = b
                else:
                    hit_sl = a >= self.pos["sl"]
                    hit_tp = a <= self.pos["tp"]
                    real_price = a

                if hit_sl or hit_tp:
                    pnl = (real_price - self.pos["entry"]) * self.pos["dir"] * self.pos["qty"]
                    self.eq += pnl
                    self.trades.append(dict(exit_time=ts.iloc[i], pnl=round(pnl, 2)))
                    self.pos = None

            if self.pos is None and self.pend is not None:
                if b >= self.pend["be"]:
                    self.pos = dict(dir=1, entry=a, sl=self.pend["bsl"], tp=self.pend["btp"],
                                     qty=self.pend["bq"])
                    self.pend = None
                elif a <= self.pend["se"]:
                    self.pos = dict(dir=-1, entry=b, sl=self.pend["ssl"], tp=self.pend["stp"],
                                     qty=self.pend["sq"])
                    self.pend = None


def analyze_rolling_windows(trades_df: pd.DataFrame, window_days: int = 14) -> pd.DataFrame:
    trades_df = trades_df.sort_values("exit_time").reset_index(drop=True)
    trades_df["date"] = trades_df.exit_time.dt.normalize()

    daily_pnl = trades_df.groupby("date")["pnl"].sum()
    all_dates = pd.date_range(daily_pnl.index.min(), daily_pnl.index.max(), freq="D")
    daily_pnl = daily_pnl.reindex(all_dates, fill_value=0.0)

    window_results = []
    for start in daily_pnl.index:
        end = start + pd.Timedelta(days=window_days)
        if end > daily_pnl.index[-1] + pd.Timedelta(days=1):
            break
        window_pnl = daily_pnl.loc[start:end - pd.Timedelta(days=1)].sum()
        window_results.append(dict(
            start=start.date(), end=(end - pd.Timedelta(days=1)).date(),
            net_pnl=round(window_pnl, 2),
        ))

    return pd.DataFrame(window_results)


def show_analysis(wdf: pd.DataFrame, window_days: int):
    print("=" * 65)
    print(f"ROLLING {window_days}-DAY NET P&L DISTRIBUTION  ({len(wdf)} overlapping windows)")
    print("=" * 65)

    pcts = [5, 10, 25, 50, 75, 90, 95]
    print()
    print("PERCENTILES (dollar amount every window reached AT LEAST this often):")
    for p in pcts:
        val = np.percentile(wdf.net_pnl, 100 - p)
        print(f"  {100 - p:3d}th percentile achieved  ->  ${val:8.2f}   "
              f"(this amount or MORE was hit in {p}% of all {window_days}-day windows)")

    print()
    print(f"Mean {window_days}-day P&L    : ${wdf.net_pnl.mean():.2f}")
    print(f"Median {window_days}-day P&L  : ${wdf.net_pnl.median():.2f}")
    print(f"Worst {window_days}-day P&L   : ${wdf.net_pnl.min():.2f}")
    print(f"Best {window_days}-day P&L    : ${wdf.net_pnl.max():.2f}")

    print()
    print("=" * 65)
    print("HIT-RATE TABLE  (how often a round-number target was reached)")
    print("=" * 65)
    for target in [150, 200, 250, 300, 350, 400, 450, 500]:
        hit_rate = 100 * (wdf.net_pnl >= target).mean()
        print(f"  Target ${target:4d}  ->  reached in {hit_rate:5.1f}% of {window_days}-day windows")

    print()
    print("=" * 65)
    print("SUGGESTED PAYOUT TARGETS")
    print("=" * 65)
    print(f"Conservative (reached ~75-80% of windows) : ${np.percentile(wdf.net_pnl, 25):.2f}")
    print(f"Balanced (median, reached ~50% of windows) : ${np.percentile(wdf.net_pnl, 50):.2f}")
    print(f"Aggressive (reached ~25% of windows)       : ${np.percentile(wdf.net_pnl, 75):.2f}")

    print()
    print("Full window table (first 20 rows):")
    print(wdf.head(20).to_string(index=False))


def main():
    parser = argparse.ArgumentParser(description="Tick-level backtest of the XAUUSD Round Number strategy")
    parser.add_argument("csv_path", help="Path to tick CSV with Time/Ask/Bid columns")
    parser.add_argument("--cap", type=float, default=5000.0)
    parser.add_argument("--risk-pct", type=float, default=1.0)
    parser.add_argument("--buffer", type=float, default=3.15)
    parser.add_argument("--sl-from-round", type=float, default=5.0)
    parser.add_argument("--rr", type=float, default=1.1)
    parser.add_argument("--round-size", type=float, default=100.0)
    parser.add_argument("--setup-hour", type=int, default=9)
    parser.add_argument("--setup-minute", type=int, default=0)
    parser.add_argument("--chunk-size", type=int, default=1_000_000)
    parser.add_argument("--window-days", type=int, default=14)
    parser.add_argument("--trades-out", default=None, help="Optional path to write per-trade CSV")
    args = parser.parse_args()

    state = StrategyState(
        cap=args.cap, risk_pct=args.risk_pct, buf=args.buffer, sl_from=args.sl_from_round,
        rr=args.rr, rnd=args.round_size, setup_h=args.setup_hour, setup_m=args.setup_minute,
    )

    chunk_num = 0
    for raw_chunk in pd.read_csv(args.csv_path, chunksize=args.chunk_size):
        chunk_num += 1
        print(f"Processing chunk {chunk_num} ({len(raw_chunk)} rows)...")
        state.process(load_chunk(raw_chunk))

    trades_df = pd.DataFrame(state.trades)
    total = len(trades_df)
    wins = (trades_df.pnl > 0).sum() if total else 0
    losses = total - wins
    win_rate = wins / total * 100 if total else 0.0
    gross_profit = trades_df.loc[trades_df.pnl > 0, "pnl"].sum() if total else 0.0
    gross_loss = trades_df.loc[trades_df.pnl <= 0, "pnl"].sum() if total else 0.0
    profit_factor = gross_profit / abs(gross_loss) if gross_loss != 0 else float("nan")
    net_pnl = trades_df.pnl.sum() if total else 0.0

    print()
    print("=" * 65)
    print(f"RESULT (SL=${args.sl_from_round}, Buffer=${args.buffer}, RR=1:{args.rr})")
    print("=" * 65)
    print(f"Trades       : {total}")
    print(f"Wins/Losses  : {wins}/{losses}")
    print(f"Win rate     : {win_rate:.2f}%")
    print(f"Profit factor: {profit_factor:.3f}")
    print(f"Net P&L      : {net_pnl:.2f}")
    print(f"Return       : {net_pnl / args.cap * 100:.2f}%")

    if args.trades_out and total:
        trades_df.to_csv(args.trades_out, index=False)
        print(f"\nWrote {total} trades to {args.trades_out}")

    if total:
        print()
        wdf = analyze_rolling_windows(trades_df, window_days=args.window_days)
        show_analysis(wdf, args.window_days)


if __name__ == "__main__":
    main()
