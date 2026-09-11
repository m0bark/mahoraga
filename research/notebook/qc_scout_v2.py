# QC RESEARCH SCOUT v2 — PIT membership ENFORCED.
# Paste into research.ipynb AFTER the cell that built `px`, `pit`, `month_ends`.
# Free research node, no backtest token. SCOUTING ONLY — never a verdict.
#
# v1 bug this fixes: the PIT pull built the SYMBOL LIST but nothing constrained
# membership per date, so every name was scored on every date -- including
# names that only joined the top-500 in 2015, scored back in 2007. That is the
# same survivorship bias as yfinance with a better-sourced ticker list. It
# inflated every bucket (RANDOM compounded to 14.7% vs the backtest's 11.14%).
import gc

# ---- PIT membership mask -------------------------------------------------
pit["date"] = pd.to_datetime(pit["date"])
memb = (pit.assign(v=True)
          .pivot_table(index="date", columns="symbol", values="v",
                       aggfunc="first")
          .reindex(index=px.index, columns=px.columns)
          .ffill(limit=90)                 # carry membership between snapshots
          .fillna(False).astype(bool))
med = memb.sum(axis=1).median()
print(f"members per date: median {med:.0f}")
print("MUST be ~500. If it reads ~1625 the mask is not binding and nothing "
      "below counts.\n")

# ---- forward returns: a delisted name books its last print, not a NaN ----
px_ff = px.ffill(limit=FWD)
fwd_ret = (px_ff.shift(-FWD) / px - 1.0).astype("float32")
fwd_ret = fwd_ret.where(px.notna())        # only score names alive at t
del px_ff
gc.collect()


def bucket_study(feature, label, n_buckets=5, quality_mask=None, step=3):
    """Monthly sort inside the PIT-membership cross-section, non-overlapping
    windows (step=3), with a mandatory same-universe RANDOM arm.

    Read vs_rnd_cagr. A bucket that does not separate from RANDOM carries
    nothing, however large its raw return looks."""
    rows, rng, used = [], np.random.default_rng(7), 0
    for k, dt in enumerate(month_ends):
        if k % step or dt not in feature.index or dt not in fwd_ret.index:
            continue
        f, r = feature.loc[dt].dropna(), fwd_ret.loc[dt].dropna()
        common = f.index.intersection(r.index)
        common = common.intersection(memb.columns[memb.loc[dt]])   # <-- PIT
        if quality_mask is not None and dt in quality_mask.index:
            q = quality_mask.loc[dt]
            common = common.intersection(q[q].index)
        if len(common) < 50:
            continue
        used += 1
        f2, r2 = f[common], r[common]
        try:
            qs = pd.qcut(f2.rank(method="first"), n_buckets,
                         labels=[f"B{i+1}" for i in range(n_buckets)])
        except ValueError:
            continue
        for b in qs.unique():
            rows.append({"bucket": str(b), "ret": r2[qs == b].mean()})
        pick = rng.choice(len(common), size=max(len(common) // n_buckets, 10),
                          replace=False)
        rows.append({"bucket": "RANDOM", "ret": r2.iloc[pick].mean()})

    if not rows:
        print(f"=== {label}: NO USABLE DATES ===")
        return None
    d = pd.DataFrame(rows)
    out = d.groupby("bucket").ret.agg(["mean", "median", "std", "count"])
    comp = d.groupby("bucket").ret.apply(lambda s: (1 + s).prod())
    out["cagr"] = comp ** (12 / (used * step)) - 1
    out["vs_rnd_cagr"] = out["cagr"] - out.loc["RANDOM", "cagr"]
    print(f"=== {label} (B1 lowest -> B{n_buckets} highest), "
          f"{used} non-overlapping windows ===")
    print(out.round(4), "\n")
    return out


bucket_study(drawdown, "drawdown depth")              # B1 = deepest dip
bucket_study(px / px.shift(126) - 1, "6m momentum")   # B5 = strongest

print("CALIBRATION CHECK against sealed card 2026-08-31 (PIT, real portfolio "
      "accounting):")
print("  it measured deepest-dip quintile 12.02%/yr vs equal-weight 11.14% "
      "-> a gap of +0.88pp.")
print("  RANDOM here should now land near 11%, and the deep-dip gap near")
print("  +1pp. v1 said +15pp, which was the membership leak.")
print("  If those two now agree, the notebook is calibrated and can be")
print("  trusted on questions the backtests have NOT answered.")
