import sys,io,warnings; warnings.filterwarnings("ignore")
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
import yfinance as yf,pandas as pd,numpy as np
# ticker, start, expiry, clearing, split_adj_divisor_applied_to_yahoo_price, note
D=[("SCHL","2026-03-23","2026-04-21",40.00,1,"Dutch 36-40; cleared MAX; all accepted"),
("WIX","2026-03-05","2026-04-01",92.00,1,"Dutch 80-92; cleared MAX; all accepted"),
("YEXT","2026-02-10","2026-03-18",5.75,1,"Dutch 5.75-6.50; cleared MIN; ~39% prorate"),
("WEX","2025-02-26","2025-03-25",154.00,1,"Dutch 148-170; cleared 154; prorated"),
("INCY","2024-05-13","2024-06-10",60.00,1,"Dutch; cleared 60; 93% accepted"),
("MNST","2024-05-08","2024-06-05",53.00,0.5,"Dutch 53-60; cleared MIN; 48% prorate; 2:1 split Aug-2026"),
("CNNE","2024-03-01","2024-04-01",22.95,1,"Dutch 20.75-23.75; cleared 22.95; no prorate"),
("OSPN","2023-11-13","2023-12-11",10.50,1,"Dutch 9.50-11.00; cleared 10.50"),
("GPRK","2024-03-20","2024-04-17",10.00,1,"Dutch; cleared 10.00; all accepted"),
("RUM","2025-01-03","2025-02-05",7.50,1,"fixed 7.50; stock traded 10-13; NO arb"),
("EXFY","2026-05-13","2026-06-10",1.20,1,"Dutch; cleared 1.20; 100% accepted"),
("HTT","2026-05-26","2026-06-24",3.20,1,"Dutch 2.80-3.20; cleared MAX; 87% accepted"),
("OPTU","2026-06-01","2026-06-30",2.50,1,"fixed 2.50; 48.6% prorate; deep-discount stub"),
("TORO","2025-07-10","2025-08-08",2.75,1,"fixed 2.75; UNDERsubscribed; stock above offer"),
("RBNE","2026-03-24","2026-04-24",3.00,15,"fixed 3.00; 339,775 of 1.0M accepted were ODD LOTS; 1:15 rsplit Jul-2026"),
("MLCI","2025-12-29","2026-02-04",9.43,1,"fixed 9.43"),
("CFNB","2025-05-20","2025-06-27",18.50,1,"fixed 18.50; oversubscribed; stock at/above offer"),
("MTBLY","2025-09-03","2025-09-30",3.00,1,"fixed 3.00/ADS"),
("ANEB","2025-12-22","2026-01-26",3.50,1,"fixed 3.50 going-private; stub collapsed to ~1.10"),
]
FEE=38.0
rows=[]
for tic,s,e,clear,div,note in D:
    df=yf.download(tic,start=s,end=(pd.Timestamp(e)+pd.Timedelta(days=1)).strftime("%Y-%m-%d"),progress=False,auto_adjust=False)
    c=(df["Close"].squeeze().dropna())/div
    med=float(c.median())
    rows.append(dict(tic=tic,exp=e,clear=clear,entry_med=round(med,3),
        spread_pct=round(100*(clear-med)/med,2),cost99=round(99*med,2),
        gross99=round(99*(clear-med),2),net99_fee38=round(99*(clear-med)-FEE,2),
        days=(pd.Timestamp(e)-pd.Timestamp(s)).days,note=note))
df=pd.DataFrame(rows).sort_values("gross99",ascending=False)
pd.set_option("display.width",260,"display.max_columns",30,"display.max_colwidth",60)
print(df[["tic","exp","clear","entry_med","spread_pct","cost99","gross99","net99_fee38","days"]].to_string(index=False))
print("\nNOTES:"); [print(f"  {r.tic:6s} {r.note}") for r in df.itertuples()]
g=df["gross99"]; n=df["net99_fee38"]
print(f"\n--- N={len(df)} completed, priceable odd-lot tenders, Sep-2023..Sep-2026 (36 months) ---")
print(f"positive gross spread : {(g>0).sum()}/{len(df)}  ({100*(g>0).mean():.0f}%)")
print(f"gross $/99sh  median {g.median():8.2f}  mean {g.mean():8.2f}  sum {g.sum():9.2f}")
print(f"net(-$38)     median {n.median():8.2f}  mean {n.mean():8.2f}  sum {n.sum():9.2f}")
print(f"net>0 count   {(n>0).sum()}/{len(df)}")
tr=df[df["gross99"]>0]
print(f"\nIf you ONLY trade the ex-ante positive ones (perfect selection, n={len(tr)}):")
print(f"  gross sum ${tr['gross99'].sum():,.2f} over 3yr = ${tr['gross99'].sum()/3:,.2f}/yr")
print(f"  net(-$38) sum ${tr['net99_fee38'].sum():,.2f} over 3yr = ${tr['net99_fee38'].sum()/3:,.2f}/yr")
print(f"  capital deployed per event median ${tr['cost99'].median():,.2f}")
print(f"  on $25,000 account: {100*tr['net99_fee38'].sum()/3/25000:.2f}%/yr")
big=tr[tr["gross99"]>150]
print(f"\n  concentration: top-3 events = ${tr.nlargest(3,'gross99')['gross99'].sum():,.2f} of ${tr['gross99'].sum():,.2f} gross ({100*tr.nlargest(3,'gross99')['gross99'].sum()/tr['gross99'].sum():.0f}%)")
med_only=tr[tr["gross99"]<=150]
print(f"  excluding the 3 outliers: {len(tr)-3} events, gross sum ${tr['gross99'].sum()-tr.nlargest(3,'gross99')['gross99'].sum():,.2f}, net sum ${tr['net99_fee38'].sum()-tr.nlargest(3,'net99_fee38')['net99_fee38'].sum():,.2f} over 3yr")
df.to_csv("odd_lot_econ_corrected.csv",index=False)
print("\nwrote odd_lot_econ_corrected.csv")
