"""SIPRI Arms Transfers Database: deliveries of major conventional arms, supplier to recipient, by year, in TIV."""
import base64
import csv
import io
import json
import urllib.error
import urllib.request

import kg
from loaders._money_helpers import fetch

API = "https://atbackend.sipri.org/api/p/"
FIRST_YEAR, LAST_YEAR = 1950, 2025
# SIPRI names that differ from the ISO names in kg.places
ALIASES = {
    "laos": "LAO", "turkiye": "TUR", "vatican (holy see)": "VAT", "viet nam": "VNM", "cote d'ivoire": "CIV",
    "dr congo": "COD", "congo": "COG", "eswatini": "SWZ", "gambia": "GMB", "russia": "RUS", "iran": "IRN",
    "syria": "SYR", "south korea": "KOR", "north korea": "PRK", "taiwan": "TWN", "moldova": "MDA", "tanzania": "TZA",
    "bosnia-herzegovina": "BIH", "brunei": "BRN", "cabo verde": "CPV", "palestine": "PSE", "micronesia": "FSM",
    "saint vincent": "VCT", "united kingdom": "GBR", "united states": "USA", "bolivia": "BOL", "venezuela": "VEN",
    "kosovo": "XKX", "north macedonia": "MKD", "czechia": "CZE", "timor-leste": "TLS", "eswatini": "SWZ",
    "myanmar": "MMR", "burkina faso": "BFA", "netherlands": "NLD", "slovakia": "SVK", "libya": "LBY",
}


def post(path, filters):
    body = json.dumps({"filters": filters, "logic": "AND"}).encode()
    for i in range(3):
        try:
            req = urllib.request.Request(API + path, data=body, headers={"Content-Type": "application/json", "User-Agent": kg.UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return base64.b64decode(json.load(r)["bytes"]).decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code in (400, 404, 500):
                return ""
            if i == 2:
                raise
    return ""


def flt(field, value1="", value2="", ids=()):
    return {"field": field, "oldField": "", "condition": "contains" if ids or field.startswith(("Year", "Recipient", "Supplier")) else "",
            "value1": value1, "value2": value2, "listData": list(ids)}


def main():
    l = kg.Loader("sipri_arms", name="SIPRI Arms Transfers Database", publisher="Stockholm International Peace Research Institute",
                  url="https://www.sipri.org/databases/armstransfers", data_url="https://armstransfers.sipri.org/", kinds=["flows"],
                  about="Deliveries of major conventional weapons by supplier and recipient, in SIPRI trend-indicator values (TIV)",
                  coverage="States, rebel groups and international organizations, 1950 to latest, annual", access="open",
                  license="SIPRI: free with source citation", found_by="survey")
    mid = l.measure("arms_tiv", "Major arms deliveries, SIPRI TIV (millions)", "TIV_million", "arms",
                    about="from = supplier, to = recipient, deliveries in the year in millions of SIPRI trend-indicator values (a volume index of military capability, not a price). Rebel groups, international organizations and former states are sipri: places")
    ents = fetch(API + "countries/getAllCountriesTrimmed")
    iso = dict(l.cur.execute("SELECT lower(name), id FROM kg.places WHERE kind = 'country'").fetchall())
    iso3 = dict(l.cur.execute("SELECT iso3, id FROM kg.places WHERE kind = 'country'").fetchall())
    unmatched = []

    def place(name, code):
        n = name.lower()
        pid = iso3.get(ALIASES[n]) if n in ALIASES else iso.get(n)
        if not pid:
            pid = l.other_place("sipri:" + code, name)
            if not name.endswith("*") and "unknown" not in n:
                unmatched.append(name)
        return pid

    by_name = {e["Name"]: e["CountryCode"] for e in ents}
    for e in sorted(ents, key=lambda e: e["Name"]):
        name, code = e["Name"], e["CountryCode"]
        if code in ("MUL", "ZZZ") or l.done(code):
            continue
        txt = post("trades/import-export-csv/", [flt("Year range 1", FIRST_YEAR, LAST_YEAR), flt("Supplier", ids=[e["EntityId"]]),
                                                 flt("DeliveryType", "delivered"), flt("Status", "0")])
        lines = txt.splitlines()
        start = next((i for i, x in enumerate(lines) if x.startswith("Recipient,")), None)
        with l.part(code):
            if start is None:
                continue
            rows = list(csv.reader(lines[start:]))
            years = [(i, int(h)) for i, h in enumerate(rows[0]) if h.isdigit()]
            sp = place(name, code)
            for r in rows[1:]:
                if not r or r[0].startswith("Total") or r[0] not in by_name:
                    continue
                rp = place(r[0], by_name[r[0]])
                if rp == sp:
                    continue
                for i, y in years:
                    if i < len(r) and r[i] not in ("", None):
                        l.flow(mid, y, sp, rp, None, float(r[i]))
    if unmatched:
        print("unmatched:", sorted(set(unmatched)))
    l.finish()


if __name__ == "__main__":
    main()
