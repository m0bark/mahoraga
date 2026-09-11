"""If you scan N analysts and keep the best, how good does the BEST one look
when NONE of them has any skill at all?

Every analyst here is a coin-flipper: each call succeeds with probability
equal to the measured base rate (70.1% of stocks rise over 12 months).
Nobody has skill. We then do what the ranking sites do -- sort and take the
top -- and look at what the winner's record looks like.
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np

BASE = 0.701          # measured: share of stocks with positive 12m return
rng = np.random.default_rng(7)

print(f"base rate = {BASE:.1%}  (measured, 23,948 stock-years 2005-2025)\n")
print("ZERO-SKILL analysts. Best record you would see anyway:\n")
print(f"{'analysts scanned':>18}{'calls each':>12}{'best win rate':>15}{'99th pct':>10}")
for n_analysts in (100, 1_000, 5_000, 20_000):
    for calls in (100, 900):
        wins = rng.binomial(calls, BASE, size=(2000, n_analysts)) / calls
        best = wins.max(axis=1)
        print(f"{n_analysts:>18,}{calls:>12}{best.mean()*100:>14.1f}%"
              f"{np.percentile(best, 99)*100:>9.1f}%")

print("\n--- how many SD above base is a given record, at 900 calls? ---")
se = np.sqrt(BASE * (1 - BASE) / 900)
print(f"standard error at 900 calls = {se*100:.2f} percentage points")
for rate in (0.72, 0.75, 0.78, 0.80, 0.85):
    z = (rate - BASE) / se
    # prob at least one of N zero-skill analysts beats this
    from math import erfc, sqrt
    p_one = 0.5 * erfc(z / sqrt(2))
    for n in (1_000, 20_000):
        exp_count = p_one * n
        print(f"  {rate:.0%} win rate = {z:+.1f} SD | "
              f"expected # of {n:,} zero-skill analysts hitting it: {exp_count:,.1f}")
    print()

print("--- and the part win rate cannot tell you ---")
for wr, w, l in [(0.80, 0.05, -0.25), (0.80, 0.10, -0.40), (0.62, 0.26, -0.34)]:
    ev = wr * w + (1 - wr) * l
    print(f"  win rate {wr:.0%}, avg win {w:+.0%}, avg loss {l:+.0%} "
          f"-> expectancy {ev:+.2%} per trade")
