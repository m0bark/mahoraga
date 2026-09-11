"""Evolutionary strategy search -- organisms that must earn to reproduce.

    python research/evolve/evolve.py

Each organism is a set of screening rules. Every generation:
    * it is scored on the TRAIN period
    * the top survivors reproduce (crossover + mutation)
    * the rest die

THE TRAP, AND WHY THIS PRINTS TWO NUMBERS
A GA maximises whatever you score it on. Score it on the training period
and it will memorise that period's noise -- perfectly, effortlessly, and
with a beautiful equity curve. That is not fitness, it is taxidermy.

So every generation reports BOTH:
    train  -- what selection optimised (always improves; means nothing)
    valid  -- a later period no organism was ever selected on
              (the only number that carries information)

If train climbs while valid stays flat, the population is memorising. That
is the expected outcome, and watching the gap open is the point of running
this. If valid climbs WITH train, you have a candidate worth a
pre-registered QC run -- not a strategy, a candidate.

A third slice, TEST, is held back and scored once at the very end for the
single best organism. Look at it once. Looking twice makes it a validation
set, and then you have nothing left.

Survivorship note: local ticker list, so absolute returns are inflated.
Does not matter here -- the train-vs-valid GAP is the measurement, and both
slices carry the same bias.
"""
from __future__ import annotations

import io
import sys
import warnings

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

U = ("AAPL MSFT GOOGL AMZN META NVDA AMD AVGO TSM MU INTC QCOM TXN ADI MRVL LRCX AMAT "
     "KLAC NXPI ON MCHP SWKS TER MPWR ANET ADBE CRM NOW ORCL PANW ZS NET DDOG TEAM WDAY "
     "INTU ADSK SNPS CDNS FTNT SHOP FSLR ENPH RUN PLUG NEE BE TSLA GM F ALB MP VRT ETN "
     "PWR NVT MOD CEG VST ISRG DXCM JNJ XOM JPM PG KO PEP WMT CVX MRK PFE T VZ CSCO IBM "
     "MCD NKE HD LOW CAT DE MMM GE BA HON UPS UNH ABT LLY BMY AMGN GILD COST TGT SBUX "
     "DIS CMCSA DAL LUV GS MS BAC C WFC AXP USB PNC SCHW").split()

POP, GENS, ELITE, N_RULES = 60, 30, 12, 3
HOLD = 63
FEATURES = ["drawdown", "mom20", "mom126", "vol60", "d200", "rel_vol"]


def build_features(px: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "drawdown": px / px.rolling(252).max() - 1,
        "mom20": px / px.shift(20) - 1,
        "mom126": px / px.shift(126) - 1,
        "vol60": px.pct_change().rolling(60).std() * np.sqrt(252),
        "d200": px / px.rolling(200).mean() - 1,
        "rel_vol": px.pct_change().rolling(20).std()
                   / px.pct_change().rolling(120).std(),
    }


def random_org(rng) -> list[tuple[str, str, float]]:
    return [(FEATURES[rng.integers(len(FEATURES))],
             "<" if rng.random() < 0.5 else ">",
             float(rng.normal(0, 0.5)))
            for _ in range(N_RULES)]


def mutate(org, rng):
    child = [list(g) for g in org]
    for g in child:
        r = rng.random()
        if r < 0.15:
            g[0] = FEATURES[rng.integers(len(FEATURES))]
        elif r < 0.30:
            g[1] = "<" if g[1] == ">" else ">"
        elif r < 0.70:
            g[2] = float(g[2] + rng.normal(0, 0.15))
    return [tuple(g) for g in child]


def crossover(a, b, rng):
    return [a[i] if rng.random() < 0.5 else b[i] for i in range(N_RULES)]


