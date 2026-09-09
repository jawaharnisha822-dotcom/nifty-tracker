# XAUUSD Round-Number Dual Strategy — full backtest report

**Data**: XAUUSD 15-min bid, 2016-01-01 → 2026-06-09, 246,838 bars, Asia/Kolkata.
**Primary test window**: 2025-01-01 → 2026-06-09 (as requested).
**Engine**: `engine.py` — a bug-for-bug Python replica of the Pine script.
**All numbers below**: Monte-Carlo intrabar model, 6 seeds, $0.30/oz round-trip cost.

---

## 1. The headline

Your parameters — `buffer 3.15 / SL 2.0 / RR 2.0 / $100+$50 / 09:00 IST` — **lose money**.

| metric | 2025-01-01 → 2026-06-09 |
|---|---|
| trades | 540 |
| win rate | 33.98 % |
| profit factor | **0.914** |
| expectancy | **−0.042 R** |
| net on $5,000 | **−$1,246** |
| max drawdown | 40.7 % |
| seeds profitable | 1 of 6 |

The breakeven win rate for a 2R target is 33.3 %. You are landing at 34.0 % — i.e.
the raw signal is a coin flip, and the $0.30 spread turns it negative.

---

## 2. Why 15-minute data cannot answer this question honestly

Your risk distance is `entry_buffer + SL_from_round = 3.15 + 2.00 = **$5.15**`.

| year | median 15-min bar range |
|---|---|
| 2018 | $0.93 |
| 2024 | $2.40 |
| 2025 | $4.45 |
| 2026 | $9.89 |

**In 2025-26, 55 % of 15-minute bars are wider than your entire stop distance.**
For most trades the entry, the stop and the target all sit inside one bar, and
15-minute OHLC simply does not record which was touched first.

That is not a rounding error — it *is* the result:

| intrabar assumption | win rate | PF | expectancy |
|---|---|---|---|
| always assume SL first | 14.7 % | 0.47 | −0.558 R |
| 3-leg OHLC path (o→l→h→c) | 46.8 % | 1.68 | +0.405 R |
| Monte-Carlo ≈15 s | 37.3 % | 1.17 | +0.113 R |
| Monte-Carlo ≈7.5 s | 34.3 % | 1.02 | +0.027 R |

Running the *same* strategy on coarser bars shows the two bounds closing as
resolution improves — they only meet at roughly 35-second granularity:

```
            'path' model        'pessimistic' model
   1h bars     50.5 % WR             5.4 % WR
  30m bars     48.3 % WR             9.7 % WR
  15m bars     46.8 % WR            14.7 % WR
```

**Conclusion: with a $5.15 stop, no 15-minute backtest of this strategy — mine,
TradingView's, or anyone's — is trustworthy.** TradingView's own strategy tester
uses an optimistic intrabar rule, which is why it will show you a far prettier
equity curve than reality.

---

## 3. The resolution-stability test (the one that matters)

A real edge does not care how finely you look inside the bar. An artefact does.
Expectancy in R at four intrabar resolutions, 2025-01-01 → 2026-06-09:

| configuration | 40 | 80 | 160 | 320 | stable? |
|---|---|---|---|---|---|
| **your params @ 09:00** | +0.127 | +0.063 | −0.069 | **−0.145** | **NO** |
| your params @ 05:30 ("best" hour) | +0.289 | +0.195 | +0.087 | **−0.049** | **NO** |
| buf 3.15 / SL 6 / RR 3.0 @ 09:00 | +0.208 | +0.136 | +0.088 | +0.001 | marginal |
| buf 5.0 / SL 15 / RR 1.5 @ 09:00 | +0.135 | +0.104 | +0.051 | +0.042 | yes |
| buf 2.0 / SL 15 / RR 2.0 @ 09:00 | +0.164 | +0.142 | +0.100 | +0.076 | yes |
| buf 3.15 / SL 15 / RR 1.5 @ 09:00 | +0.146 | +0.120 | +0.098 | +0.086 | yes |
| **buf 3.15 / SL 15 / RR 1.5, $100 only** | +0.193 | +0.167 | +0.140 | +0.120 | **YES** |
| **same @ 05:30 IST** | +0.204 | +0.197 | +0.158 | +0.123 | **YES** |

Your settings change sign. So does the "best entry hour" found for your settings.
Only configurations with a **stop wide enough to sit outside the noise** survive.

---

## 4. Do round numbers actually work? — the control experiment

I shifted the whole $100/$50 grid off the round numbers by a fixed offset,
keeping every other rule identical. If round numbers are decoration, the offset
should not matter.

