"""USGS Mineral Commodity Summaries data release: world mine production, reserves and capacity by country and mineral."""
import csv
import json
import urllib.request

import kg
from loaders._sector_helpers import num, Unmatched

PAGE = "https://www.usgs.gov/data/mineral-commodity-summaries-2026-data-release"
PARENT = "696a75d5d4be0228872d3bf8"  # ScienceBase item holding the release; the world statistics file sits in its second child
LIST = "https://www.sciencebase.gov/catalog/items?parentId=%s&format=json&max=50&fields=title,files" % PARENT
FILE = "MCS2026_Commodities_Data.csv"
ISO3 = {"United States": "USA", "Russia": "RUS", "Turkey": "TUR", "Iran": "IRN", "Vietnam": "VNM", "Bolivia": "BOL",
        "Congo (Kinshasa)": "COD", "Laos": "LAO", "Tanzania": "TZA", "United Kingdom": "GBR", "Burma": "MMR",
        "Korea, North": "PRK", "Korea, Republic of": "KOR", "Netherlands": "NLD", "Venezuela": "VEN",
        "Côte d’Ivoire": "CIV", "Syria": "SYR", "Brunei": "BRN", "Moldova": "MDA", "Czechia": "CZE",
        "Macedonia, North": "MKD", "North Macedonia": "MKD", "Congo (Brazzaville)": "COG", "Taiwan": "TWN"}
# (statistic, unit) -> (measure slug, unit label, factor)
UNITS = {"metric tons": ("tonnes", 1), "tons": ("tonnes", 1), "thousand metric tons": ("tonnes", 1e3),
         "million metric tons": ("tonnes", 1e6), "thousand metric dry tons": ("tonnes", 1e3),
         "kilograms": ("tonnes", 1e-3), "thousands of carats": ("carats", 1e3), "million carats": ("carats", 1e6),
         "million cubic meters": ("m3", 1e6), "million liters": ("liters", 1e6)}
STAT = {"Production": "production", "Reserves": "reserves", "Capacity": "capacity"}


def main():
    l = kg.Loader("usgs_minerals", name="USGS Mineral Commodity Summaries: world production, reserves and capacity",
                  publisher="U.S. Geological Survey", url=PAGE, data_url=LIST, kinds=["stats"],
                  about="Mine production, reserves and capacity by country for about 90 mineral commodities, latest two years",
                  coverage="Producing countries per commodity, 2024 and 2025 estimate", access="open", license="public domain",
                  found_by="survey")
    d = kg.workdir("usgs_minerals")
    req = urllib.request.Request(LIST, headers={"User-Agent": kg.UA})
    url = next(f["url"] for i in json.load(urllib.request.urlopen(req, timeout=60))["items"]
               for f in i.get("files", []) if f["name"] == FILE)
    path = kg.download(url, d / FILE)
    if l.done("all"):
        l.finish()
        return
    measures, seen, bad = {}, set(), Unmatched()
    other = l.other_place("usgs:other", "Other countries (USGS)")
    with l.part("all"):
        for r in csv.DictReader(open(path, encoding="cp1252")):
            if not r["Section"].startswith("World") or r["Statistics"] not in STAT:
                continue
            unit = UNITS.get(r["Unit"].strip())
            v, year = num(r["Value"]), r["Year"]
            if not unit or v is None or not year.isdigit():
                continue
            c = r["Country"]
            place = (l.place("world") if c == "World total" else other if c == "Other countries" else
                     l.country(iso3=ISO3[c]) if c in ISO3 else l.country(name=c))
            if not place:
                bad.add(c)
                continue
            slug = "mineral_%s_%s" % (STAT[r["Statistics"]], unit[0])
            if slug not in measures:
                measures[slug] = l.measure(slug, "Mineral %s" % STAT[r["Statistics"]], unit[0], "production",
                                           "Content as USGS reports it for each commodity, as given in the detail column")
            com = r["Commodity"].strip()
            det = r["Statistics_detail"].strip() or STAT[r["Statistics"]]
            key = (slug, com, det, c, year)
            if key in seen:
                continue
            seen.add(key)
            parent = l.sector("usgs_mineral", com, com)
            sid = l.sector("usgs_mineral", "%s: %s" % (com, det), "%s, %s" % (com, det.lower()), parent)
            l.stat(measures[slug], int(year), place, sid, v * unit[1])
    bad.report("usgs_minerals")
    l.finish()
    kg.cleanup("usgs_minerals")


if __name__ == "__main__":
    main()
