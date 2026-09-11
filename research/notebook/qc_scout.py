# QC RESEARCH NOTEBOOK — free scouting on point-in-time data.
# Paste into a QuantBook notebook on quantconnect.com (Research, not Backtest).
# Runs on the FREE research node and consumes NO backtest token.
#
# WHY THIS EXISTS
# Local yfinance scouting is structurally broken for every question this
# project cares about. Measured, repeatedly:
#   * drawdown-vs-near-high: local distorted the answer by ~26 points
#     (research/screen/RESULTS-nearhigh.md)
#   * a confirmation rule scored t=+3.45 locally and was pure survivorship
#     (research/screen/RESULTS-confirmation.md)
# QC research gives the same PIT universes the Sentinel backtests use, for
# free. This replaces the broken scouting loop with an honest one.
#
# WHAT THIS IS NOT
# NOT a verdict. PLAN.md principle 1 stands: QuantConnect backtests are the
# sole verdict engine, local P&L is banned from the ledger, and no local
# backtester will ever exist. Notebook output is SCOUTING -- it decides what
# is worth a pre-registration, never whether something works.
# Anything found here still needs a sealed one-shot backtest.
#
# Also note: notebook results are read over the FULL period. Do not run a
# scout over 2023+ or you burn a family's holdout without a card.

# ============================================================ CELL 1: setup
qb = QuantBook()

START = datetime(2007, 1, 1)
END = datetime(2022, 12, 31)      # holdout 2023+ deliberately excluded
UNIVERSE_SIZE = 500
FWD = 63                          # forward window in trading days (~1 quarter)


def liquid_large_caps(fundamental):
    liquid = [f for f in fundamental
              if f.has_fundamental_data and f.price > 5
              and f.dollar_volume > 20_000_000]
    liquid = sorted(liquid, key=lambda f: f.market_cap, reverse=True)
    return [f.symbol for f in liquid[:UNIVERSE_SIZE]]


universe = qb.add_universe(liquid_large_caps)

# ================================================ CELL 2: PIT universe pull
# universe_history returns the ACTUAL members on each historical date, with
# their as-reported fundamentals. This is the survivorship-free part -- names
# that later delisted are present on the dates they existed.
uh = qb.universe_history(universe, START, END)
print(f"universe snapshots: {len(uh)}")

records = []
for dt, constituents in uh.items():
    for c in constituents:
        try:
            records.append({
                "date": dt,
                "symbol": str(c.symbol),
                "price": float(c.price),
                "mcap": float(c.market_cap),
                "pe": float(c.valuation_ratios.pe_ratio),
                "fcf_yield": float(c.valuation_ratios.fcf_yield),
                "roa": float(c.operation_ratios.roa.one_year),
                "roic": float(c.operation_ratios.roic.one_year),
                "net_margin": float(c.operation_ratios.net_margin.one_year),
                "d_e": float(c.operation_ratios.total_debt_equity_ratio.one_year),
            })
        except Exception:
            continue

pit = pd.DataFrame(records)
print(f"{len(pit):,} name-dates | {pit.symbol.nunique():,} distinct symbols")
print("distinct symbols is the number that matters -- if it is close to 500,")
print("the pull is NOT point-in-time and something is wrong.")

# ============================================ CELL 3: price panel + features
syms = sorted(pit.symbol.unique())
print(f"pulling daily history for {len(syms)} symbols "
      f"(this is the slow cell; free node, be patient)")

hist = qb.history(
    [qb.symbol(s) for s in syms], START - timedelta(days=400), END,
    Resolution.DAILY)
px = hist["close"].unstack(level=0)
px.columns = [str(c) for c in px.columns]
print(f"price panel: {px.shape[0]} days x {px.shape[1]} names")

hi252 = px.rolling(252).max()
nearness = px / hi252                      # 1.00 = at the 52-week high
drawdown = nearness - 1.0
sma200 = px.rolling(200).mean()
d200 = px / sma200 - 1.0
fwd_ret = px.shift(-FWD) / px - 1.0

# ============================================= CELL 4: bucket + measure
# Edit THIS cell to scout a new idea. Everything above is fixed plumbing.

def bucket_study(feature: pd.DataFrame, label: str, n_buckets: int = 5,
                 quality_mask: pd.DataFrame | None = None) -> pd.DataFrame:
    """Sort the PIT universe by `feature` each month, report forward returns
    per bucket, and include a same-universe RANDOM control.

    The random control is not optional. It is the only thing separating a
    real gradient from the universe's own drift."""
    month_ends = px.resample("ME").last().index
    rows = []
    rng = np.random.default_rng(7)
    for dt in month_ends:
        if dt not in feature.index:
            continue
        f = feature.loc[dt].dropna()
        r = fwd_ret.loc[dt].dropna() if dt in fwd_ret.index else None
        if r is None or len(f) < 50:
            continue
        common = f.index.intersection(r.index)
        if quality_mask is not None and dt in quality_mask.index:
            q = quality_mask.loc[dt]
            common = common.intersection(q[q].index)
        if len(common) < 50:
            continue
        f2, r2 = f[common], r[common]
        try:
            qs = pd.qcut(f2.rank(method="first"), n_buckets,
                         labels=[f"B{i+1}" for i in range(n_buckets)])
        except ValueError:
            continue
        for b in qs.unique():
            rows.append({"date": dt, "bucket": str(b),
                         "ret": r2[qs == b].mean()})
        pick = rng.choice(len(common), size=max(len(common)//n_buckets, 10),
                          replace=False)
        rows.append({"date": dt, "bucket": "RANDOM",
                     "ret": r2.iloc[pick].mean()})

    d = pd.DataFrame(rows)
    out = d.groupby("bucket").ret.agg(["mean", "std", "count"])
    out["ann"] = (1 + out["mean"]) ** (252 / FWD) - 1
    rnd = out.loc["RANDOM", "mean"] if "RANDOM" in out.index else np.nan
    out["vs_random"] = out["mean"] - rnd
    print(f"\n=== {label} (B1 = lowest {label}, B{n_buckets} = highest) ===")
    print(out.round(4))
    print("\nRead vs_random, never the raw column. If no bucket separates")
    print("from RANDOM, the feature carries nothing regardless of the spread.")
    return out


# --- scout 1: does drawdown depth predict, PIT? -------------------------
bucket_study(drawdown, "drawdown depth")

# --- scout 2: nearness to the 52-week high ------------------------------
bucket_study(nearness, "nearness to 52w high")

# --- scout 3: quality-conditioned -- edit freely -------------------------
# qual = build a boolean DataFrame from `pit` reindexed to px's grid, then:
# bucket_study(drawdown, "drawdown | quality", quality_mask=qual)

# ================================================ CELL 5: the sanity check
# ALWAYS run this before believing any result above. It asks whether this
# dataset reproduces something whose survivorship-free answer is already
# sealed. If it cannot, nothing computed in it counts.
#
#   known: card 2026-08-31 measured, PIT, deepest-drawdown quintile
#          +12.02%/yr vs nearest-high quintile +8.17%/yr.
#
# If the drawdown study above disagrees with that sign, the pull is not
# actually point-in-time -- check the distinct-symbol count in CELL 2.
print("SANITY: compare scout 1's B1-vs-B5 sign against card "
      "2026-08-31-nearhigh-fscore.md (dips ahead by +3.85%/yr).")
print("Agreement means the pull is PIT. Disagreement means it is not.")
