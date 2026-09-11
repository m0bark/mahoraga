"""Calibrate the fear meter's flags. NOT a return backtest.

The meter classifies BUSINESS STATE, so tuning it on returns would be
overfitting a classifier to the wrong target. The right question is:

    does each flag actually discriminate a deteriorating business
    from a healthy one, and does it fire rarely enough to mean anything?

A flag is only worth keeping if BOTH hold:
  * it is SELECTIVE -- fires on a minority of names, not everything
  * it has LIFT     -- fires much more often on deteriorating names

Ground truth (observable, not a forecast): a name is DETERIORATING if its
latest full-year revenue fell, or net income went negative. Flags that are
definitionally part of that truth (the revenue flags) are excluded from the
lift table -- scoring them against it would be circular.

Known limits, stated not hidden:
  * survivorship -- names that fully broke have delisted and are absent, so
    the deteriorating group here is the mildly-sick, not the dead. Lift
    measured this way is a LOWER bound.
  * ~120 names, one snapshot in time. This calibrates thresholds; it does
    not validate that the meter predicts anything.
"""
from __future__ import annotations

import io
import sys
import warnings

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

import numpy as np
import yfinance as yf

U = ("AAPL MSFT GOOGL AMZN META NVDA AMD AVGO TSM MU INTC QCOM TXN ADI MRVL LRCX AMAT "
     "KLAC NXPI ON MCHP SWKS QRVO TER ENTG MPWR ANET COHR LITE ONTO ACLS AMKR AEIS ADBE "
     "CRM NOW ORCL PANW ZS NET DDOG TEAM WDAY HUBS INTU ADSK SNPS CDNS FTNT OKTA TWLO "
     "TTD SHOP FSLR ENPH SEDG RUN CSIQ JKS PLUG NEE BE TSLA GM F LI XPEV APTV ALB MP VRT "
     "ETN PWR NVT MOD CEG VST ISRG DXCM JNJ XOM JPM PG KO PEP WMT CVX MRK PFE T VZ CSCO "
     "IBM MCD NKE HD LOW CAT DE MMM GE BA HON UPS UNH ABT LLY BMY AMGN GILD COST TGT "
     "SBUX DIS CMCSA DAL LUV GS MS BAC C WFC AXP USB PNC SCHW").split()

# thresholds currently hard-coded in fear_meter.py, plus tighter/looser
# variants so we can see how selectivity moves with the knob
VARIANTS = {
    "gross margin compressing": [0.01, 0.02, 0.03],
    "capex step-up":            [1.3, 1.4, 1.6, 2.0],
    "OCF/NI conversion below":  [0.5, 0.6, 0.8],
    "dilution QoQ above":       [0.01, 0.03, 0.05],
}


def grab(tk, stmt, row):
    try:
        s = getattr(tk, stmt).loc[row].dropna().sort_index()
        return [float(x) for x in s.values] if len(s) >= 2 else None
    except Exception:
        return None


