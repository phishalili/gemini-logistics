"""Përditëson prices.json me çmimet e naftës (diesel, €/L) për vendet e rrugës.

Burimet:
- Vendet e BE-së (AT, DE, HR, SI, HU): EU Weekly Oil Bulletin (Komisioni Evropian), çmimet me taksa.
- Kosova dhe Serbia (nuk janë në buletinin e BE-së): globalpetrolprices.com.
Nëse një burim dështon, mbetet çmimi i fundit i njohur. Asnjë çmim nuk zëvendësohet me zero.
"""
import io, json, re, sys, datetime, urllib.request

OUT = "prices.json"
UA = {"User-Agent": "Mozilla/5.0 (price-updater)"}
EU = {"AT": "Austria", "DE": "Germany", "HR": "Croatia", "SI": "Slovenia", "HU": "Hungary"}
GPP = {"XK": "Kosovo", "RS": "Serbia"}
SANE = (0.8, 3.0)  # €/L, çdo gjë jashtë këtij intervali injorohet


def get(url, binary=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def eu_prices():
    """Gjen skedarin xlsx 'prices with taxes' në faqen e buletinit dhe lexon diesel për vendet tona."""
    import openpyxl
    page = get("https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en")
    links = re.findall(r'href="([^"]+)"[^>]*>([^<]*)<', page)
    cand = [h for h, t in links if ("xlsx" in h.lower() or "download" in h.lower())
            and "with" in (h + t).lower() and "tax" in (h + t).lower() and "histor" not in (h + t).lower()]
    print("EU candidate links:", cand[:5])
    if not cand:
        raise RuntimeError("no EU xlsx link found")
    cand = [c for c in cand if "without" not in c.lower()] or cand
    dated = lambda c: (re.findall(r"(20\d\d-\d\d-\d\d)", c) or ["0"])[-1]
    cand.sort(key=dated, reverse=True)
    print("EU file used:", cand[0])
    url = cand[0] if cand[0].startswith("http") else "https://energy.ec.europa.eu" + cand[0]
    wb = openpyxl.load_workbook(io.BytesIO(get(url, binary=True)), data_only=True)
    ws = wb.worksheets[0]
    rows = [[c for c in r] for r in ws.iter_rows(values_only=True)]
    # gjej kolonën e diesel-it nga titujt
    col = None
    for r in rows[:15]:
        for i, c in enumerate(r):
            if isinstance(c, str) and ("diesel" in c.lower() or "gas oil" in c.lower() or "gasoil" in c.lower()) and "heat" not in c.lower():
                col = i; break
        if col is not None:
            break
    if col is None:
        raise RuntimeError("diesel column not found")
    for r in rows[:6]:
        print("EU header:", [str(c)[:40] for c in r[:8]])
    print("EU diesel column:", col)
    out = {}
    for r in rows:
        name = next((c for c in r if isinstance(c, str)), "")
        for code, country in EU.items():
            if name.strip().lower().startswith(country.lower()):
                v = r[col]
                try:
                    v = float(str(v).replace(",", ""))
                except ValueError:
                    continue
                if v > 100:  # € për 1000 L
                    v = v / 1000
                out[code] = round(v, 3)
                print("EU row", code, [str(c)[:20] for c in r[:8]])
    return out


def gpp_price(country):
    html = get(f"https://www.globalpetrolprices.com/{country}/diesel_prices/")
    m = re.search(r"([0-9]+\.[0-9]+)\s*(?:Euro|EUR)\s*per liter", html)
    if m:
        return round(float(m.group(1)), 3)
    # Serbia: çmimi në USD -> EUR me kursin e ECB
    m = re.search(r"([0-9]+\.[0-9]+)\s*U\.?S\.?\s*Dollars?\s*per liter", html)
    if m:
        usd = float(m.group(1))
        x = get("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml")
        rate = float(re.search(r"currency='USD' rate='([0-9.]+)'", x).group(1))
        return round(usd / rate, 3)
    i = html.lower().find("per liter")
    print(country, "snippet:", re.sub(r"<[^>]+>", " ", html[max(0, i - 400):i + 200])[:600] if i >= 0 else html[:300])
    raise RuntimeError("price not found for " + country)


# ---- Çmimet reale nga pikat e karburantit përgjatë rrugës ----
AT_POINTS = {"Spielfeld": (46.708, 15.633), "Graz": (47.070, 15.440), "Salzburg": (47.810, 13.040)}
DE_POINTS = {"München": (48.137, 11.575), "Nürnberg": (49.452, 11.077), "Frankfurt": (50.110, 8.682), "Dortmund": (51.514, 7.468)}


def at_stations():
    """Austria: E-Control Spritpreisrechner (falas, pa çelës). Kthen pikat më të lira të diesel-it."""
    out = []
    for town, (la, lo) in AT_POINTS.items():
        try:
            data = json.loads(get(f"https://api.e-control.at/sprit/1.0/search/gas-stations/by-address?latitude={la}&longitude={lo}&fuelType=DIE&includeClosed=false"))
            best = None
            for st in data:
                pr = [p.get("amount") for p in st.get("prices", []) if p.get("fuelType") == "DIE" and p.get("amount")]
                if pr and (best is None or pr[0] < best["price"]):
                    loc = st.get("location", {})
                    best = {"name": st.get("name", ""), "address": loc.get("address", ""), "city": loc.get("city", town), "price": round(float(pr[0]), 3), "near": town}
            if best:
                out.append(best)
        except Exception as e:
            print("AT", town, "failed:", e, file=sys.stderr)
    return out


def de_stations():
    """Gjermania: Tankerkönig (MTS-K). Duhet çelësi falas në sekretin TANKERKOENIG_KEY."""
    import os
    key = os.environ.get("TANKERKOENIG_KEY", "").strip()
    if not key:
        print("DE: no TANKERKOENIG_KEY yet, skipping", file=sys.stderr)
        return []
    out = []
    for town, (la, lo) in DE_POINTS.items():
        try:
            d = json.loads(get(f"https://creativecommons.tankerkoenig.de/json/list.php?lat={la}&lng={lo}&rad=10&sort=price&type=diesel&apikey={key}"))
            st = next((x for x in d.get("stations", []) if x.get("price") and x.get("isOpen", True)), None)
            if st:
                out.append({"name": st.get("brand") or st.get("name", ""), "address": f"{st.get('street','')} {st.get('houseNumber','') or ''}".strip(), "city": st.get("place", town), "price": round(float(st["price"]), 3), "near": town})
        except Exception as e:
            print("DE", town, "failed:", e, file=sys.stderr)
    return out


RSD_PER_EUR = 117.2   # dinari mbahet afër këtij kursi nga Banka e Serbisë


def kosovo_price():
    """Kosova: mesatarja e diesel-it nga naftasot.com (çmimet nga vetë kompanitë, përditësim ditor)."""
    html = get("https://naftasot.com/")
    m = re.search(r"Nafta \(dizel\)[^0-9]{0,80}?([0-9]+[.,][0-9]+)\s*\u20ac", html)
    if not m:
        raise RuntimeError("naftasot pattern not found")
    v = float(m.group(1).replace(",", "."))
    d = re.search(r"P\u00ebrdit\u00ebsuar:?\s*([^<\n]{4,30})", html)
    print("Kosovo naftasot:", v, d.group(1) if d else "")
    return round(v, 3)


def serbia_price():
    """Serbia: çmimi maksimal i evrodizelit që cakton Ministria e Tregtisë çdo të premte (lajmi në danas.rs)."""
    page = get("https://www.danas.rs/?s=cene+goriva")
    links = list(dict.fromkeys(re.findall(r'href="(https://www\.danas\.rs/vesti/ekonomija/[^"]*cene-goriva[^"]*)"', page)))
    print("Serbia candidate articles:", links[:3])
    for url in links[:4]:
        art = get(url)
        m = re.search(r"evrodizel[a-z]*[^.]{0,160}?maksimalno\s*([0-9]{3})\s*dinara", art, re.I) or re.search(r"evrodizel[a-z]*[^.]{0,120}?([0-9]{3})\s*dinara", art, re.I)
        if m:
            rsd = float(m.group(1))
            print("Serbia evrodizel RSD:", rsd, url)
            return round(rsd / RSD_PER_EUR, 3), url
    raise RuntimeError("serbia price not found")


# ---- Pikat e karburantit përgjatë korridorit Kosovë → Gjermani (për çdo udhëtim) ----
import math, time
def _km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))

