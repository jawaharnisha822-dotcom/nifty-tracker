# XAUUSD $100 Round-Number Strategy — Tick Backtest

Tick-by-tick backtest of the Pine v5 strategy
*"XAUUSD Round Number | 10S | 100 + 50 Dual Strategy | 1% Risk"*
with **only the $100 round leg enabled** (`round100 = true`, `round50 = false`).

## Data
| | |
|---|---|
| Source | `XAUUSD_Ticks_2026.03.01_2026.03.20.csv` (real bid/ask ticks) |
| Ticks | 5,734,426 |
| Period | 2026.03.02 → 2026.03.20 |
| Timezone | Asia/Kolkata (IST) — already native in the file |
| Setup days | 15 (Saturdays 03.07 / 03.14 close before 09:00 IST) |

## Strategy parameters (Pine defaults)
Initial capital 5000 · Risk 1%/trade · Entry buffer $3.15 · SL $2.00 from round ·
RR 1:2 · Point value 1.0 · Setup 09:00 IST · Round step $100

Per day at 09:00 IST: `upper = ceil(open/100)*100`, `lower = floor(open/100)*100`
- Buy stop `upper + 3.15`, SL `upper - 2.00`, TP `entry + 10.30`
- Sell stop `lower - 3.15`, SL `lower + 2.00`, TP `entry - 10.30`
- Risk/unit = $5.15 · OCA: first fill cancels the other side · max 1 trade/day

## Execution model (primary run)
- Reference 09:00 "open" = **bid** of the first tick at/after 09:00:00.000
- Long entry fills on **ask ≥ level**, short entry fills on **bid ≤ level**
  (fill price = the actual tick price, so gap slippage is real, not assumed)
- Long exits priced on **bid**, short exits on **ask**
- SL = market fill at the tick price (slippage allowed); TP = fills exactly at the limit
- Equity compounds: size recalculated from `strategy.equity` at each 09:00 setup

## Headline result
| Metric | Value |
|---|---|
| Trades | 15 |
| Wins / Losses | 7 / 8 |
| Win rate | 46.67% |
| Profit factor | **1.51** |
| Net profit | **+$233.14 (+4.66%)** |
| Final equity | $5,233.14 |
| Max drawdown | $138.47 (2.72%) |
| Expectancy | +0.32R |
| Avg win / avg loss | $98.27 / $56.85 |

## Files
| File | Contents |
|---|---|
| `backtest_round100.py` | The tick engine (faithful Pine state machine) |
| `verify.py` | Independent brute-force re-derivation of every fill |
| `analysis.py` | MAE/MFE, cost sensitivity, order-lifetime quirk |
| `results_realistic/trades.csv` | Every trade with entry/exit tick timestamps |
| `results_realistic/daily_setups.csv` | The 15 daily level sets and outcomes |
| `results_realistic/summary.json` | Summary metrics |

## Reproduce
```bash
python3 backtest_round100.py <ticks.csv> --out results_realistic
python3 verify.py <ticks.csv>          # 15/15 trades verified identical
python3 analysis.py <ticks.csv>
```

## Two behaviours found in the original Pine script
1. **Pending orders survive overnight.** They are only cancelled at the *next*
   09:00 setup, so the 2026.03.12 setup (which never triggered during its own
   day) filled at **2026.03.13 00:15**, and 03.13 then took a second trade from
   its own setup. That single overnight trade is +$95.25 — without it the run is
   +$137.87 (+2.76%) instead of +$233.14.
2. **Open positions inherit the new day's SL/TP.** `strategy.exit` is re-issued
   every bar using the current-day variables, so a position held through 09:00
   would silently have its stop and target moved. It did not bite in this
   sample — no trade was ever open at a 09:00 setup — but it is live in the code.
