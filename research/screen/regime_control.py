"""Critical control: does the panic effect survive when the RANDOM arm is
also conditioned on the same market regime? If random entries during a
panic do just as well, the 'edge' is only high-beta names rebounding
harder than SPY -- which is beta you can buy for free, not selection skill.
"""
import sys, io, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
S = pd.read_csv("research/screen/backtest_entries.csv", parse_dates=["date"])
R = pd.read_csv("research/screen/backtest_random.csv", parse_dates=["date"])
print("SIGNAL vs RANDOM, split by market regime at entry (excess return vs SPY)\n")
print(f"{'regime':<24}{'arm':<9}{'n':>6}{'60d':>9}{'250d':>9}")
for lo, hi, lab in [(-99, -0.12, "SPY <= -12% (panic)"), (-0.12, -0.05, "SPY -5..-12%"),
                    (-0.05, 1, "SPY > -5% (calm)")]:
    for nm, d in (("signal", S), ("random", R)):
        s = d[(d.spy_dd > lo) & (d.spy_dd <= hi)]
        if len(s) > 20:
            print(f"{lab:<24}{nm:<9}{len(s):6d}{s.x60.mean()*100:8.2f}%{s.x250.mean()*100:8.2f}%")
    print()
for h in (60, 250):
    p, q = S[S.spy_dd <= -0.12], R[R.spy_dd <= -0.12]
    d = p[f"x{h}"].mean() - q[f"x{h}"].mean()
    se = np.sqrt(p[f"x{h}"].var()/len(p) + q[f"x{h}"].var()/len(q))
    print(f"PANIC-ONLY EDGE (signal - random), {h}d: {d*100:+.2f}%  SE {se*100:.2f}%  t = {d/se:+.2f}")
