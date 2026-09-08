# Defects in the original Pine script

Found while porting `XAUUSD Round Number | 10S | 100 + 50 Dual Strategy | 1% Risk`
to Python. Ordered by how much money each one can cost.

---

### B1 — "1% Risk" is really up to 2%, and the two trades can fight each other

`oca_name="ROUND100_ENTRY"` and `oca_name="ROUND50_ENTRY"` are **two separate OCA
groups**. The OCA only makes BUY100 cancel SELL100. Nothing stops a $100 trade and
a $50 trade being open at the same time, and `pyramiding=2` explicitly allows it.

Consequences:
* Risk per event is 2%, not the 1% the title claims.
* The two can be on *opposite sides* (long $100 + short $50). That is a hedge that
  can only lose the spread — both legs pay costs, and the SLs are only $5.15 apart.

### B2 — The $100 and $50 orders are frequently the *identical* price

If the reference open sits in the upper half of a $100 block, then
`ceil(o/50)*50 == ceil(o/100)*100`. Example: open 2360 → BUY100 = 2403.15 and
BUY50 = 2403.15. Same entry, same SL, same TP.

The script then takes **the same trade twice at double size**. This is not
diversification between two round-number systems; it is unintentional leverage,
and it happens on roughly half of all days (measured in `diagnose.py`).

### B3 — Orders are silently deferred to a random time of day

```pine
if setup100Active and not orders100Submitted and not trade100Taken and
   strategy.position_size == 0
```

This condition is re-evaluated on **every bar**, not only at the setup time. If
yesterday's trade is still open at 09:00, today's orders are *not* placed. They
are placed later — at whatever minute that old position happens to close —
using levels that were computed from the stale 09:00 open.

### B4 — Pending orders never expire

Levels are derived from the 09:00 open but the orders live until the *next* 09:00.
An order can trigger at 03:00 the following morning, 18 hours after the reference
price that justified it.

### B5 — Gap fills silently break the 1% risk

`buySL100` is hard-wired to `upper100 - slFromRound`. Position size was computed
assuming risk = `entryBuffer + slFromRound` = $5.15. If price **gaps** through the
stop and fills at, say, $8 above the round number, the real distance to that fixed
SL is ~$10 — the trade now risks ~2% while sized for 1%. Gold gaps every Monday.

### B6 — The fill detector misidentifies which order filled

```pine
string lastEntry = strategy.opentrades.entry_id(strategy.opentrades - 1)
```

plus

```pine
newLong = strategy.position_size > 0 and strategy.position_size[1] <= 0
```

`newLong` only fires on a transition **from flat/short to long**. When BUY100 is
already long and BUY50 fills on a later bar, position_size goes from +qty to
+2·qty — no transition, so `newLong` is false, `trade50Taken` is never set, and
**SELL50 is never cancelled**. That stale short can fire later and flip the book.

### B7 — Position size depends on the other trade's floating P&L

`strategy.equity` includes open-trade P&L. With two concurrent trades (B1), the
size of the second trade moves with the unrealised P&L of the first.

### B8 — The stop is inside the noise, which is why it loses

The economic defect, not a coding one. Risk distance is fixed at
`3.15 + 2.00 = $5.15`. Median 15-minute XAUUSD range:

| year | median 15m range |
|---|---|
| 2018 | $0.93 |
| 2024 | $2.40 |
| 2025 | $4.45 |
| 2026 | $9.89 |

In 2025-26 **55% of 15-minute bars are wider than the entire stop distance**. The
trade is decided by sub-minute noise, not by the round-number thesis. The
parameters were reasonable for 2018 gold; they were never re-scaled for 2025 gold.

### B9 — Redundant `strategy.exit` re-issued every bar

The two "ACTIVE EXITS" blocks re-issue `strategy.exit` for all four entry ids on
every bar where a position exists, including for entries that do not exist.
Harmless in the emulator, but it hides B5 by making the brackets look dynamic
when they are in fact static constants.