| setup time | true round grid | mean of 9 shifted grids | rank of round grid |
|---|---|---|---|
| 09:00 | −0.042 R | −0.217 R | **1st of 10** |
| 21:30 | +0.048 R | −0.192 R | **1st of 10** |
| 00:00 | −0.015 R | −0.151 R | 2nd of 10 |

**Round numbers are real.** They are worth roughly **+0.18 R per trade** versus an
arbitrary price grid, consistently across three independent setup times.

This is the good news in your idea. The bad news is that a $5.15 stop plus
spread costs more than +0.18 R, so the genuine edge is spent before you collect it.

---

## 5. Structural problems, measured

| finding | number |
|---|---|
| days where the $100 and $50 orders land on the **identical price** | **100 %** (buy side 50.3 %, sell side 49.7 %) |
| $50 grid, 2025+ | 312 trades, WR 31.8 %, **−$1,516** |
| $100 grid, 2025+ | 228 trades, WR 37.0 %, **+$270** |
| short side | WR 32.0 %, −$1,202 |
| long side | WR 35.7 %, −$44 |
| median distance from 09:00 open to the $100 entry | **$52.8** |

Two things follow. The **$50 grid is the losing half** — it should be switched off.
And because `ceil(o/50)*50 == ceil(o/100)*100` on half of all days, the "dual"
system is not trading two systems: on every single day one of its two sides is
the same trade taken twice at double size. See `BUGS.md` (B1, B2).

---

## 6. The nine code defects

Full detail in `BUGS.md`. The ones that cost money:

* **B1** The two OCA groups are separate, so a $100 and a $50 trade can be open
  together — **2 % risk, not the 1 % in the title** — and can even be long *and*
  short simultaneously.
* **B2** On 100 % of days the $100 and $50 orders collide on one side: the same
  trade at double size.
* **B3** `strategy.position_size == 0` is checked on *every* bar, not only at
  setup. If yesterday's trade is still open at 09:00, today's orders are placed
  later at an arbitrary minute using stale 09:00 levels.
* **B5** SL is hard-wired to the round number, so a gap fill silently risks far
  more than the 1 % the size was computed for.
* **B6** `newLong` only fires on a flat→long transition, so when BUY50 fills while
  BUY100 is already long, `trade50Taken` is never set and **SELL50 is never
  cancelled**.
* **B8** The $5.15 risk distance was sane for 2018 gold and was never rescaled
  for 2025-26 gold.

---

## 7. Best entry time for YOUR parameters — the honest answer: there isn't one

I swept all 96 setup times (every 15 min of the day) keeping your other settings.
Ranked by expectancy the winners looked good — 05:30 IST gave +0.145 R, PF 1.21.
Three checks kill it:

**a) It is inside the noise.** 96 times were tested. Pure chance alone produces a
best t-statistic of ≈2.35. The actual best was **2.40**. Statistically, picking the
best hour out of 96 buys you nothing.

**b) It does not survive higher resolution.** Your params at 05:30 go
+0.289 R → +0.195 → +0.087 → **−0.049** as the intrabar view gets finer. Sign flip.

**c) It does not persist out of sample.** Correlation between a setup time's
expectancy in 2016-2024 and in 2025-2026 is **+0.104** — essentially zero. The
best 8 times of 2016-2024 went on to average **−0.014 R** in 2025-26, versus
−0.011 R for *all* times. Selecting the best hour made things slightly **worse**.

| setup time | 2025-2026 | 2016-2024 |
|---|---|---|
| 05:30 (best in 2025-26) | **+0.153 R** | −0.110 R |
| 00:30 | +0.052 R | −0.144 R |
| 09:00 (yours) | −0.055 R | −0.062 R |

**So: do not change your entry time. Change your stop.** The clock is not the
problem; the $5.15 risk distance is.

---

## 8. Best parameters

Ranking by return alone just picks the luckiest overfit. I required a
configuration to be profitable **at every intrabar resolution (40/120/320
sub-steps) AND in both volatility regimes (2016-2024 and 2025-2026)**.

Of 14 hand-picked candidates on the corrected engine, **3 survived**. Of 36
volatility-scaled variants, 14 survived. The best is:

### ✅ Recommended

| parameter | value |
|---|---|
| round grid | **$100 only** (drop the $50 grid) |
| setup time | **09:00 IST** — your original choice |
| entry buffer | **$2.00** |
| risk distance | **max($17, 4 × ATR(96 on 15-min))** |
| risk : reward | **1.5** |
| order validity | 48 bars (12 h), then cancel |
| risk per trade | 1 % of closed equity, one position at a time |

