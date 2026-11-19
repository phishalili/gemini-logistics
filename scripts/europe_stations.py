"""Pikat e karburantit në Evropë me çmimin e diesel-it, për faqen "Nafta" të app-it -> stations.json.

Vendet me të dhëna të hapura për çdo pikë (pa regjistrim):
- Franca: prix-carburants (data.economie.gouv.fr), të gjitha pikat.
- Italia: MIMIT "prezzo_alle_8" + "anagrafica_impianti_attivi", të gjitha pikat.
- Spanja: Ministerio (geoportal gasolineras), të gjitha pikat.
- Kroacia, Sllovenia, Austria, Gjermania: nga update_prices.py (pikat përgjatë rrugëve kryesore).
Për të mos e bërë skedarin të rëndë, ruhet vetëm pika më e lirë në çdo katror ~20 km.
"""
import csv, io, json, re, sys, datetime, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) price-updater"}
CELL = 0.2   # gradë, rreth 15-22 km


def get(url, binary=False, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = r.read()
    return d if binary else d.decode("utf-8", "replace")


def grid(stations):
    best = {}
    for s in stations:
        if not (0.8 <= s["price"] <= 3.0):
            continue
        k = (round(s["lat"] / CELL), round(s["lng"] / CELL))
        if k not in best or s["price"] < best[k]["price"]:
            best[k] = s
    return list(best.values())


def france():
    url = ("https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/prix-des-carburants-en-france-flux-instantane-v2/"
           "exports/json?select=id,latitude,longitude,adresse,ville,gazole_prix,gazole_maj&where=gazole_prix%20is%20not%20null")
    rows = json.loads(get(url))
    lim = (datetime.date.today() - datetime.timedelta(days=4)).isoformat()
    out = []
    for r in rows:
        try:
            if str(r.get("gazole_maj") or "")[:10] < lim:
                continue
            la, lo = float(r["latitude"]), float(r["longitude"])
            if abs(la) > 90:
                la, lo = la / 100000, lo / 100000
            out.append({"c": "FR", "name": "", "address": (r.get("adresse") or "").title(), "city": (r.get("ville") or "").title(),
                        "lat": round(la, 5), "lng": round(lo, 5), "price": round(float(r["gazole_prix"]), 3)})
        except Exception:
            continue
    print("FR stations:", len(out))
    return out


def italy():
    an = get("https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv")
    pr = get("https://www.mimit.gov.it/images/exportCSV/prezzo_alle_8.csv")
    def rows(txt):
        lines = txt.splitlines()
        start = next(i for i, l in enumerate(lines) if l.lower().startswith("idimpianto"))
        sep = "|" if "|" in lines[start] else ";"
        return list(csv.reader(lines[start + 1:], delimiter=sep)), [h.strip().lower() for h in lines[start].split(sep)]
    a, ah = rows(an)
    p, ph = rows(pr)
    print("IT headers:", ah, ph)
    ix = lambda h, *names: next(i for i, x in enumerate(h) if any(n in x for n in names))
    ia, ib, ina, iad, ico, ila, ilo = ix(ah, "idimpianto"), ix(ah, "bandiera"), ix(ah, "nome"), ix(ah, "indirizzo"), ix(ah, "comune"), ix(ah, "latitudine"), ix(ah, "longitudine")
    info = {}
    for r in a:
        try:
            info[r[ia]] = (r[ib], r[iad], r[ico], float(r[ila]), float(r[ilo]))
        except Exception:
            continue
    pid, pdesc, pprice, pself = ix(ph, "idimpianto"), ix(ph, "desccarburante"), ix(ph, "prezzo"), ix(ph, "isself")
    best = {}
    for r in p:
        try:
            if r[pdesc].strip().lower() != "gasolio" or r[pself].strip() != "1":
                continue
            v = float(r[pprice].replace(",", "."))
            if r[pid] not in best or v < best[r[pid]]:
                best[r[pid]] = v
        except Exception:
            continue
    out = []
    for k, v in best.items():
        if k in info:
            b, ad, co, la, lo = info[k]
            out.append({"c": "IT", "name": b.title(), "address": ad.title(), "city": co.title(), "lat": round(la, 5), "lng": round(lo, 5), "price": round(v, 3)})
    print("IT stations:", len(out))
    return out


def spain():
    d = json.loads(get("https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/"))
    out = []
    for r in d.get("ListaEESSPrecio", []):
        try:
            v = float(r["Precio Gasoleo A"].replace(",", "."))
            out.append({"c": "ES", "name": r.get("Rótulo", "").title(), "address": r.get("Dirección", "").title(), "city": r.get("Localidad", "").title(),
                        "lat": round(float(r["Latitud"].replace(",", ".")), 5), "lng": round(float(r["Longitud (WGS84)"].replace(",", ".")), 5), "price": round(v, 3)})
        except Exception:
            continue
    print("ES stations:", len(out))
    return out


def croatia_all():
    """Të gjitha pikat në Kroaci (mzoe-gor.hr). Çmimi = eurodizeli më i lirë (i rregullt), jo premium."""
    j = json.loads(get("https://mzoe-gor.hr/data.json"))
    vrsta = {g["id"]: g.get("vrsta_goriva_id") for g in j.get("gorivos", [])}
    comp = {o["id"]: o.get("naziv", "") for o in j.get("obvezniks", [])}
    out = []
    for st in j.get("postajas", []):
        try:
            a, b = float(st["long"]), float(st["lat"])
            la, lo = (a, b) if a > b else (b, a)
        except Exception:
            continue
        pr = [float(c["cijena"]) for c in st.get("cjenici", []) if vrsta.get(c.get("gorivo_id")) in (7, 8) and c.get("cijena")]
        pr = [x for x in pr if 1.2 <= x <= 2.6]
        if not pr:
            continue
        brand = re.sub(r"\s*d\.o\.o\.?|\s*d\.d\.?|\s*–\s*Industrija nafte", "", comp.get(st.get("obveznik_id"), "")).strip()
        nm = st.get("naziv") or ""
        out.append({"c": "HR", "name": (brand + " " + nm).strip(), "address": st.get("adresa") or "", "city": st.get("mjesto") or "",
                    "lat": round(la, 5), "lng": round(lo, 5), "price": round(min(pr), 3),
                    "mw": bool(re.search(r"autocest|odmori", (nm + " " + (st.get("adresa") or "")).lower()))})
    print("HR all stations:", len(out))
    return out


def slovenia_all():
    """Të gjitha pikat në Slloveni (goriva.si), dizeli i rregullt. AC = pikë në autostradë."""
    out, url, n = [], "https://goriva.si/api/v1/search/?position=46.1,14.8&radius=300000", 0
    while url and n < 60:
        d = json.loads(get(url)); n += 1
        for x in d.get("results", []):
            v = (x.get("prices") or {}).get("dizel")
            if not v:
                continue
            nm = x.get("name") or ""
            out.append({"c": "SI", "name": nm.title(), "address": (x.get("address") or "").title(), "city": "",
                        "lat": round(x["lat"], 5), "lng": round(x["lng"], 5), "price": round(float(v), 3), "mw": bool(re.search(r"\bAC\b", nm))})
        url = d.get("next")
    print("SI all stations:", len(out))
    return out


def no_outliers(lst):
    import statistics
    if not lst:
        return lst
    med = statistics.median(x["price"] for x in lst)
    return [x for x in lst if x["price"] >= 0.9 * med]


def build(route_stations):
    """route_stations: lista nga update_prices.py (HR, SI, AT, DE). Kthen stations.json."""
    try:
        cur = json.load(open("stations.json"))
    except Exception:
        cur = {"stations": []}
    old = {}
    for s in cur.get("stations", []):
        old.setdefault(s["c"], []).append(s)
    out, today = [], datetime.date.today().isoformat()
    for code, fn in (("FR", france),):   # Italia (MIMIT) bllokon shkarkimet nga jashtë Italisë
        try:
            g = grid(fn())
            print(code, "grid:", len(g))
            out += g if g else old.get(code, [])
        except Exception as e:
            print(code, "failed:", e, file=sys.stderr)
            out += old.get(code, [])
    full = {}
    for code, fn in (("HR", croatia_all), ("SI", slovenia_all)):
        try:
            full[code] = no_outliers(fn())
        except Exception as e:
            print(code, "all failed:", e, file=sys.stderr)
    route_stations = [x for x in route_stations if x["c"] not in full or not full[x["c"]]]
    for code, l in full.items():
        route_stations += l
    have = {x["c"] for x in route_stations}
    out += route_stations + [s for c, l in old.items() if c in ("HR", "SI", "AT", "DE") and c not in have for s in l]
    # vetëm fushat që i duhen app-it, numrat e shkurtuar
    out = [{**{k: s.get(k, "") for k in ("c", "name", "address", "city", "lat", "lng", "price")}, **({"mw": 1} if s.get("mw") else {})} for s in out]
    json.dump({"updated": today, "stations": out}, open("stations.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print("stations.json:", len(out), {c: sum(1 for s in out if s["c"] == c) for c in sorted({s["c"] for s in out})})
