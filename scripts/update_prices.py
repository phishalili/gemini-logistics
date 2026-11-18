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
    for code, country in GPP.items():
        try:
            v = gpp_price(country)
            if SANE[0] <= v <= SANE[1]:
                diesel[code] = v; src[code] = "globalpetrolprices.com " + today
        except Exception as e:
            print(country, "failed:", e, file=sys.stderr)
    stations = dict(cur.get("stations", {}))
    for code, fn in (("AT", at_stations), ("DE", de_stations)):
        st = [x for x in fn() if SANE[0] <= x["price"] <= SANE[1]]
        if st:
            stations[code] = sorted(st, key=lambda x: x["price"])
            diesel[code] = stations[code][0]["price"]   # pika më e lirë përgjatë rrugës
            src[code] = ("E-Control" if code == "AT" else "Tankerkönig") + " (pika reale) " + today
    changed = diesel != cur.get("diesel") or stations != cur.get("stations", {})
    out = {"updated": today if changed else cur.get("updated", today), "checked": today, "diesel": diesel, "sources": src, "stations": stations}
    json.dump(out, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