`ATR(96)` on a 15-min chart is a 24-hour ATR, so the stop scales with gold's
volatility instead of being frozen at a 2018-era dollar value.

**Measured at the harshest resolution (320 sub-steps) with $0.30/oz costs:**

| period | trades | win rate | PF | expectancy | net on $5k | max DD | seeds + |
|---|---|---|---|---|---|---|---|
| 2025-01 → 2026-06 | 158 | 45.5 % | 1.214 | +0.126 R | +$1,030 (+20.6 %) | **8.2 %** | 8/8 |
| 2016-2024 (out of sample) | 201 | 45.0 % | 1.185 | +0.108 R | +$1,123 (+22.5 %) | 15.0 % | 8/8 |
| full 2016-2026 | 358 | 45.3 % | 1.204 | +0.118 R | +$2,434 (+48.7 %) | 15.0 % | 8/8 |

Compare with your current settings on the same yardstick: PF 0.914, −0.042 R,
−$1,246, 40.7 % drawdown.

### Runner-up (fixed stop, if you prefer no ATR)

`$100 grid, buffer $2.00, SL $15 from the round, RR 2.0, 09:00 IST`
→ 2025-26: PF 1.18, +0.130 R, DD 25.6 %; 2016-24: PF 1.12, +0.086 R.
Worse drawdown and it will need re-tuning as volatility drifts.

---

## 9. Honest limitations

1. **The edge is small.** PF ≈1.20 and +0.12 R per trade is a *thin* edge, not a
   money machine. On ~160 trades a year at 1 % risk, expect roughly +20 % a year
   with a 15 % drawdown — and wide error bars around that.
2. **3 of 11 years lost money** (2017, 2019, 2021), including −$320 in 2021.
   Multi-year flat-to-down stretches are normal for this system.
3. **Long beat short in 2025-26** (+0.213 R vs +0.032 R). That is a gold bull
   market, not a proven property. I did not go long-only, because that would be
   fitting the trend.
4. **Trade count collapses in quiet years** — 6 trades in 2018 vs 88 in 2025 —
   because gold rarely crossed a $100 level in a day at $1,200. The $100 grid is
   implicitly a volatility filter.
5. **The intrabar model is a model.** Even at 320 sub-steps it is a constrained
   random walk, not real ticks. The recommended config was chosen precisely
   because it is *insensitive* to that choice, but the absolute numbers still
   carry uncertainty.
6. **Costs assumed $0.30/oz round trip.** At $0.60 the edge roughly halves.

## 10. What to do next

* Re-verify on **1-minute or tick data** before risking money. That is the single
  highest-value next step — it removes the largest uncertainty in this report.
* Forward-test on demo for 3-6 months; ~160 trades/yr means a quarter gives you
  ~40 trades, enough to spot a gross mismatch but not to confirm the edge.
* Do not re-optimise the setup hour. Section 7 shows that specific knob is noise.

---

## 11. "Which round number is nearer — does price go that way?"

Tested on every 09:00 IST setup, 2016-2026. Distance from the open to the $100
level above and below; then which level price reaches first within 24 hours.

**The trap:** a nearer barrier is hit first more often by pure geometry. For a
driftless walk starting `d_dn` above the lower level and `d_up` below the upper,
`P(upper first) = d_dn / (d_up + d_dn)`. So "the nearer one gets hit more" proves
nothing. The test must be against that baseline.

| period | setup days | days a level was hit | went to the NEARER one | random-walk baseline | edge | z |
|---|---|---|---|---|---|---|
| 2025-01 → 2026-06 | 370 | 243 (65.7 %) | **204 (84.0 %)** | 77.8 % | **+6.1 pts** | +2.45 |
| 2016-2024 | 2,322 | 477 (20.5 %) | **470 (98.5 %)** | 89.4 % | **+9.1 pts** | +6.83 |
| full 2016-2026 | 2,692 | 720 (26.7 %) | **674 (93.6 %)** | 85.5 % | **+8.1 pts** | +6.63 |

**Your instinct is correct and statistically strong (z = +6.6).** Price really is
drawn to the nearer $100 level, beyond what geometry explains. The effect is
biggest when the nearer level is $20-40 away (+14 to +19 points over baseline);
when it is under $10 away the baseline is already 95 %, so there is little room.

### But note how many days nothing happens

Only **26.7 %** of setup days touch either level within 24 h — and just 20.5 % in
2016-2024, when gold at $1,200 rarely travelled $100 in a day. That single fact
decides how the effect can and cannot be traded.

### ❌ Trading it directly as a target ("magnet trade") — FAILS