HR_POINTS = {"Lipovac (kufiri)": (45.05, 19.08), "Slavonski Brod": (45.16, 18.02), "Nova Gradiška": (45.25, 17.38),
             "Kutina": (45.48, 16.78), "Zagreb": (45.80, 15.98), "Bregana": (45.84, 15.69), "Krapina / Macelj": (46.16, 15.87)}
SI_POINTS = {"Obrežje": (45.85, 15.69), "Novo Mesto": (45.80, 15.17), "Ljubljana": (46.05, 14.50), "Kranj": (46.24, 14.36),
             "Jesenice / Karavanke": (46.44, 14.06), "Ptuj": (46.42, 15.87), "Maribor": (46.55, 15.65), "Šentilj": (46.68, 15.65)}
AT_ROUTE = {"Spielfeld": (46.708, 15.633), "Graz": (47.070, 15.440), "Liezen": (47.57, 14.24), "Wels": (48.16, 14.03),
            "Villach": (46.61, 13.85), "Salzburg": (47.810, 13.040)}
DE_ROUTE = {"Rosenheim": (47.856, 12.128), "München": (48.137, 11.575), "Augsburg": (48.371, 10.898), "Ulm": (48.401, 9.987),
            "Stuttgart": (48.776, 9.183), "Karlsruhe": (49.007, 8.404), "Mannheim": (49.487, 8.466), "Frankfurt": (50.110, 8.682),
            "Würzburg": (49.792, 9.953), "Nürnberg": (49.452, 11.077), "Regensburg": (49.013, 12.102), "Saarbrücken": (49.240, 6.997),
            "Köln": (50.938, 6.960), "Düsseldorf": (51.227, 6.773), "Dortmund": (51.514, 7.468), "Kassel": (51.312, 9.479),
            "Hannover": (52.375, 9.732), "Hamburg": (53.551, 9.993), "Bremen": (53.079, 8.801), "Berlin": (52.520, 13.405),
            "Leipzig": (51.340, 12.375), "Dresden": (51.050, 13.738)}

