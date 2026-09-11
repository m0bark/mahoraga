# QC RESEARCH NOTEBOOK — one-block scout. Paste into research.ipynb, run once.
# Free research node. No backtest token. PIT, survivorship-free.
# NOT a verdict — scouting only. Anything found here still needs a sealed run.
import gc

qb = QuantBook()
START, END = datetime(2007, 1, 1), datetime(2022, 12, 31)   # 2023+ = holdout
UNIVERSE_SIZE, FWD, CHUNK = 500, 63, 120


def liquid_large_caps(fundamental):
    liquid = [f for f in fundamental
              if f.has_fundamental_data and f.price > 5
              and f.dollar_volume > 20_000_000]
    return [f.symbol for f in
            sorted(liquid, key=lambda f: f.market_cap, reverse=True)[:UNIVERSE_SIZE]]


universe = qb.add_universe(liquid_large_caps)

# ---- PIT universe: real members on each date, delisted names included ----
uh = qb.universe_history(universe, START, END)
records, sym_objs = [], {}
for dt, constituents in uh.items():
    for c in constituents:
        try:
            key = str(c.symbol)
            sym_objs[key] = c.symbol
            records.append({
                "date": dt, "symbol": key,
                "roa": float(c.operation_ratios.roa.one_year),
                "roic": float(c.operation_ratios.roic.one_year),
                "net_margin": float(c.operation_ratios.net_margin.one_year),
                "d_e": float(c.operation_ratios.total_debt_equity_ratio.one_year),
                "pe": float(c.valuation_ratios.pe_ratio),
                "fcf_yield": float(c.valuation_ratios.fcf_yield),
            })
        except Exception:
            continue
pit = pd.DataFrame(records)
print(f"{len(pit):,} name-dates | {pit.symbol.nunique():,} distinct symbols")
print("INTEGRITY: distinct symbols must be WELL ABOVE 500. If it is ~500 the")
print("pull is not point-in-time and nothing below counts.\n")

# ---- price panel, chunked + float32 so the kernel survives ----
syms = sorted(pit.symbol.unique())
frames = []
for i in range(0, len(syms), CHUNK):
    batch = syms[i:i + CHUNK]
    try:
        h = qb.history([sym_objs[s] for s in batch],
                       START - timedelta(days=400), END, Resolution.DAILY)
        if h is not None and len(h):
            c = h["close"].unstack(level=0).astype("float32")
            c.columns = [str(x) for x in c.columns]
            frames.append(c)
    except Exception as e:
        print(f"  chunk {i//CHUNK} failed: {str(e)[:70]}")
    finally:
        h = None
        gc.collect()
    print(f"  {min(i+CHUNK, len(syms))}/{len(syms)}", end="\r")

px = pd.concat(frames, axis=1).sort_index()
px = px.loc[:, ~px.columns.duplicated()]
frames = None
gc.collect()
print(f"\npanel: {px.shape[0]} days x {px.shape[1]} names "
      f"({px.memory_usage().sum()/1e6:.0f} MB)\n")

hi252 = px.rolling(252).max()
nearness = (px / hi252).astype("float32")     # 1.00 = at the 52-week high
drawdown = nearness - 1.0
fwd_ret = (px.shift(-FWD) / px - 1.0).astype("float32")
del hi252
gc.collect()


# ---- bucket study with the mandatory random control ----
def bucket_study(feature, label, n_buckets=5, quality_mask=None):
    """Monthly sort into buckets + a same-universe RANDOM arm.
    Read vs_random. A spread that does not separate from RANDOM is nothing."""
    rows, rng = [], np.random.default_rng(7)
    for dt in px.resample("ME").last().index:
        if dt not in feature.index or dt not in fwd_ret.index:
            continue
        f, r = feature.loc[dt].dropna(), fwd_ret.loc[dt].dropna()
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
            rows.append({"bucket": str(b), "ret": r2[qs == b].mean()})
        pick = rng.choice(len(common), size=max(len(common)//n_buckets, 10),
                          replace=False)
        rows.append({"bucket": "RANDOM", "ret": r2.iloc[pick].mean()})
    out = pd.DataFrame(rows).groupby("bucket").ret.agg(["mean", "std", "count"])
    out["ann"] = (1 + out["mean"]) ** (252 / FWD) - 1
    out["vs_random"] = out["mean"] - out.loc["RANDOM", "mean"]
    print(f"=== {label} (B1 lowest -> B{n_buckets} highest) ===")
    print(out.round(4), "\n")
    return out


bucket_study(drawdown, "drawdown depth")
bucket_study(nearness, "nearness to 52w high")

print("SANITY: card 2026-08-31 measured, PIT, deepest-dip quintile +12.02%/yr")
print("vs nearest-high +8.17%. If drawdown depth disagrees in SIGN here, the")
print("pull is not PIT — recheck the distinct-symbol count above.")
