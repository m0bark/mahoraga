"""Find correlations AND the hidden variable driving them.

    python research/tool/confound.py NVDA AMD AVGO KO PEP XOM CVX

The ice-cream / shark-attack problem: two series move together because a
THIRD thing moves both. Ice cream and shark attacks both track summer.
The test is partial correlation -- correlation between x and y once z is
held constant:

    r(x,y | z) = (rxy - rxz*ryz) / sqrt((1-rxz^2)(1-ryz^2))

If r(x,y) is high and r(x,y | z) collapses toward zero, z was the cause and
the pair relationship was an illusion.

In markets the "summer" is almost always THE MARKET ITSELF. Two stocks
correlate at 0.7 because both are stocks. Controlling for SPY tells you
whether anything real connects them.

Why not a neural network: a net finds more correlations, not fewer, and it
cannot tell you WHICH variable is doing the work. Confounding is a question
about structure, and the answer has to be readable. This prints its
arithmetic.

Two rules baked in, both of which people get wrong:
  1. Uses RETURNS, never price levels. Any two series that trend upward
     correlate near 1.0 -- that is spurious regression, not a relationship.
  2. Reports the confounded pairs as loudly as the real ones, because the
     confounded ones are what get traded by mistake.
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


def partial_corr(x, y, z) -> float:
    """corr(x, y) with z held constant."""
    rxy, rxz, ryz = np.corrcoef(x, y)[0, 1], np.corrcoef(x, z)[0, 1], np.corrcoef(y, z)[0, 1]
    den = np.sqrt((1 - rxz ** 2) * (1 - ryz ** 2))
    return float("nan") if den == 0 else (rxy - rxz * ryz) / den


def demo() -> None:
    """Validate the method on data where we KNOW the answer."""
    rng = np.random.default_rng(0)
    n = 400
    summer = np.sin(np.arange(n) * 2 * np.pi / 365)          # the hidden cause
    ice_cream = 3 * summer + rng.normal(0, 1, n)             # caused by summer
    sharks = 3 * summer + rng.normal(0, 1, n)                # caused by summer
    r = np.corrcoef(ice_cream, sharks)[0, 1]
    pr = partial_corr(ice_cream, sharks, summer)
    print("METHOD CHECK -- synthetic data, cause known by construction")
    print(f"  corr(ice cream, sharks)          = {r:+.3f}   <- looks causal")
    print(f"  corr(ice cream, sharks | summer) = {pr:+.3f}   <- collapses\n")


def main() -> None:
    tickers = [a.upper() for a in sys.argv[1:]] or \
        "NVDA AMD AVGO MU KO PEP XOM CVX JPM BAC GLD TLT".split()
    demo()

    px = yf.download(tickers + ["SPY"], period="3y", auto_adjust=True,
                     progress=False, threads=True)["Close"].dropna(how="all")
    # RETURNS, not levels -- levels of any two rising series correlate ~1.0
    rets = px.pct_change().dropna()
    if "SPY" not in rets:
        print("need SPY as the market control")
        return
    mkt = rets["SPY"].values
    names = [t for t in tickers if t in rets]

    rows = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            x, y = rets[a].values, rets[b].values
            raw = np.corrcoef(x, y)[0, 1]
            pc = partial_corr(x, y, mkt)
            rows.append({"a": a, "b": b, "raw": raw, "partial": pc,
                         "explained": raw - pc})
    d = pd.DataFrame(rows)

    print(f"{len(names)} series, {len(rets)} daily observations, "
          f"control = SPY (the market)\n")

    print("=== CONFOUNDED: strong raw link that the market fully explains ===")
    conf = d[(d.raw.abs() > 0.35) & (d.partial.abs() < 0.15)] \
        .sort_values("explained", ascending=False)
    if len(conf):
        for _, r in conf.head(12).iterrows():
            print(f"  {r.a:<6}~{r.b:<6} raw {r.raw:+.2f} -> "
                  f"partial {r.partial:+.2f}   the market was the 'summer'")
    else:
        print("  none")

    print("\n=== REAL: link survives controlling for the market ===")
    real = d[d.partial.abs() > 0.35].sort_values("partial", ascending=False)
    if len(real):
        for _, r in real.head(12).iterrows():
            print(f"  {r.a:<6}~{r.b:<6} raw {r.raw:+.2f} -> "
                  f"partial {r.partial:+.2f}   something genuinely shared")
    else:
        print("  none")

    print("\n=== how much of each pair is just 'being a stock' ===")
    print(f"  median raw correlation:     {d.raw.median():+.3f}")
    print(f"  median partial correlation: {d.partial.median():+.3f}")
    print(f"  median explained by market: {d.explained.median():+.3f}")

    d.sort_values("partial", ascending=False).to_csv(
        "research/tool/confound_out.csv", index=False)
    print("\nwrote research/tool/confound_out.csv")
    print("\nCAUTION: a surviving partial correlation is still not causation.")
    print("It only means SPY was not the explanation. There can be another")
    print("confounder you did not control for -- sector, rates, oil, the")
    print("dollar. Add it as a control and re-run. This narrows the field of")
    print("candidates; it never proves a cause.")


if __name__ == "__main__":
    main()
