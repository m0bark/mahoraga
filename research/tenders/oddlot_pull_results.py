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
    h=re.sub(r"&#\d+;|&[a-z]+;"," ",h)
    return re.sub(r"\s+"," ",h)
d=json.load(open("terms_raw.json",encoding="utf-8"))
PAT=re.compile(r"(purchase price of \$|final purchase price|proration|prorated|odd lot|accepted for pur|will purchase|per share|per Share|per ADS)",re.I)
res={}
for tic,v in d.items():
    u=v["FINAL"]["url"]; base=u.rsplit("/",1)[0]
    try:
        idx=json.loads(get(base+"/index.json"))
        files=[it["name"] for it in idx["directory"]["item"] if re.search(r"(ex.?99|ex-99|d?ex99|pressrelease|prel)",it["name"],re.I) and it["name"].endswith((".htm",".html",".txt"))]
        if not files:
            files=[it["name"] for it in idx["directory"]["item"] if it["name"].endswith(".htm")][:3]
        txt=""
        for fn in files[:3]:
            txt+=" "+strip(get(base+"/"+fn)); time.sleep(0.2)
        sents=[s for s in re.split(r"(?<=[.;])\s+",txt) if PAT.search(s) and "$" in s]
        res[tic]=sents[:7]
        print(f"\n##### {tic} FINAL {v['FINAL']['date']}  files={files[:3]}")
        for s in sents[:7]: print("   >",s[:400])
    except Exception as e:
        print(f"{tic}: ERR {e}")
    time.sleep(0.3)
json.dump(res,open("final_results.json","w",encoding="utf-8"))
