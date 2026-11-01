"""World Bank International Debt Statistics: public and publicly guaranteed external debt stock, creditor to debtor."""
import kg
from loaders._money_helpers import Countries, fetch

API = "https://api.worldbank.org/v2/sources/6/"
SERIES = "DT.DOD.DPPG.CD"
# creditor names in IDS that differ from the ISO names in kg.places
ALIASES = {
    "germany, fed. rep. of": "DEU", "turkiye": "TUR", "bosnia-herzegovina": "BIH", "slovak republic": "SVK",
    "russian federation": "RUS", "moldova": "MDA", "congo, rep.": "COG", "congo, dem. rep.": "COD",
    "gambia, the": "GMB", "cote d`ivoire, republic of": "CIV", "somalia, fed. rep.": "SOM",
    "tanzania": "TZA", "sao tome & principe": "STP", "united states": "USA", "trinidad & tobago": "TTO",
    "antigua": "ATG", "st. kitts and nevis": "KNA", "st. lucia": "LCA", "st. vincent & the grenadines": "VCT",
    "venezuela, republic bolivarian": "VEN", "iran, islamic republic of": "IRN", "syrian arab republic": "SYR",
    "yemen, republic of": "YEM", "korea, d.p.r. of": "PRK", "korea, republic of": "KOR",
    "lao people's democratic rep.": "LAO", "brunei": "BRN", "viet nam": "VNM", "hong kong": "HKG", "macao": "MAC",
    "micronesia fed sts": "FSM", "kyrgyz republic": "KGZ", "united kingdom": "GBR", "bolivia": "BOL",
    "netherlands": "NLD", "north macedonia": "MKD", "czechia": "CZE", "myanmar": "MMR", "eswatini": "SWZ",
    "cabo verde": "CPV", "taiwan": "TWN", "kosovo": "XKX", "virgin is.(us)": "VIR", "neth. antilles": "ANT",
    "pacific is. (us)": None, "new caledonia (fr.)": "NCL", "reunion": "REU", "guadeloupe": "GLP",
}


def main():
    l = kg.Loader("wb_ids", name="International Debt Statistics", publisher="World Bank",
                  url="https://www.worldbank.org/en/programs/debt-statistics/ids", data_url=API, kinds=["flows"],
                  about="External debt of low and middle income countries by creditor: bilateral, multilateral, bondholders",
                  coverage="Debtor countries reporting to the World Bank, creditor detail, annual, 1970 on", access="open",
                  license="CC BY 4.0", found_by="survey")
    mid = l.measure("debt_stock_usd", "External debt stock, public and publicly guaranteed, USD", "USD", "debt",
                    about="from = creditor, to = debtor country (the reporter), year-end stock of public and publicly guaranteed external debt outstanding and disbursed, current USD. Creditor is a country, a multilateral or lender group (ids: places), or world for the all-creditor total, so do not add them together")
    cs = Countries(l)
    cps = {v["id"]: v["value"].replace("\xa0", "").strip()
           for v in fetch(API + "counterpart-area?format=json&per_page=400")["source"][0]["concept"][0]["variable"]}
    cp_place = {}
    for cid, name in cps.items():
        if cid == "WLD":
            cp_place[cid] = l.place("world")
        else:
            iso3 = ALIASES.get(name.lower())
            pid = (iso3 and l.country(iso3=iso3)) or l.country(name=name)
            if not pid and cid.isdigit() and int(cid) < 900 and name.lower() not in ALIASES:
                cs.misses[name] = cs.misses.get(name, 0) + 1
            cp_place[cid] = pid or l.other_place("ids:" + cid, name)
    debtors = l.cur.execute("SELECT iso3, id FROM kg.places WHERE kind = 'country' AND iso3 IS NOT NULL ORDER BY iso3").fetchall()
    for iso3, pid in debtors:
        if l.done(iso3):
            continue
        try:
            doc = fetch("%scountry/%s/series/%s/counterpart-area/all/time/all?format=json&per_page=30000" % (API, iso3, SERIES))
        except Exception as e:
            if "400" in str(e) or "404" in str(e):
                doc = None
            else:
                raise
        with l.part(iso3):
            for x in (doc or {}).get("source", {}).get("data", []):
                if x["value"] is None:
                    continue
                v = {c["concept"]: c["id"] for c in x["variable"]}
                cid = v["Counterpart-Area"]
                if cp_place.get(cid) and cp_place[cid] != pid:
                    l.flow(mid, int(v["Time"][2:]), cp_place[cid], pid, None, float(x["value"]))
    cs.report()
    l.finish()


if __name__ == "__main__":
    main()
