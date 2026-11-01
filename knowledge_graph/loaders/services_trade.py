"""WTO-OECD Balanced Trade in Services (BaTiS): bilateral services exports by EBOPS 2010 item, balanced series, annual."""
import csv
import json
import time
import urllib.error

import kg
from loaders import _trade_helpers as h

DF = "https://sdmx.oecd.org/public/rest/%s/OECD.SDD.TPS,DSD_BATIS@DF_BATIS,1.0"
JSON = {"Accept": "application/vnd.sdmx.structure+json"}
CSV = {"Accept": "application/vnd.sdmx.data+csv; charset=utf-8"}
AGGREGATES = {"W", "OECD", "EU27_2020"}  # world and country groups: kept out so sums by place do not double count
MEMO = ("SOX", "SPX", "S5")  # overlapping memo groupings, not part of the EBOPS tree
ABOUT = ("Services exported from the 'from' economy to the 'to' economy in the year, USD, from the WTO-OECD balanced series "
         "(exports and imports reported by the two economies reconciled into one figure). Every EBOPS level is stored as "
         "published: S is total services and already includes the groups below it (SC transport) and their items (SC1 sea "
         "transport), so read one code or sum one level, never a prefix of S. Zero values are not stored.")


def fetch(url, headers, dest, tries=12):
    """OECD answers 429 when asked too fast: wait and retry. 404 means no data for that reporter."""
    for i in range(tries):
        try:
            return kg.download(url, dest, headers=headers)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                dest.write_text("")
                return None
            if e.code != 429 or i == tries - 1:
                raise
            time.sleep(300)


def main():
    l = kg.Loader("services_trade", name="WTO-OECD Balanced Trade in Services (BaTiS), bilateral services exports",
                  publisher="OECD and WTO", url="https://www.oecd.org/en/data/datasets/balanced-trade-in-services.html",
                  data_url=DF % "data", kinds=["flows"],
                  about="Bilateral services exports by economy pair and EBOPS 2010 service type, balanced series",
                  coverage="About 200 economies, annual, 2005 to latest year", access="open", license="OECD terms, https://www.oecd.org/en/about/terms-conditions.html", found_by="core")
    d = kg.workdir("services_trade")
    struct = json.load(open(kg.download("https://sdmx.oecd.org/public/rest/dataflow/OECD.SDD.TPS/DSD_BATIS@DF_BATIS/1.0?references=all", d / "structure.json", headers=JSON)))["data"]
    codelist = lambda n: {c["id"]: c for c in next(x for x in struct["codelists"] if x["id"] == n)["codes"]}
    items, areas = codelist("CL_BOP6_ITEM"), codelist("CL_AREA")
    sectors = {}
    for code in sorted((c for c in items if c.startswith("S") and not c.startswith(MEMO)), key=lambda c: (len(c), c)):
        parent = items[code].get("parent")
        if code == "S" or parent in sectors:
            sectors[code] = l.sector("ebops", code, items[code]["name"], parent=sectors.get(parent))
    m = l.measure("services_trade_usd", "Services trade, exporter to importer", "USD", "services_trade", ABOUT)
    l.conn.commit()
    ac = json.load(open(kg.download(DF % "availableconstraint" + "/all/all/TIME_PERIOD", d / "years.json", headers=JSON)))
    span = ac["data"]["dataConstraints"][0]["cubeRegions"][0]["keyValues"][0]["timeRange"]
    years = range(int(span["startPeriod"]["period"][:4]), int(span["endPeriod"]["period"][:4]) + 1)
    places, unmatched = {}, set()

    def place(code):
        if code not in places:
            pid = l.country(iso3=code)
            if not pid and code not in AGGREGATES:
                pid = l.other_place("batis:" + code, areas[code]["name"])
                unmatched.add(code)
            places[code] = pid
        return places[code]

    # one request per year (all economies): the OECD API allows few requests per hour
    for year in years:
        if l.done(str(year)):
            continue
        time.sleep(2)
        f = fetch("%s/..X.S..A.USD_EXC.B?startPeriod=%d&endPeriod=%d" % (DF % "data", year, year), CSV, d / ("%d.csv" % year))
        h.clear_year(l, year)
        with l.part(str(year)):
            for r in csv.DictReader(open(f, encoding="utf-8")) if f else ():
                sid, src, to = sectors.get(r["SERVICE"]), place(r["REF_AREA"]), place(r["COUNTERPART_AREA"])
                v = float(r["OBS_VALUE"] or 0) * 10 ** int(r["UNIT_MULT"] or 0)
                if sid and src and to and v > 0:
                    l.flow(m, year, src, to, sid, v)
        (d / ("%d.csv" % year)).unlink(missing_ok=True)
    print("non-country places used:", sorted(unmatched))
    l.finish()
    kg.cleanup("services_trade")


if __name__ == "__main__":
    main()
