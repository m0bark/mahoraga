"""Does an analyst's rating DATE carry information? Self-matched event study.

    python research/analysts/revision_study.py

WHAT KILLED THE PREVIOUS VERSION

event_study.py drew its random-entry control from the entire 15-month price
history while the events themselves sat in two narrow calendar bands. So
its "edge" was (date selection) + (event-period regime - full-period
regime), and on that data the regime term was 8x larger than the selection
term and carried the opposite sign. It printed -18.49% with t=-2.67 and
read as "the analyst's dates destroyed value." Calendar-matched, the same
events came out +3.3pp AHEAD. The significant result was entirely an
artifact of an unmatched control.

THE DESIGN THAT CANNOT HAVE THAT BUG

Every event is compared to entries into THE SAME STOCK within a +/-W
trading-day band around the event date. Same stock, same weeks, same
regime, same sector -- the only difference is WHICH DAY was chosen.
Whatever the stock was going to do that month is differenced out. No
benchmark is needed, and therefore no benchmark can be wrong.

    f[i]    = v[i+h]/v[i] - 1                 forward return from day i
    ctrl[i] = mean(f[i-W .. i+W]) EXCLUDING i  what a nearby day paid
    edge[i] = f[i] - ctrl[i]                   what the DATE was worth

The event's own return is removed from its control window; leaving it in
would shrink every edge by a factor (2W)/(2W+1) toward zero.

W is not a parameter to choose after seeing the answer, so every W in
{10, 21, 42, 63} is printed. A sign that flips across W IS the finding.

INFERENCE IS BY RANDOMIZATION, NOT BY t

Events cluster: one analyst rates eight semis inside five weeks and those
63-day windows overlap 83%. A paired iid t treated that as n=10 and gave
|t|=2.67 where the honest figure was 1.09 -- design effect 5.7. So the null
is built by BLOCK-SHIFTING: every event belonging to one analyst moves by a
single shared random offset, preserving within-analyst spacing and the
cross-name correlation. p = fraction of shuffles whose |mean edge| beats
the real one.

Vectorised: ctrl is a centred rolling mean over the forward-return array,
so scoring 11,570 events costs one pass per symbol rather than 400 draws
per event, and a permutation is an index shift.

AUDIT FIXES CARRIED IN
  * `fwd(...) or np.nan` turned a real 0.0 return into NaN (0.0 is falsy).
  * searchsorted clamps to 0 for an event predating the price history,
    fabricating a return -- such events are dropped and counted.
  * Every attempted test is counted; the Bonferroni threshold is printed.
"""
from __future__ import annotations

import csv
import io
import os
import sys
import warnings

_OUT = io.TextIOWrapper(open(sys.stdout.fileno(), "wb", closefd=False),
                        encoding="utf-8", errors="replace")


def say(*a) -> None:
    print(*a, file=_OUT)
    _OUT.flush()


warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

TAPE = "research/analysts/ratings_tape.csv"
HORIZONS = [21, 63]
BANDS = [10, 21, 42, 63]
N_PERM = 2000
MIN_N = 30
UP, DOWN = ("Upgrade", "Upgrades"), ("Downgrade", "Downgrades")


def load() -> pd.DataFrame:
    df = pd.DataFrame(list(csv.DictReader(open(TAPE, encoding="utf-8"))))
    df["edate"] = pd.to_datetime(df["date"], format="%b %d, %Y", errors="coerce")
    df = df.dropna(subset=["edate"])
    df = df.drop_duplicates(subset=["symbol", "analyst", "date", "action"])
    return df.reset_index(drop=True)


