# XAUUSD Round-Number Strategy — backtest study

Python replication, diagnosis and re-optimisation of the Pine v5 strategy
*"XAUUSD Round Number | 10S | 100 + 50 Dual Strategy | 1% Risk"*.

Data: `XAUUSD 15-min bid, 2016-01-01 → 2026-06-09` (246,838 bars, Asia/Kolkata).

## Files

| file | what it is |
|---|---|
| `engine.py`  | Faithful replica of the ORIGINAL Pine script, bug-for-bug. Four intrabar models. |
| `engine2.py` | The CORRECTED strategy (single OCA, one grid, order expiry, gap-capped entry, ATR stop). |
| `BUGS.md`    | The nine defects found in the original script. |
| `strategy_corrected.pine` | The fixed Pine v5 implementation, ready to paste into TradingView. |
| `REPORT.md`  | Full findings: does it work, best entry time, best parameters. |
| `sweep*.py`, `calibrate.py`, `diagnose.py`, `walkforward.py` | The experiments. |
| `results/`   | Raw logs and CSVs from every run. |

## The intrabar problem (read this first)

The original risks `entry_buffer + sl_from_round = 3.15 + 2.00 = $5.15` per trade.
In 2025-26, **55% of 15-minute XAUUSD bars have a range wider than that entire
stop distance**. So for most trades, both the stop and the target sit inside a
single bar, and 15-minute OHLC data cannot tell you which was touched first.

That is not a detail — it is the whole result:

| intrabar assumption | win rate | profit factor |
|---|---|---|
| always assume SL first | 14.7% | 0.43 |
| 3-leg OHLC path (o→l→h→c) | 46.8% | 1.68 |
| Monte-Carlo, ~7.5s resolution | 34.0% | 0.91 |

Any backtest of this strategy that does not state its intrabar assumption is
reporting an artefact. `engine.py` therefore ships all four models, and every
number in `REPORT.md` uses the Monte-Carlo model averaged over 6 random seeds,
with a $0.30/oz round-trip cost.

## Reproduce

```bash
pip install pandas numpy
./run_all.sh          # ~45 min on 4 cores
```
