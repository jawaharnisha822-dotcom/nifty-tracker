from sweep import *
if __name__ == "__main__":
    grid = []
    for hh in range(24):
        for mi in (0, 15, 30, 45):
            grid.append(((("hour", hh), ("min", mi)),
                         dict(setup_hour=hh, setup_minute=mi)))
    df = sweep(grid)
    df["key"] = df.apply(lambda r: f"{int(r['hour']):02d}:{int(r['min']):02d}", axis=1)
    df.to_csv("results/sweep_hour.csv", index=False)
    show = ["key","trades","win_rate","pf","exp_r","net","dd","pos_frac"]
    print("### BEST setup times (user's other params: buf3.15 sl2.0 rr2.0 $100+$50)")
    print(fmt(df, "exp_r", 15, show))
    print("\n### WORST")
    print(fmt(df, "exp_r", 200, show).split(chr(10))[0])
    print(chr(10).join(fmt(df, "exp_r", 200, show).split(chr(10))[-8:]))
    print("\n### user's own 09:00")
    print(df[df.key == "09:00"][show].round(3).to_string(index=False))