def band_ctrl(f: np.ndarray, w: int) -> np.ndarray:
    """Centred mean of f over +/-w, EXCLUDING the centre point itself."""
    s = pd.Series(f)
    win = 2 * w + 1
    tot = s.rolling(win, center=True, min_periods=w).sum()
    cnt = s.notna().rolling(win, center=True, min_periods=w).sum()
    # remove the centre observation from its own control window
    tot = tot - s.fillna(0.0)
    cnt = cnt - s.notna().astype(float)
    out = np.array((tot / cnt).to_numpy(), dtype="float64")  # copy: to_numpy may be read-only
    out[cnt.to_numpy() < max(8, w // 2)] = np.nan
    return out


def build(df: pd.DataFrame, px: pd.DataFrame, h: int, w: int):
    """Return (edge array, analyst codes, per-symbol arrays for permutation)."""
    edges, who, packs = [], [], []
    dropped = 0
    for sym, grp in df.groupby("symbol", sort=False):
        if sym not in px.columns:
            dropped += len(grp)
            continue
        s = px[sym].dropna()
        if len(s) < h + 2 * w + 10:
            dropped += len(grp)
            continue
        idx = s.index
        v = s.to_numpy(dtype="float64")
        f = np.full(len(v), np.nan)
        ok = v[:-h] > 0
        f[:-h] = np.where(ok, v[h:] / np.where(ok, v[:-h], 1.0) - 1.0, np.nan)
        c = band_ctrl(f, w)
        e = f - c
        pos = idx.searchsorted(grp.edate.to_numpy())
        inside = (grp.edate.to_numpy() >= idx[0].to_numpy()) & \
                 (grp.edate.to_numpy() <= idx[-1].to_numpy())
        for p, a, ins in zip(pos, grp.analyst.to_numpy(), inside):
            if not ins or p >= len(e) or not np.isfinite(e[p]):
                dropped += 1
                continue
            edges.append(e[p])
            who.append(a)
            packs.append((len(packs), e, int(p)))
    return np.array(edges), np.array(who), packs, dropped


def perm_p(edges: np.ndarray, who: np.ndarray, packs, rng, obs: float) -> float:
    """Block shift: all events of one analyst move by one shared offset."""
    if len(edges) < MIN_N:
        return float("nan")
    order = {}
    for a in np.unique(who):
        order[a] = np.where(who == a)[0]
    arrs = [p[1] for p in packs]
    poss = np.array([p[2] for p in packs])
    hits = 0
    for _ in range(N_PERM):
        tot, n = 0.0, 0
        for a, ix in order.items():
            off = int(rng.integers(-126, 127))
            for j in ix:
                e, p = arrs[j], poss[j] + off
                if 0 <= p < len(e) and np.isfinite(e[p]):
                    tot += e[p]
                    n += 1
        if n and abs(tot / n) >= abs(obs):
            hits += 1
    return (hits + 1) / (N_PERM + 1)


def main() -> None:
    df = load()
    say(f"{len(df)} dated events | {df.symbol.nunique()} symbols | "
        f"{df.analyst.nunique()} analysts | {df.firm.nunique()} firms")
    say(f"{df.edate.min():%Y-%m-%d} .. {df.edate.max():%Y-%m-%d}")
    say(f"actions: {df.action.value_counts().to_dict()}\n")

    syms = sorted(df.symbol.unique())
    start = (df.edate.min() - pd.Timedelta(days=260)).strftime("%Y-%m-%d")
    say(f"downloading {len(syms)} symbols from {start} ...")
    import time as _t

    def pull(batch):
        d = yf.download(batch, start=start, auto_adjust=True,
                        progress=False, threads=True)["Close"]
        if isinstance(d, pd.Series):
            d = d.to_frame(batch[0])
        return d

    px = pd.DataFrame()
    CH = 200
    for i in range(0, len(syms), CH):
        try:
            d = pull(syms[i:i + CH])
        except Exception:
            d = pd.DataFrame()
        px = d if px.empty else px.join(d, how="outer")
        say(f"  {min(i + CH, len(syms))}/{len(syms)}")
    # A whole chunk failing is a rate limit, not 200 simultaneous delistings.
    # Retry the misses in small batches before believing the data is gone.
    for attempt in range(3):
        miss = [s for s in syms if s not in px.columns or not px[s].notna().any()]
        if not miss:
            break
        say(f"  retry {attempt + 1}: {len(miss)} unresolved")
        _t.sleep(5)
        for i in range(0, len(miss), 40):
            try:
                d = pull(miss[i:i + 40])
                px = px.join(d[[c for c in d.columns if c not in px.columns]],
                             how="outer") if not px.empty else d
                for c in d.columns:
                    if c in px.columns:
                        px[c] = px[c].fillna(d[c])
            except Exception:
                pass
            _t.sleep(1.0)
    px = px.dropna(how="all")
    say(f"prices: {len(px)} days, {px.notna().any().sum()}/{len(syms)} resolved\n")

    groups = [("ALL", df)]
    for lab, m in [("UPGRADE", df.action.isin(UP)),
                   ("DOWNGRADE", df.action.isin(DOWN)),
                   ("Initiates", df.action.eq("Initiates")),
                   ("Maintains", df.action.eq("Maintains")),
                   ("Reiterates", df.action.eq("Reiterates"))]:
        if m.sum() >= MIN_N:
            groups.append((lab, df[m]))

    say(f"{'group':<12}{'h':>4}{'W':>5}{'n':>7}{'edge':>9}{'perm p':>9}")
    say("-" * 46)
    rng = np.random.default_rng(11)
    rows, attempted = [], 0
    for lab, sub in groups:
        for h in HORIZONS:
            for w in BANDS:
                if w < h // 3:
                    continue
                edges, who, packs, drop = build(sub, px, h, w)
                if len(edges) < MIN_N:
                    continue
                attempted += 1
                obs = float(np.mean(edges))
                p = perm_p(edges, who, packs, rng, obs)
                rows.append((lab, h, w, len(edges), obs, p))
                say(f"{lab:<12}{h:>4}{w:>5}{len(edges):>7}"
                    f"{obs*100:>8.2f}%{p:>9.3f}")
    say("-" * 46)
    say("edge   = analyst's own date minus a nearby day in the SAME stock")
    say("perm p = analyst-block-shifted randomization")
    if attempted:
        thr = 0.05 / attempted
        say(f"\n{attempted} tests attempted -> Bonferroni p < {thr:.4f}")
        hits = [r for r in rows if r[5] < thr]
        say(f"clearing it: {len(hits)}")
        for r in hits:
            say(f"   {r[0]} h={r[1]} W={r[2]} n={r[3]} edge={r[4]*100:+.2f}% p={r[5]:.4f}")
    if rows:
        pd.DataFrame(rows, columns=["group", "h", "W", "n", "edge", "p"]).to_csv(
            "research/analysts/revision_study_out.csv", index=False)
        say("\nwrote research/analysts/revision_study_out.csv")
    say("\nIf edge changes sign across W, there is no stable effect and the")
    say("estimate at any single W is a choice, not a measurement.")


if __name__ == "__main__":
    main()
