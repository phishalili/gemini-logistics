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
    raise RuntimeError("price not found for " + country)


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
    changed = diesel != cur.get("diesel")
    out = {"updated": today if changed else cur.get("updated", today), "checked": today, "diesel": diesel, "sources": src}
    json.dump(out, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
