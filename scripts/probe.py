import urllib.request, re, json
UA={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36","Accept":"*/*"}
def g(u):
    with urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=60) as r: return r.read().decode("utf-8","replace")
d=g("https://www.clever-tanken.de/tankstelle_liste?lat=48.137&lon=11.575&ort=Muenchen&spritsorte=3&r=5")
i=d.find('href="/tankstelle_details/');print("CT2",re.sub(r"\s+"," ",d[i:i+2500]))
print("CTN",len(re.findall('tankstelle_details/',d)))
n=g("https://naftasot.com/cmimi-naftes/podujeve");t=re.sub(r"\s+"," ",re.sub(r"<(script|style)[^>]*>.*?</\1>"," ",n,flags=re.S));t=re.sub(r"<[^>]+>"," | ",t);t=re.sub(r"(\s*\|\s*)+"," | ",t);print("NS2",t[:4000])
for m in set(re.findall(r'"(/api/[^"]+|https://api[^"]+)"',n)): print("NSAPI",m)
