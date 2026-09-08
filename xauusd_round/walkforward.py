"""Out-of-sample validation: is the 'best setup time' a real edge or data mining?"""
from sweep import *
if __name__ == "__main__":
    grid = [((("hour", h), ("min", m)), dict(setup_hour=h, setup_minute=m))
            for h in range(24) for m in (0, 15, 30, 45)]

    print("=== IN-SAMPLE  2016-2024 ===", flush=True)
    old = sweep(grid, period=("2016-01-01", "2025-01-01"))
    old.to_csv("results/wf_2016_2024.csv", index=False)
    new = pd.read_csv("results/sweep_hour.csv")          # 2025+ already computed

    m = old.merge(new, on=["hour", "min"], suffixes=("_old", "_new"))
    m["key"] = m.apply(lambda r: f"{int(r.hour):02d}:{int(r['min']):02d}", axis=1)

    print("\n### Best 8 on 2016-2024, and how they then did on 2025-2026")
    print(m.nlargest(8, "exp_r_old")[["key","trades_old","exp_r_old","pf_old",
                                      "trades_new","exp_r_new","pf_new"]]
          .round(3).to_string(index=False))
    print("\n### Best 8 on 2025-2026, and how they had done on 2016-2024")
    print(m.nlargest(8, "exp_r_new")[["key","trades_new","exp_r_new","pf_new",
                                      "trades_old","exp_r_old","pf_old"]]
          .round(3).to_string(index=False))
    c = m[["exp_r_old", "exp_r_new"]].corr().iloc[0, 1]
    print(f"\n### Correlation of expectancy across the two eras: {c:+.3f}")
    print("    (>0 = setup-time ranking persists; ~0 = the ranking is noise)")
    top_old = m.nlargest(8, "exp_r_old")
    print(f"    Top-8 of 2016-2024 averaged {top_old.exp_r_new.mean():+.3f}R in 2025-26 "
          f"vs {m.exp_r_new.mean():+.3f}R for all times")