def score(org, feats, fwd, dates) -> tuple[float, int]:
    """Mean forward return of names passing every rule. Returns (score, n)."""
    picks = []
    for dt in dates:
        mask = None
        for f, op, thr in org:
            fv = feats[f].loc[dt]
            m = (fv < thr) if op == "<" else (fv > thr)
            mask = m if mask is None else (mask & m)
        sel = mask[mask.fillna(False)].index
        if len(sel) < 5:                     # too few names = not a strategy
            continue
        r = fwd.loc[dt, sel].dropna()
        if len(r) >= 5:
            picks.append(r.mean())
    if len(picks) < 8:
        return -9.9, len(picks)
    return float(np.mean(picks)), len(picks)


def main() -> None:
    px = yf.download(U, start="2010-01-01", end="2026-08-28",
                     auto_adjust=True, progress=False, threads=True)["Close"]
    px = px.dropna(axis=1, thresh=int(len(px) * 0.6))
    feats = build_features(px)
    fwd = px.shift(-HOLD) / px - 1

    me = (px.index.to_series().groupby([px.index.year, px.index.month])
            .last().values)
    me = [d for d in me if d in px.index]
    train = [d for d in me if pd.Timestamp(d) < pd.Timestamp("2018-01-01")]
    valid = [d for d in me if pd.Timestamp("2018-01-01") <= pd.Timestamp(d)
             < pd.Timestamp("2022-01-01")]
    test = [d for d in me if pd.Timestamp(d) >= pd.Timestamp("2022-01-01")]
    train = train[13:]                       # drop warm-up months
    test = test[:-3]                          # need forward returns to exist
    print(f"universe {px.shape[1]} names | train {len(train)}mo "
          f"valid {len(valid)}mo test {len(test)}mo (test read ONCE at the end)\n")

    rng = np.random.default_rng(42)
    pop = [random_org(rng) for _ in range(POP)]
    history = []
    print(f"{'gen':<5}{'best TRAIN':>12}{'its VALID':>12}{'pop VALID avg':>15}"
          f"{'gap':>9}")
    for g in range(GENS):
        scored = []
        for o in pop:
            s, n = score(o, feats, fwd, train)
            scored.append((s, o))
        scored.sort(key=lambda x: -x[0])
        elite = [o for _, o in scored[:ELITE]]
        best_train = scored[0][0]
        best_valid, _ = score(scored[0][1], feats, fwd, valid)
        pop_valid = np.mean([score(o, feats, fwd, valid)[0]
                             for o in elite if score(o, feats, fwd, valid)[0] > -9])
        history.append((g, best_train, best_valid))
        print(f"{g:<5}{best_train:11.4f}{best_valid:11.4f}"
              f"{pop_valid:14.4f}{best_train - best_valid:9.4f}")

        children = list(elite)
        while len(children) < POP:
            a, b = elite[rng.integers(ELITE)], elite[rng.integers(ELITE)]
            children.append(mutate(crossover(a, b, rng), rng))
        pop = children

    h = pd.DataFrame(history, columns=["gen", "train", "valid"])
    first, last = h.iloc[:5], h.iloc[-5:]
    print(f"\nfirst 5 generations: train {first.train.mean():+.4f}  "
          f"valid {first.valid.mean():+.4f}")
    print(f"last  5 generations: train {last.train.mean():+.4f}  "
          f"valid {last.valid.mean():+.4f}")
    print(f"TRAIN improved by {last.train.mean() - first.train.mean():+.4f}")
    print(f"VALID improved by {last.valid.mean() - first.valid.mean():+.4f}")
    print("\nIf TRAIN moved and VALID did not, evolution memorised noise.")
    print("That is the expected result and it is the point of the run.")

    best = sorted([(score(o, feats, fwd, train)[0], o) for o in pop],
                  key=lambda x: -x[0])[0][1]
    print("\nfittest organism:")
    for f, op, thr in best:
        print(f"   {f} {op} {thr:+.3f}")
    ts, tn = score(best, feats, fwd, test)
    vs, _ = score(best, feats, fwd, valid)
    print(f"\n  train {score(best, feats, fwd, train)[0]:+.4f}"
          f"   valid {vs:+.4f}   TEST {ts:+.4f}  ({tn} windows)")
    print("\nTEST is now spent. Do not score another organism on it.")


if __name__ == "__main__":
    main()