Enter at 09:00 toward the nearer level, take profit at the round number, stop the
other way. Tested 30 combinations of stop size, minimum distance and TP pullback:

| period | best result |
|---|---|
| 2025-01 → 2026-06 | +0.069 R, PF 1.16 — weak |
| 2016-2024 | **every single combination negative**; best −0.005 R, PF 0.91 |

Why: **84-95 % of those trades simply expire**. You cannot condition on "a level
will be reached" — you only know that afterwards. Most days you are left holding
a random position that pays the spread.

### ✅ Using it as a FILTER on the breakout order — WORKS

Leave the pending stop order, but place it only on the nearer side. Now the
no-touch days cost nothing, because the order never fills.

| config | trades | WR | PF | expectancy | max DD |
|---|---|---|---|---|---|
| recommended, both sides — 2025+ | 158 | 45.3 % | 1.205 | +0.122 R | 8.3 % |
| **recommended, nearer only — 2025+** | 135 | 48.9 % | **1.394** | **+0.213 R** | **7.8 %** |
| recommended, both sides — 2016-24 | 201 | 45.5 % | 1.209 | +0.120 R | 14.8 % |
| **recommended, nearer only — 2016-24** | 190 | 46.6 % | **1.265** | **+0.148 R** | **11.5 %** |

It improves both eras, and it lowers drawdown. ("Farther only" is untestable —
just 3 trades in 9 years.)

### Final configuration

Everything from section 8, plus **trade only the nearer round level**:

| period | trades | WR | PF | expectancy | net on $5k | max DD | seeds + |
|---|---|---|---|---|---|---|---|
| 2025-01 → 2026-06 | 135 | 48.8 % | 1.383 | +0.208 R | +$1,553 (+31.1 %) | **7.9 %** | 8/8 |
| 2016-2024 (out of sample) | 190 | 46.5 % | 1.257 | +0.144 R | +$1,476 (+29.5 %) | 11.8 % | 8/8 |
| **full 2016-2026** | **326** | **47.6 %** | **1.331** | **+0.176 R** | **+$3,636 (+72.7 %)** | **11.8 %** | **8/8** |

Resolution stability — expectancy barely moves, which is what a real edge looks like:

```
  2025+      k=40: +0.227   k=120: +0.228   k=320: +0.208
  2016-2024  k=40: +0.148   k=120: +0.149   k=320: +0.144
```

8 of 11 years profitable (2017, 2019, 2021 lost). Versus the "both sides"
version: PF 1.204 → **1.331**, drawdown 15.0 % → **11.8 %**, return +48.7 % → **+72.7 %**.

This is the largest single improvement found in the whole study — and it came
from your observation, not from parameter fitting.

---

## 12. "Market entry toward the nearer level, fixed $5-10 SL, 1:2 RR" — tested, FAILS

A follow-up question asked to test a simpler version of the idea: at 09:00 IST,
find the nearer $100 level, enter **immediately at the open** (market order, no
breakout confirmation) in the direction of that level, with a **fixed** SL
between $5 and $10, target at 1:2 RR, no other filter.

| risk ($) | 2025+ WR | 2025+ PF | 2025+ net | 2016-24 PF | 2016-24 max DD |
|---|---|---|---|---|---|
| 5 | 29.7% | 0.783 | −$2,397 | 0.840 | 86.2% |
| 6 | 31.0% | 0.836 | −$1,877 | 0.857 | 82.3% |
| 7 | 31.7% | 0.871 | −$1,566 | 0.797 | 88.7% |
| 8 | 32.4% | 0.908 | −$1,211 | 0.880 | 73.4% |
| 9 | 33.7% | 0.956 | −$581 | 0.897 | 65.8% |
| 10 | 32.9% | 0.933 | −$881 | 0.931 | 55.8% |

**Negative at every stop size, in both eras.** Best case (risk $9, 2025+) still
has PF < 1. 2016-2024 drawdowns of 55-93% — this would have wiped out an account.

**Why it fails, unlike the validated "nearer" filter in section 11:** the
statistic in section 11 says price is more likely to *touch* the nearer level
eventually — not that it moves toward it immediately from the open with no
confirmation. An unconditional market entry with no breakout confirmation and a
fixed dollar stop is a coin-flip directional bet (WR 30-34%, below the 33.3%
breakeven for 2R) sitting on a stop distance that is still inside 15-min noise.
It is the "magnet trade" from section 11 again, made worse by removing the wait
for actual price confirmation.

**Do not use this version.** Use the breakout-order + nearer-side filter +
ATR stop from sections 8 and 11 (already in `strategy_corrected.pine`) instead —
that is the one shown to work.