def main() -> None:
    recs = []
    for t in U:
        try:
            tk = yf.Ticker(t)
            arev = grab(tk, "income_stmt", "Total Revenue")
            ani = grab(tk, "income_stmt", "Net Income")
            if not arev or len(arev) < 2:
                continue
            deteriorating = (arev[-1] < arev[-2]) or (ani and ani[-1] < 0)

            qrev = grab(tk, "quarterly_income_stmt", "Total Revenue")
            qgp = grab(tk, "quarterly_income_stmt", "Gross Profit")
            qni = grab(tk, "quarterly_income_stmt", "Net Income")
            qocf = grab(tk, "quarterly_cashflow", "Operating Cash Flow")
            qcapex = grab(tk, "quarterly_cashflow", "Capital Expenditure")
            qsh = grab(tk, "quarterly_balance_sheet", "Ordinary Shares Number")
            info = {}
            try:
                info = tk.info
            except Exception:
                pass

            r = {"t": t, "bad": bool(deteriorating)}

            if qgp and qrev and len(qgp) >= 2 and len(qrev) >= 2 and qrev[-1] and qrev[-2]:
                r["gm_drop"] = (qgp[-2] / qrev[-2]) - (qgp[-1] / qrev[-1])
            if qocf:
                r["ocf_neg"] = qocf[-1] < 0
            if qocf and qni and qni[-1] and qni[-1] > 0:
                r["ocf_ni"] = qocf[-1] / qni[-1]
            if qcapex and len(qcapex) >= 4:
                base = np.mean([abs(x) for x in qcapex[-4:-1]])
                if base:
                    r["capex_x"] = float(abs(qcapex[-1]) / base)
            if qsh and len(qsh) >= 2 and qsh[-2]:
                r["dilution"] = qsh[-1] / qsh[-2] - 1
            de = info.get("debtToEquity")
            if de is not None:
                r["de"] = de / 100
            cr = info.get("currentRatio")
            if cr is not None:
                r["cr"] = cr
            recs.append(r)
        except Exception:
            continue

    n = len(recs)
    bad = [r for r in recs if r["bad"]]
    good = [r for r in recs if not r["bad"]]
    print(f"{n} names | deteriorating {len(bad)} ({len(bad)/n:.0%}) | "
          f"healthy {len(good)}\n")

    def report(label, fn):
        # NOTE: never use `is True` here -- numpy comparisons return
        # np.bool_, and np.True_ is not True. That bug silently reported
        # the capex flag as firing 0% of the time.
        hit = lambda r: fn(r) is not None and bool(fn(r))
        f_all = [r for r in recs if hit(r)]
        f_bad = [r for r in bad if hit(r)]
        f_good = [r for r in good if hit(r)]
        if not recs:
            return
        rate = len(f_all) / n
        pb = len(f_bad) / len(bad) if bad else 0
        pg = len(f_good) / len(good) if good else 0
        lift = (pb / pg) if pg > 0 else (float("inf") if pb > 0 else 0)
        verdict = ("KEEP" if (0.02 <= rate <= 0.40 and lift >= 1.5) else
                   "TOO LOOSE" if rate > 0.40 else
                   "TOO RARE" if rate < 0.02 else "NO LIFT")
        li = "inf" if lift == float("inf") else f"{lift:.2f}x"
        print(f"  {label:<38}fires {rate:5.0%}  bad {pb:5.0%}  good {pg:5.0%}  "
              f"lift {li:>6}  {verdict}")

    print("FLAG CALIBRATION  (fires = share of all names; lift = P(fire|bad)/P(fire|good))")
    print("-" * 96)
    for thr in VARIANTS["gross margin compressing"]:
        report(f"gross margin down > {thr:.0%}",
               lambda r, k=thr: (r["gm_drop"] > k) if "gm_drop" in r else None)
    print()
    for thr in VARIANTS["capex step-up"]:
        report(f"capex > {thr}x its 3q base",
               lambda r, k=thr: (r["capex_x"] > k) if "capex_x" in r else None)
    print()
    for thr in VARIANTS["OCF/NI conversion below"]:
        report(f"OCF < {thr:.0%} of net income",
               lambda r, k=thr: (r["ocf_ni"] < k) if "ocf_ni" in r else None)
    print()
    for thr in VARIANTS["dilution QoQ above"]:
        report(f"share count +{thr:.0%} QoQ",
               lambda r, k=thr: (r["dilution"] > k) if "dilution" in r else None)
    print()
    report("operating cash flow negative",
           lambda r: r.get("ocf_neg") if "ocf_neg" in r else None)
    report("debt/equity > 2.0",
           lambda r: (r["de"] > 2.0) if "de" in r else None)
    report("debt/equity > 1.0",
           lambda r: (r["de"] > 1.0) if "de" in r else None)
    report("current ratio < 1",
           lambda r: (r["cr"] < 1) if "cr" in r else None)
    print("-" * 96)
    print("KEEP      = selective (2-40% fire rate) AND lift >= 1.5x")
    print("TOO LOOSE = fires on >40% of names; it is describing the market,")
    print("            not the company")
    print("NO LIFT   = fires as often on healthy names as on sick ones")
    print("\nSurvivorship: fully-broken companies have delisted and are absent,")
    print("so 'deteriorating' here means mildly sick. Lift is a LOWER bound.")


if __name__ == "__main__":
    main()