def _best(lst, n=2):
    lst = [x for x in lst if SANE[0] <= x["price"] <= SANE[1]]
    return sorted(lst, key=lambda x: x["price"])[:n]

def route_hr():
    j = json.loads(get("https://mzoe-gor.hr/data.json"))
    vrsta = {g["id"]: g.get("vrsta_goriva_id") for g in j.get("gorivos", [])}
    comp = {o["id"]: o.get("naziv", "") for o in j.get("obvezniks", [])}
    out = []
    for town, pt in HR_POINTS.items():
        near = []
        for st in j.get("postajas", []):
            try:
                a, b = float(st["long"]), float(st["lat"])   # në këtë burim lat/long janë të ndërruara
                la, lo = (a, b) if a > b else (b, a)
            except Exception:
                continue
            if _km(pt, (la, lo)) > 8:
                continue
            pr = [c["cijena"] for c in st.get("cjenici", []) if vrsta.get(c.get("gorivo_id")) == 8 and c.get("cijena")] or \
                 [c["cijena"] for c in st.get("cjenici", []) if vrsta.get(c.get("gorivo_id")) == 7 and c.get("cijena")]
            if pr:
                brand = re.sub(r"\s*d\.o\.o\.?|\s*d\.d\.?", "", comp.get(st.get("obveznik_id"), "")).strip()
                near.append({"c": "HR", "name": (brand + " " + st.get("naziv", "")).strip(), "address": st.get("adresa", ""),
                             "city": st.get("mjesto", ""), "lat": round(la, 5), "lng": round(lo, 5), "price": round(float(min(pr)), 3), "near": town})
        out += _best(near)
    return out

def route_si():
    out = []
    for town, (la, lo) in SI_POINTS.items():
        try:
            d = json.loads(get(f"https://goriva.si/api/v1/search/?position={la},{lo}&radius=8000"))
            near = [{"c": "SI", "name": x.get("name", "").title(), "address": (x.get("address") or "").title(),
                     "city": town.split(" /")[0], "lat": x.get("lat"), "lng": x.get("lng"), "price": float(x["prices"]["dizel"]), "near": town}
                    for x in d.get("results", []) if (x.get("prices") or {}).get("dizel")]
            out += _best(near)
        except Exception as e:
            print("SI", town, "failed:", e, file=sys.stderr)
        time.sleep(0.5)
    return out

def route_at():
    out = []
    for town, (la, lo) in AT_ROUTE.items():
        try:
            data = json.loads(get(f"https://api.e-control.at/sprit/1.0/search/gas-stations/by-address?latitude={la}&longitude={lo}&fuelType=DIE&includeClosed=false"))
            near = []
            for st in data:
                pr = [p.get("amount") for p in st.get("prices", []) if p.get("fuelType") == "DIE" and p.get("amount")]
                if pr:
                    loc = st.get("location", {})
                    near.append({"c": "AT", "name": st.get("name", ""), "address": loc.get("address", ""), "city": loc.get("city", ""),
                                 "lat": loc.get("latitude", la), "lng": loc.get("longitude", lo), "price": round(float(pr[0]), 3), "near": town})
            out += _best(near)
        except Exception as e:
            print("AT", town, "failed:", e, file=sys.stderr)
        time.sleep(0.5)
    return out

