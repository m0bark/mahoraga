"""With 4,600 analysts tracked, what does the BEST one look like if not a
single one of them has any skill?

Uses the measured inputs, not guesses:
  base rate for covered stocks, 2009+   ~60%
  ~45% of ratings are never scored (Holds excluded)
  ratings cluster in time and sector -> effective n ~= headline/8
"""
from __future__ import annotations
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np

rng = np.random.default_rng(11)
N_ANALYSTS = 4600
BASE = 0.60
DEFF = 8.0          # measured design effect from clustering

# rating counts across a real leaderboard are wide; model as lognormal
# centred near 300 scored ratings, floor 40
counts = np.clip(rng.lognormal(mean=np.log(300), sigma=0.8,
                               size=(3000, N_ANALYSTS)), 40, 4000)
ess = counts / DEFF                       # effective independent observations
# each analyst's observed hit rate under ZERO skill
obs = rng.binomial(np.round(ess).astype(int), BASE) / np.round(ess)
best = obs.max(axis=1)
p99 = np.percentile(obs, 99.9, axis=1)

print(f"{N_ANALYSTS:,} analysts, ZERO skill, base rate {BASE:.0%}, "
      f"clustering design effect {DEFF:.0f}x\n")
print(f"  best hit rate seen by pure luck : {best.mean()*100:.1f}%  "
      f"(90% of runs land {np.percentile(best,5)*100:.1f}-{np.percentile(best,95)*100:.1f}%)")
print(f"  99.9th percentile analyst       : {p99.mean()*100:.1f}%")

# how many SD above base is the luckiest, in z terms
z_expected = np.sqrt(2 * np.log(N_ANALYSTS)) - (
    np.log(np.log(N_ANALYSTS)) + np.log(4 * np.pi)) / (2 * np.sqrt(2 * np.log(N_ANALYSTS)))
print(f"\n  expected z of the single luckiest of {N_ANALYSTS:,}: +{z_expected:.2f} SD")
print(f"  best clustered z actually MEASURED on the leaderboard: +1.61")
print(f"\n  => the observed top performer is {z_expected-1.61:.2f} SD WEAKER than")
print(f"     a leaderboard of {N_ANALYSTS:,} pure coin-flippers would produce.")

print("\n--- what hit rate WOULD be convincing? ---")
for n_scored in (200, 500, 1000):
    e = n_scored / DEFF
    se = np.sqrt(BASE * (1 - BASE) / e)
    need = BASE + z_expected * se
    print(f"  with {n_scored:,} scored ratings (ESS {e:.0f}): "
          f"need > {need*100:.1f}% to beat the luck-max")
