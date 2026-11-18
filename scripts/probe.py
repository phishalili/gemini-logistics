import urllib.request, re, json
UA={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36","Accept":"*/*"}
def g(u):
    with urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=60) as r: return r.read().decode("utf-8","replace")
d=g("https://www.clever-tanken.de/tankstelle_liste?lat=48.137&lon=11.575&ort=Muenchen&spritsorte=3&r=5")
i=d.find('price-text');print("CTBLOCK",re.sub(r"\s+"," ",d[i-3000:i+600]))
j=json.loads(g("https://mzoe-gor.hr/data.json"));print("HRKEYS",list(j.keys()))
for k,v in j.items():
    if isinstance(v,list) and v and k!="postajas": print("HR",k,len(v),json.dumps(v[:12],ensure_ascii=False)[:1500])
p=j["postajas"][0];print("HRP",json.dumps({x:p[x] for x in p if x!="radnaVremena"},ensure_ascii=False)[:800])
n=g("https://naftasot.com/");t=re.sub(r"<[^>]+>"," ",n);t=re.sub(r"\s+"," ",t);print("NS",t[:2500])
for m in re.findall(r'href="(/[^"]{3,60})"',n)[:40]: print("NSL",m)
h=g("https://holtankoljak.hu/");print("HU",re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",h))[:1500])
for m in re.findall(r'href="([^"]{3,80})"',h)[:60]: print("HUL",m)
