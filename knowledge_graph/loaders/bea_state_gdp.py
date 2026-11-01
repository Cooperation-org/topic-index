"""BEA GDP by state and industry, current dollars, 1997 onward (value added by NAICS industry)."""
import csv
import io
import re
import zipfile

import kg
from loaders._sector_helpers import num

PAGE = "https://www.bea.gov/data/gdp/gdp-state"
DATA = "https://apps.bea.gov/regional/zip/SAGDP.zip"
MEMBER = "SAGDP2__ALL_AREAS_1997_2025.csv"
STATES = "https://www2.census.gov/geo/docs/reference/state.txt"
LAST_LINE = 86  # lines after this are alternative groupings of the same industries


def main():
    l = kg.Loader("bea_state_gdp", name="BEA GDP by state and industry",
                  publisher="U.S. Bureau of Economic Analysis", url=PAGE, data_url=DATA, kinds=["stats"],
                  about="GDP by NAICS industry (value added, current dollars) for each state, DC and the United States",
                  coverage="50 states, DC and US total, 1997 to 2025", access="open", license="public domain", found_by="survey")
    d = kg.workdir("bea_state_gdp")
    va = l.measure("value_added_usd", "Value added", "USD", "output",
                   "Gross value added at current prices by industry, converted to US dollars at market exchange rates")
    postal = {}
    for line in open(kg.download(STATES, d / "state.txt")).read().splitlines()[1:]:
        fips, usps = line.split("|")[:2]
        postal[fips] = usps
    with zipfile.ZipFile(kg.download(DATA, d / "sagdp.zip")) as z, z.open(MEMBER) as f:
        rows = [r for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline="")) if r["LineCode"]]
    years = [c for c in rows[0] if c.isdigit()]
    sectors, stack = {}, []
    for r in sorted((r for r in rows if r["GeoFIPS"].strip(' "') == "00000"), key=lambda r: int(r["LineCode"])):
        n = int(r["LineCode"])
        if n > LAST_LINE:
            continue
        name = re.sub(r"\s*\d/$", "", r["Description"].strip())
        indent = len(r["Description"]) - len(r["Description"].lstrip())
        code = r["IndustryClassification"].strip() if r["IndustryClassification"].strip() != "..." else name.lower().replace(" ", "-")
        del stack[indent:]
        sectors[n] = l.sector("bea_industry", "TOTAL" if n == 1 else code, name, stack[-1] if stack else None)
        stack.append(sectors[n])
    l.conn.commit()
    by = {}
    for r in rows:
        by.setdefault(r["GeoFIPS"].strip(' "'), []).append(r)
    for fips, grp in sorted(by.items()):
        place = l.place("USA") if fips == "00000" else l.place("US." + postal[fips[:2]]) if fips.endswith("000") and fips[:2] in postal else None
        if not place or l.done(fips):
            continue
        with l.part(fips):
            for r in grp:
                if int(r["LineCode"]) <= LAST_LINE:
                    for y in years:
                        v = num(r[y])
                        if v is not None:
                            l.stat(va, int(y), place, sectors[int(r["LineCode"])], v * 1e6)
    l.finish()
    kg.cleanup("bea_state_gdp")


if __name__ == "__main__":
    main()
