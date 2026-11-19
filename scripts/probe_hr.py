import json, urllib.request
def get(u):return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=60).read())
d=get("https://goriva.si/api/v1/search/?position=46.1,14.8&radius=300000")
print("SI keys",list(d.keys()),d.get("count"),len(d.get("results",[])),d.get("next"))
print(json.dumps(d["results"][0],ensure_ascii=False)[:500])
mw=[x for x in d["results"] if "AC" in (x.get("name") or "") or "avtocest" in (x.get("name","")+(x.get("address") or "")).lower()]
print("SI motorway-like",len(mw),[ (x["name"],x["prices"].get("dizel")) for x in mw[:10]])
