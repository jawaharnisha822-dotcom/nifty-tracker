"""MAE/MFE, cost sensitivity, and the overnight-pending-order quirk."""
import csv, sys
CSV = sys.argv[1]
tr = list(csv.DictReader(open('results_realistic/trades.csv')))

ticks = []
with open(CSV) as fh:
    fh.readline()
    for line in fh:
        ts, ask, bid = line.split(',', 3)[:3]
        ticks.append((ts, float(ask), float(bid)))

print("=== MAE / MFE per trade (in R, risk = planned 5.15/unit) ===")
print(f"{'setup':<12}{'dir':<6}{'result':<7}{'MAE_R':>8}{'MFE_R':>8}   how close to the other side")
rows = []
for t in tr:
    e = float(t['entry']); d = t['dir']; risk = 5.15
    mae = mfe = 0.0
    for ts, ask, bid in ticks:
        if ts <= t['entry_ts']: continue
        if ts > t['exit_ts']: break
        if d == 'long':
            mae = min(mae, (bid - e)); mfe = max(mfe, (bid - e))
        else:
            mae = min(mae, -(ask - e)); mfe = max(mfe, -(ask - e))
    rows.append((t, mae/risk, mfe/risk))
    note = ''
    if t['reason'] == 'TP' and mae/risk < -0.5: note = f"went {abs(mae/risk):.2f}R against first"
    if t['reason'] == 'SL' and mfe/risk >  0.5: note = f"was {mfe/risk:.2f}R in profit first"
    print(f"{t['day']:<12}{d:<6}{t['reason']:<7}{mae/risk:>8.2f}{mfe/risk:>8.2f}   {note}")

print("\n=== Cost sensitivity (commission, $ per ounce round-turn) ===")
gross = sum(float(t['pnl']) for t in tr)
for c in (0.0, 0.05, 0.07, 0.10, 0.20, 0.35):
    cost = sum(float(t['qty']) * c for t in tr)
    print(f"  ${c:.2f}/oz RT -> total cost ${cost:6.2f} | net ${gross-cost:7.2f} "
          f"({(gross-cost)/5000*100:+.2f}%)")

print("\n=== Isolating the overnight-pending-order quirk ===")
overnight = [t for t in tr if t['day'] != t['entry_ts'][:10] or
             t['entry_ts'][:10] != max(d for d in ['2026.03.02'])] # placeholder
on = [t for t in tr if t['entry_ts'] == '2026.03.13 00:15:24.226'][0]
print(f"  Trade armed 2026.03.12 09:00 filled {on['entry_ts']} (before the 09:00 cancel).")
print(f"  Its P&L: {on['pnl']}  -> without it (orders cancelled at day end):")
alt = 5000.0
for t in tr:
    if t is on: continue
    alt += float(t['pnl'])
print(f"  14 trades, net ${alt-5000:.2f} ({(alt-5000)/50:.2f}%), final equity ${alt:.2f}")

print("\n=== Both-sides-touched check (did price hit the losing side too?) ===")
setups = list(csv.DictReader(open('results_realistic/daily_setups.csv')))
for s in setups:
    lo = float(s['sell_entry']); hi = float(s['buy_entry'])
    day = s['day']
    tb = ta = False
    for ts, ask, bid in ticks:
        if ts < s['setup_ts']: continue
        if ts[:10] != day: break
        if ask >= hi: tb = True
        if bid <= lo: ta = True
    print(f"  {day}: buy-stop touched={tb}  sell-stop touched={ta}  -> {s['outcome']}")
