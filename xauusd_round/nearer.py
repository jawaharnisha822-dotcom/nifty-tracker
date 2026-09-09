"""
"At 09:00 IST, which $100 round number is NEARER - the one above or below?
 Does price then move in THAT direction? On how many days?"

The catch: a nearer barrier is hit first more often by pure geometry. For a
driftless walk starting d_dn above the lower level and d_up below the upper,
    P(touch upper first) = d_dn / (d_up + d_dn)
So 'the nearer one gets hit more' proves nothing on its own. The real question
is whether it happens MORE OFTEN THAN THAT BASELINE predicts.
"""
import numpy as np, pandas as pd
from engine import load_data
from sweep import CSV

HOUR, MINUTE, STEP = 9, 0, 100.0

def build(df, horizon_bars=96):
    o_, h_, l_, c_ = (df[k].to_numpy(float) for k in "ohlc")
    setup = np.where((df.dt.dt.hour == HOUR) & (df.dt.dt.minute == MINUTE))[0]
    rows = []
    for si in setup:
        ref = o_[si]
        up = np.ceil(ref / STEP) * STEP
        dn = np.floor(ref / STEP) * STEP
        if up == dn:
            continue
        d_up, d_dn = up - ref, ref - dn
        end = min(si + 1 + horizon_bars, len(df))
        first = None
        for i in range(si + 1, end):
            hit_u, hit_d = h_[i] >= up, l_[i] <= dn
            if hit_u and hit_d:                       # same bar: use path order
                first = "up" if c_[i] >= o_[i] else "dn"
                # an up bar travels o->l->h, so the LOW side is reached first
                first = "dn" if c_[i] >= o_[i] else "up"
                break
            if hit_u:
                first = "up"; break
            if hit_d:
                first = "dn"; break
        rows.append(dict(i=si, dt=df.dt.iloc[si], ref=ref, up=up, dn=dn,
                         d_up=d_up, d_dn=d_dn,
                         nearer="up" if d_up < d_dn else "dn",
                         near_dist=min(d_up, d_dn), far_dist=max(d_up, d_dn),
                         first=first,
                         p_up_baseline=d_dn / (d_up + d_dn)))
    return pd.DataFrame(rows)

def report(t, label):
    res = t[t.first.notna()].copy()
    res["went_nearer"] = res.first == res.nearer
    # baseline probability that the NEARER side is touched first
    res["p_near_base"] = np.where(res.nearer == "up",
                                  res.p_up_baseline, 1 - res.p_up_baseline)
    n = len(res)
    actual = res.went_nearer.mean()
    base = res.p_near_base.mean()
    # binomial SE using per-day baselines (Poisson-binomial)
    se = np.sqrt((res.p_near_base * (1 - res.p_near_base)).sum()) / n
    z = (actual - base) / se
    print(f"\n=== {label} ===")
    print(f"  days with a setup            : {len(t)}")
    print(f"  days where SOME level was hit: {n}  ({n/len(t)*100:.1f}%)")
    print(f"  -> went to the NEARER level first : {res.went_nearer.sum()} "
          f"({actual*100:.1f}%)")
    print(f"  -> random-walk baseline says      : {base*100:.1f}%")
    print(f"  -> edge over baseline             : {(actual-base)*100:+.1f} pts   "
          f"(z = {z:+.2f})")
    print(f"     {'SIGNIFICANT' if abs(z)>2 else 'NOT significant (|z|<2)'}")
    # by how near the near level is
    res["bucket"] = pd.cut(res.near_dist, [0, 10, 20, 30, 40, 50],
                           labels=["0-10", "10-20", "20-30", "30-40", "40-50"])
    g = res.groupby("bucket", observed=True).agg(
        days=("went_nearer", "size"), went_nearer_pct=("went_nearer", lambda x: x.mean()*100),
        baseline_pct=("p_near_base", lambda x: x.mean()*100))
    g["edge"] = (g.went_nearer_pct - g.baseline_pct).round(1)
    print("\n  by distance to the nearer level ($):")
    print(g.round(1).to_string())
    return res

if __name__ == "__main__":
    df = load_data(CSV)
    for tag, a, b in [("2025-01-01 -> 2026-06-09", "2025-01-01", "2026-12-31"),
                      ("2016-2024", "2016-01-01", "2025-01-01"),
                      ("FULL 2016-2026", "2016-01-01", "2026-12-31")]:
        d = df[(df.dt >= a) & (df.dt < b)].reset_index(drop=True)
        t = build(d)
        r = report(t, f"{tag}  (24h horizon)")
        if "FULL" in tag:
            r.to_csv("results/nearer_days.csv", index=False)
