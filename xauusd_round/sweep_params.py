from sweep import *
if __name__ == "__main__":
    BUF = [1.0, 2.0, 3.15, 5.0, 8.0, 12.0]
    SL  = [1.0, 2.0, 4.0, 6.0, 10.0, 15.0]
    RR  = [1.0, 1.5, 2.0, 3.0]
    grid = []
    for b, s, r in itertools.product(BUF, SL, RR):
        grid.append(((("buf", b), ("sl", s), ("rr", r)),
                     dict(entry_buffer=b, sl_from_round=s, rr=r)))
    print(f"combos: {len(grid)}", flush=True)
    df = sweep(grid)
    df["risk"] = df.buf + df.sl
    df.to_csv("results/sweep_params_coarse.csv", index=False)
    show = ["buf","sl","risk","rr","trades","win_rate","pf","exp_r","net","dd","pos_frac"]
    print("### TOP 25 by expectancy (09:00 IST, $100+$50, both directions)")
    print(fmt(df, "exp_r", 25, show))
    print("\n### TOP 15 by net $ (compounded)")
    print(fmt(df, "net", 15, show))