def route_de():
    """Gjermania: lista publike e clever-tanken.de (çmimet zyrtare MTS-K), pa regjistrim."""
    import html as H
    out = []
    for town, (la, lo) in DE_ROUTE.items():
        try:
            d = get(f"https://www.clever-tanken.de/tankstelle_liste?lat={la}&lon={lo}&ort={urllib.request.quote(town)}&spritsorte=3&r=8")
            near = []
            for m in re.finditer(r"generateDygraph\(event, '\d+', 'hover', '((?:[^'\\]|\\.)*)', '((?:[^'\\]|\\.)*)' \)\">(.{0,600}?)<sup>(\d)</sup>", d, re.S):
                pm = re.search(r"(\d)\.(\d\d)\s*$", re.sub(r"<[^>]+>", " ", m.group(3)).strip())
                if not pm:
                    continue
                near.append({"c": "DE", "name": H.unescape(m.group(1)).replace("\\'", "'").title(), "address": H.unescape(m.group(2)).replace("\\'", "'"),
                             "city": town, "lat": la, "lng": lo, "price": float(f"{pm.group(1)}.{pm.group(2)}{m.group(4)}"), "near": town})
            out += _best(near)
        except Exception as e:
            print("DE", town, "failed:", e, file=sys.stderr)
        time.sleep(1)
    return out

def route_stations():
    out = []
    for name, fn in (("HR", route_hr), ("SI", route_si), ("AT", route_at), ("DE", route_de)):
        try:
            r = fn(); print("route", name, len(r)); out += r
        except Exception as e:
            print("route", name, "failed:", e, file=sys.stderr)
    return out


def main():
    try:
        cur = json.load(open(OUT))
    except Exception:
        cur = {"diesel": {}, "sources": {}}
    diesel, src, today = dict(cur.get("diesel", {})), dict(cur.get("sources", {})), datetime.date.today().isoformat()
    try:
        for k, v in eu_prices().items():
            if SANE[0] <= v <= SANE[1]:
                diesel[k] = v; src[k] = "EU Weekly Oil Bulletin " + today
    except Exception as e:
        print("EU source failed:", e, file=sys.stderr)
    try:
        v = kosovo_price()
        if SANE[0] <= v <= SANE[1]:
            diesel["XK"] = v; src["XK"] = "naftasot.com (mesatarja e kompanive) " + today
    except Exception as e:
        print("Kosovo failed:", e, file=sys.stderr)
    try:
        v, url = serbia_price()
        if SANE[0] <= v <= SANE[1]:
            diesel["RS"] = v; src["RS"] = "Çmimi maksimal shtetëror (danas.rs) " + today
    except Exception as e:
        print("Serbia failed:", e, file=sys.stderr)
    stations = dict(cur.get("stations", {}))
    for code, fn in (("AT", at_stations), ("DE", de_stations)):
        st = [x for x in fn() if SANE[0] <= x["price"] <= SANE[1]]
        if st:
            stations[code] = sorted(st, key=lambda x: x["price"])
            diesel[code] = stations[code][0]["price"]   # pika më e lirë përgjatë rrugës
            src[code] = ("E-Control" if code == "AT" else "Tankerkönig") + " (pika reale) " + today
    route = route_stations()
    # hiq pikat me çmim të dyshimtë (p.sh. pika private të flotave), >10% nën mesataren e vendit
    import statistics
    for c in {x["c"] for x in route}:
        med = statistics.median(x["price"] for x in route if x["c"] == c)
        route = [x for x in route if x["c"] != c or x["price"] >= 0.9 * med]
    have = {x["c"] for x in route}
    # çmimi i vendit = mesatarja (mediana) e pikave reale në rrugë, që llogaritja të jetë realiste
    for c in have & {"HR", "SI", "DE"}:
        diesel[c] = round(statistics.median(x["price"] for x in route if x["c"] == c), 3)
        src[c] = {"HR": "mzoe-gor.hr", "SI": "goriva.si", "DE": "clever-tanken.de (MTS-K)"}[c] + " (mediana e pikave në rrugë) " + today
    route += [x for x in cur.get("route", []) if x.get("c") not in have]   # vendi që dështoi mban listën e djeshme
    changed = diesel != cur.get("diesel") or stations != cur.get("stations", {}) or route != cur.get("route", [])
    out = {"updated": today if changed else cur.get("updated", today), "checked": today, "diesel": diesel, "sources": src, "stations": stations, "route": route}
    json.dump(out, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
