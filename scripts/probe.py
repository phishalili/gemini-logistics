import urllib.request, re, json
UA={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36","Accept":"*/*"}
def g(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=40) as r: d=r.read().decode("utf-8","replace"); return r.status,d
    except Exception as e: return "ERR",str(e)
U=["https://goriva.si/api/v1/search/?position=46.05,14.5&radius=5000",
"https://mzoe-gor.hr/data.json",
"https://www.clever-tanken.de/tankstelle_liste?lat=48.137&lon=11.575&ort=Muenchen&spritsorte=3&r=5",
"https://www.mehr-tanken.de/tankstellen?searchText=M%C3%BCnchen&fuelType=2",
"https://holtankoljak.hu/",
"https://naftasot.com/",
"https://www.nis.rs/cene-goriva/",
"https://creativecommons.tankerkoenig.de/json/list.php?lat=48.137&lng=11.575&rad=5&sort=price&type=diesel&apikey=00000000-0000-0000-0000-000000000002"]
for u in U:
    s,d=g(u); print("=====",u,s,len(d)); print(re.sub(r"\s+"," ",d[:1500]))
    if "clever" in u:
        for m in re.finditer(r'(price[^<]{0,80}|\d[.,]\d\d<sup>\d)',d): print("  CT",m.group(0)[:100])
