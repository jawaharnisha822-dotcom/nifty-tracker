"""Independent brute-force check of every trade in results_realistic/trades.csv.

Re-derives, straight from the raw ticks and with no shared code path:
  * the first tick that triggers the entry stop,
  * the first tick after entry that touches SL or TP,
and compares against the engine's output.
"""
import csv, sys

CSV = sys.argv[1]
trades = list(csv.DictReader(open('results_realistic/trades.csv')))
setups = {d['day']: d for d in csv.DictReader(open('results_realistic/daily_setups.csv'))}

ticks = []
with open(CSV) as fh:
    fh.readline()
    for line in fh:
        ts, ask, bid = line.split(',', 3)[:3]
        ticks.append((ts, float(ask), float(bid)))
print(f"loaded {len(ticks):,} ticks")

def scan_entry(start_ts, direction, level):
    for ts, ask, bid in ticks:
        if ts < start_ts:
            continue
        if direction == 'long' and ask >= level:
            return ts, ask
        if direction == 'short' and bid <= level:
            return ts, bid
    return None, None

def scan_exit(start_ts, direction, sl, tp):
    for ts, ask, bid in ticks:
        if ts <= start_ts:
            continue
        if direction == 'long':
            if bid <= sl:  return ts, bid, 'SL'
            if bid >= tp:  return ts, tp, 'TP'
        else:
            if ask >= sl:  return ts, ask, 'SL'
            if ask <= tp:  return ts, tp, 'TP'
    return None, None, None

fails = 0
for t in trades:
    # the setup that armed this order = the last setup at or before the entry
    arm_day = max((d for d in setups if setups[d]['setup_ts'] <= t['entry_ts']),
                  key=lambda d: setups[d]['setup_ts'])
    s = setups[arm_day]
    lvl = float(s['buy_entry'] if t['dir'] == 'long' else s['sell_entry'])
    sl  = float(s['buy_sl']    if t['dir'] == 'long' else s['sell_sl'])
    tp  = float(s['buy_tp']    if t['dir'] == 'long' else s['sell_tp'])

    e_ts, e_px = scan_entry(s['setup_ts'], t['dir'], lvl)
    x_ts, x_px, x_rs = scan_exit(t['entry_ts'], t['dir'], sl, tp)

    ok = (e_ts == t['entry_ts'] and abs(e_px - float(t['entry'])) < 1e-6
          and x_ts == t['exit_ts'] and abs(x_px - float(t['exit'])) < 1e-6
          and x_rs == t['reason'])

    # recompute P&L from scratch
    qty = float(t['qty'])
    pnl = (x_px - e_px) * qty if t['dir'] == 'long' else (e_px - x_px) * qty
    ok_pnl = abs(pnl - float(t['pnl'])) < 0.011

    status = 'OK ' if (ok and ok_pnl) else 'FAIL'
    if status == 'FAIL':
        fails += 1
        print(f"  engine: entry {t['entry_ts']} @{t['entry']}  exit {t['exit_ts']} @{t['exit']} {t['reason']} pnl {t['pnl']}")
        print(f"  brute : entry {e_ts} @{e_px}  exit {x_ts} @{x_px} {x_rs} pnl {pnl:.2f}")
    print(f"{status} armed@{arm_day}  {t['dir']:<5} entry {e_ts} @{e_px:.3f} -> {x_rs} {x_ts} @{x_px:.3f}  pnl {pnl:+.2f}")

print(f"\n{len(trades)-fails}/{len(trades)} trades verified identical.  fails={fails}")

# equity chain check
eq = 5000.0
for t in trades:
    eq += float(t['pnl'])
    assert abs(eq - float(t['equity_after'])) < 0.02, (t['day'], eq, t['equity_after'])
print(f"equity chain consistent, final = {eq:.2f}")
