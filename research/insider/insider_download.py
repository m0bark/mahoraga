# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "requests>=2.31",
#     "pandas>=2.2",
# ]
# ///
"""SEC DERA Insider Transactions data sets: download + compact extraction.

Source: https://www.sec.gov/dera/data/form-345  (Forms 3/4/5, quarterly,
2006q1..present). Two URL generations exist; both are tried.

Usage:
  uv run --python 3.12 insider_download.py sample   # 3 quarters, schema check
  uv run --python 3.12 insider_download.py all      # full 2006q1..2026q2

For each quarter this stores the raw zip in raw/ and extracts a compact
purchases/sales table to compact/{quarter}.csv.gz with columns:
  accession, filing_date, trans_date, symbol, issuer_cik, owner_cik,
  is_officer, is_director, code (P/S), shares, price, value
"""

from __future__ import annotations

import io
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).parent
RAW = HERE / "raw"
COMPACT = HERE / "compact"
UA = {"User-Agent": "mahoraga-research/0.1 (personal quant research)"}
BASES = [
    "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets",
    "https://www.sec.gov/files/datastandardsinnovation/data/insider-transactions-data-sets",
]


def quarters(start=(2006, 1), end=(2026, 2)):
    y, q = start
    while (y, q) <= end:
        yield f"{y}q{q}"
        q += 1
        if q == 5:
            y, q = y + 1, 1


def download(qtr: str) -> Path | None:
    dest = RAW / f"{qtr}_form345.zip"
    if dest.exists() and dest.stat().st_size > 10_000:
        return dest
    for base in BASES:
        try:
            r = requests.get(f"{base}/{qtr}_form345.zip", headers=UA, timeout=120)
            if r.status_code == 200 and len(r.content) > 10_000:
                dest.write_bytes(r.content)
                time.sleep(0.6)  # SEC fair-access pacing
                return dest
        except Exception:
            pass
        time.sleep(0.6)
    print(f"  {qtr}: DOWNLOAD FAILED")
    return None


def read_tsv(z: zipfile.ZipFile, name: str) -> pd.DataFrame:
    # table names are stable but casing/extension varies slightly across years
    for candidate in z.namelist():
        if candidate.lower().startswith(name.lower()):
            with z.open(candidate) as f:
                return pd.read_csv(io.BytesIO(f.read()), sep="\t",
                                   dtype=str, low_memory=False)
    raise KeyError(f"{name} not found in zip: {z.namelist()}")


def extract(qtr: str, zpath: Path) -> None:
    out = COMPACT / f"{qtr}.csv.gz"
    if out.exists():
        return
    with zipfile.ZipFile(zpath) as z:
        sub = read_tsv(z, "SUBMISSION")
        owner = read_tsv(z, "REPORTINGOWNER")
        trans = read_tsv(z, "NONDERIV_TRANS")

    sub.columns = [c.upper() for c in sub.columns]
    owner.columns = [c.upper() for c in owner.columns]
    trans.columns = [c.upper() for c in trans.columns]

    t = trans[trans["TRANS_CODE"].isin(["P", "S"])].copy()
    t["shares"] = pd.to_numeric(t.get("TRANS_SHARES"), errors="coerce")
    t["price"] = pd.to_numeric(t.get("TRANS_PRICEPERSHARE"), errors="coerce")
    t["value"] = t["shares"] * t["price"]

    sub_cols = {
        "ACCESSION_NUMBER": "accession", "FILING_DATE": "filing_date",
        "ISSUERCIK": "issuer_cik", "ISSUERTRADINGSYMBOL": "symbol",
    }
    s = sub[[c for c in sub_cols if c in sub.columns]].rename(columns=sub_cols)
    own_cols = {
        "ACCESSION_NUMBER": "accession", "RPTOWNERCIK": "owner_cik",
        "RPTOWNER_RELATIONSHIP": "relationship",
    }
    o = owner[[c for c in own_cols if c in owner.columns]].rename(columns=own_cols)
    o = o.groupby("accession").agg(
        owner_cik=("owner_cik", "first"),
        relationship=("relationship", lambda x: ";".join(sorted(set(x.dropna())))),
    ).reset_index()

    m = (t.rename(columns={"ACCESSION_NUMBER": "accession",
                           "TRANS_DATE": "trans_date",
                           "TRANS_CODE": "code"})
         [["accession", "trans_date", "code", "shares", "price", "value"]]
         .merge(s, on="accession", how="left")
         .merge(o, on="accession", how="left"))
    m["is_officer"] = m["relationship"].str.contains("Officer", case=False, na=False)
    m["is_director"] = m["relationship"].str.contains("Director", case=False, na=False)
    m.drop(columns=["relationship"]).to_csv(out, index=False, compression="gzip")
    n_p = (m.code == "P").sum()
    print(f"  {qtr}: {len(m):6d} P/S transactions ({n_p} purchases) -> {out.name}")


def main() -> None:
    RAW.mkdir(exist_ok=True)
    COMPACT.mkdir(exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else "sample"
    qs = ["2015q1", "2024q4", "2026q2"] if mode == "sample" else list(quarters())
    print(f"mode={mode}: {len(qs)} quarters")
    for qtr in qs:
        zpath = download(qtr)
        if zpath:
            try:
                extract(qtr, zpath)
            except Exception as exc:
                print(f"  {qtr}: EXTRACT FAILED — {exc}")
    done = sorted(p.stem.replace(".csv", "") for p in COMPACT.glob("*.csv.gz"))
    print(f"\ncompact quarters ready: {len(done)}"
          + (f" ({done[0]} .. {done[-1]})" if done else ""))


if __name__ == "__main__":
    main()
