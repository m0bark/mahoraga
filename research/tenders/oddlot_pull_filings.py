import json,re,sys,io,time,gzip,urllib.request
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
UA={"User-Agent":"Mahoraga Research m0ba.c0ffe@gmail.com","Accept":"*/*"}
def get(u,tries=4):
    for i in range(tries):
        try:
            r=urllib.request.Request(u,headers=UA)
            with urllib.request.urlopen(r,timeout=60) as f:
                b=f.read()
                if f.headers.get("Content-Encoding")=="gzip": b=gzip.decompress(b)
            return b.decode("utf-8","ignore")
        except Exception as e:
            if i==tries-1: raise
            time.sleep(1.5*(i+1))
def strip(h):
    h=re.sub(r"(?is)<(script|style).*?</\1>"," ",h)
    h=re.sub(r"(?s)<[^>]+>"," ",h)
    for a,b in [("&nbsp;"," "),("&amp;","&"),("&#8217;","'"),("&#146;","'"),("&#8212;","-"),("&#8211;","-"),("&rsquo;","'")]:
        h=h.replace(a,b)
    return re.sub(r"\s+"," ",h)
TARGETS=[("SCHL","0000866729"),("WIX","0001576789"),("YEXT","0001614178"),
("WEX","0001309108"),("INCY","0000879169"),("MNST","0000865752"),
("COKE","0000317540"),("CNNE","0001704720"),("OSPN","0001044777"),
("GPRK","0001464591"),("RUM","0001830081"),("EXFY","0001476840"),
("ABUS","0001447028"),("MTBLY","0001509223"),("OPTU","0001702780"),
("ZH","0001835724"),("CFNB","0000803016"),("IMO","0000049938"),
("TORO","0001941131"),("RBNE","0002039060"),("HTT","0001692705"),
("ATIP","0001815849"),("SQFT","0001080657"),("ELAB","0001840563"),
("ANEB","0001815974"),("MLCI","0002051820")]
out={}
for tic,cik in TARGETS:
    try:
        sub=json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
        rec=sub["filings"]["recent"]
        rows=[(rec["filingDate"][i],rec["form"][i],rec["accessionNumber"][i],rec["primaryDocument"][i])
              for i in range(len(rec["form"])) if rec["form"][i].startswith("SC TO-I") and rec["filingDate"][i]>="2023-09-01"]
        if not rows: print(f"{tic}: none"); continue
        rows.sort(); first,last=rows[0],rows[-1]
        res={"n_amend":len(rows)}
        for tag,row in (("OFFER",first),("FINAL",last)):
            acc=row[2].replace("-","")
            url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{row[3]}"
            res[tag]={"date":row[0],"form":row[1],"url":url,"text":strip(get(url))}
            time.sleep(0.3)
        out[tic]=res
        print(f"{tic:6s} OFFER {res['OFFER']['date']} ({len(res['OFFER']['text']):7d}c) FINAL {res['FINAL']['date']} ({len(res['FINAL']['text']):7d}c) amend={len(rows)}")
    except Exception as e:
        print(f"{tic}: ERR {type(e).__name__} {e}")
    time.sleep(0.4)
json.dump(out,open("terms_raw.json","w",encoding="utf-8"))
print("saved", len(out))
