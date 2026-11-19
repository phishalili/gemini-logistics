import json, urllib.request, collections, statistics
j=json.loads(urllib.request.urlopen(urllib.request.Request("https://mzoe-gor.hr/data.json",headers={"User-Agent":"Mozilla/5.0"}),timeout=60).read())
print("keys",list(j.keys()))
for k in j:
    if isinstance(j[k],list) and j[k]: print(k,len(j[k]),json.dumps(j[k][0],ensure_ascii=False)[:400])
vr={g["id"]:g for g in j["gorivos"]}
print("vrste",json.dumps(j.get("vrsta_gorivas") or j.get("vrstaGorivas") or "",ensure_ascii=False)[:800])
by=collections.defaultdict(list)
for st in j["postajas"]:
    for c in st.get("cjenici",[]):
        g=vr.get(c.get("gorivo_id"));
        if g and c.get("cijena"): by[(g.get("vrsta_goriva_id"),g.get("naziv"))].append(float(c["cijena"]))
for k,v in sorted(by.items(),key=lambda x:str(x[0])):
    print(k,len(v),min(v),statistics.median(v),max(v))
# motorway stations
mw=[st for st in j["postajas"] if any(w in (st.get("naziv","")+" "+st.get("adresa","")).lower() for w in ["autocest","a1","a3","a4","a6","odmorište","odmoriste"])]
print("motorway-ish",len(mw))
for st in mw[:40]:
    d=[(vr[c["gorivo_id"]].get("vrsta_goriva_id"),vr[c["gorivo_id"]].get("naziv"),c["cijena"]) for c in st.get("cjenici",[]) if c.get("gorivo_id") in vr]
    print(st.get("naziv"),"|",st.get("adresa"),"|",[x for x in d if x[0] in (7,8)])
print(json.dumps({k:v for k,v in j["postajas"][0].items() if k!="cjenici"},ensure_ascii=False)[:600])
