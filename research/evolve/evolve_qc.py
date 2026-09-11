# EVOLUTIONARY SEARCH ON POINT-IN-TIME DATA — paste into research.ipynb
# AFTER the cell that built px, memb, month_ends, fwd_ret.
# Free research node. No backtest token.
#
# WHY THIS VERSION EXISTS
# The local GA converged on "high momentum + high volatility" and scored
# +0.166 per quarter out-of-sample -- 84%/yr, which is not a strategy, it is
# a tell. It had found the survivorship bias in a 99-name survivor universe
# and maximised it. Train/valid/test splits did nothing, because all three
# slices shared the same contaminated ticker list. Out-of-sample in TIME
# does not fix in-sample in UNIVERSE.
#
# TWO CHANGES THAT MAKE THIS HONEST
# 1. PIT membership: an organism may only pick names that were actually in
#    the universe on that date (memb), so dead companies are pickable and
#    future winners are not pickable early.
# 2. Fitness is EXCESS vs the eligible cross-section that day, not raw
#    return. Raw return rewards being invested in a bull market; excess
#    rewards only selection. This is the difference between measuring the
#    period and measuring the organism.
#
# 2023+ is never touched. It stays sealed as the family holdout.

import numpy as np, pandas as pd

POP, GENS, ELITE, N_RULES, MIN_PICKS, MIN_WINDOWS = 60, 30, 12, 3, 5, 8

feats = {
    "drawdown": px / px.rolling(252).max() - 1,
    "mom20":    px / px.shift(20) - 1,
    "mom126":   px / px.shift(126) - 1,
    "vol60":    px.pct_change().rolling(60).std() * np.sqrt(252),
    "d200":     px / px.rolling(200).mean() - 1,
    "rel_vol":  px.pct_change().rolling(20).std() / px.pct_change().rolling(120).std(),
}
FEATURES = list(feats)

dates = [d for d in month_ends if d in px.index and d in fwd_ret.index]
F = {k: v.loc[dates].to_numpy(dtype="float32") for k, v in feats.items()}
M = memb.loc[dates].to_numpy()
R = fwd_ret.loc[dates].to_numpy(dtype="float32")
dts = pd.DatetimeIndex(dates)

tr = np.where(dts < "2016-01-01")[0][13:]          # drop warm-up
va = np.where((dts >= "2016-01-01") & (dts < "2020-01-01"))[0]
te = np.where(dts >= "2020-01-01")[0][:-2]
print(f"{len(dates)} month-ends | train {len(tr)} valid {len(va)} test {len(te)}")
print(f"eligible names per date: median {M.sum(axis=1)[tr].mean():.0f}\n")


def score(org, idx):
    """Excess forward return vs the eligible PIT cross-section that date."""
    out = []
    for i in idx:
        base = M[i] & np.isfinite(R[i])
        if base.sum() < 50:
            continue
        m = base.copy()
        for f, op, thr in org:
            v = F[f][i]
            m &= np.isfinite(v) & ((v < thr) if op == "<" else (v > thr))
        if m.sum() < MIN_PICKS:
            continue
        out.append(float(R[i][m].mean() - R[i][base].mean()))
    return (float(np.mean(out)), len(out)) if len(out) >= MIN_WINDOWS else (-9.9, len(out))


def random_org(rng):
    return [(FEATURES[rng.integers(len(FEATURES))],
             "<" if rng.random() < 0.5 else ">",
             float(rng.normal(0, 0.5))) for _ in range(N_RULES)]


def mutate(org, rng):
    c = [list(g) for g in org]
    for g in c:
        r = rng.random()
        if r < 0.15:
            g[0] = FEATURES[rng.integers(len(FEATURES))]
        elif r < 0.30:
            g[1] = "<" if g[1] == ">" else ">"
        elif r < 0.70:
            g[2] = float(g[2] + rng.normal(0, 0.15))
    return [tuple(g) for g in c]


rng = np.random.default_rng(42)
pop = [random_org(rng) for _ in range(POP)]
hist = []
print(f"{'gen':<5}{'best TRAIN':>12}{'its VALID':>12}{'gap':>10}")
for g in range(GENS):
    sc = sorted(((score(o, tr)[0], o) for o in pop), key=lambda x: -x[0])
    elite = [o for _, o in sc[:ELITE]]
    bt = sc[0][0]
    bv = score(sc[0][1], va)[0]
    hist.append((g, bt, bv))
    print(f"{g:<5}{bt:11.4f}{bv:11.4f}{bt - bv:9.4f}")
    kids = list(elite)
    while len(kids) < POP:
        a, b = elite[rng.integers(ELITE)], elite[rng.integers(ELITE)]
        kids.append(mutate([a[i] if rng.random() < 0.5 else b[i]
                            for i in range(N_RULES)], rng))
    pop = kids

h = pd.DataFrame(hist, columns=["gen", "train", "valid"])
h = h[h.valid > -9]                     # drop failure sentinels, not scores
print(f"\nTRAIN  first5 {h.train.head().mean():+.4f} -> last5 {h.train.tail().mean():+.4f}")
print(f"VALID  first5 {h.valid.head().mean():+.4f} -> last5 {h.valid.tail().mean():+.4f}")

best = sorted(((score(o, tr)[0], o) for o in pop), key=lambda x: -x[0])[0][1]
print("\nfittest organism:")
for f, op, thr in best:
    print(f"   {f} {op} {thr:+.3f}")
ts, tn = score(best, te)
print(f"\n  train {score(best, tr)[0]:+.4f}   valid {score(best, va)[0]:+.4f}"
      f"   TEST {ts:+.4f}  ({tn} windows)")
print("\nSCALE CHECK: these are EXCESS returns per ~63 trading days.")
print("+0.02 = 2pp per quarter over the universe ~ 8pp/yr. Plausible.")
print("+0.15 = 84%/yr of pure selection alpha. Not plausible -- that is what")
print("the local survivorship-biased run produced. If this run lands near")
print("zero, that IS the honest answer and the local one was the illusion.")
print("\nTEST is now spent. 2023+ remains sealed.")
