"""Global Energy Monitor trackers. The gem.wiki download sits behind an email form, so those trackers are listed, not
loaded. Two trackers are published openly on Zenodo under CC BY 4.0 and are loaded: Global Steel Plant Tracker (April 2024,
factory) and Global Nuclear Power Tracker (July 2024, power_plant)."""
import csv

import openpyxl

import kg
from loaders._entity_helpers import Names, bulk_entities, geo_ok, list_only

STEEL = "https://zenodo.org/api/records/16893375/files/Global-Steel-Plant-Tracker-April-2024-Standard-Copy-V1.xlsx/content"
NUCLEAR = "https://zenodo.org/api/records/17109112/files/gem_nuclearpower_2024-07.tsv/content"
EMPTY = (None, "", "N/A", "unknown", "not found", "n/a")

PAGE = "https://globalenergymonitor.org/projects/"
NOTE = "download needs an email form (api.globalenergymonitor.org gem-download-form); not loaded"
TRACKERS = {
    "gem_solar": ("Global Solar Power Tracker", "global-solar-power-tracker", "power_plant", "Utility-scale solar farm phases"),
    "gem_wind": ("Global Wind Power Tracker", "global-wind-power-tracker", "power_plant", "Wind farm phases"),
    "gem_coal_plants": ("Global Coal Plant Tracker", "global-coal-plant-tracker", "power_plant", "Coal power units"),
    "gem_oil_gas_plants": ("Global Oil and Gas Plant Tracker", "global-oil-gas-plant-tracker", "power_plant", "Oil and gas power units"),
    "gem_oil_gas_extraction": ("Global Oil and Gas Extraction Tracker", "global-oil-gas-extraction-tracker", "mine", "Oil and gas fields"),
    "gem_iron_steel": ("Global Iron and Steel Tracker", "global-iron-steel-tracker", "factory", "Steel plants"),
    "gem_cement": ("Global Cement and Concrete Tracker", "global-cement-concrete-tracker", "factory", "Cement and concrete plants"),
}


def clean(d):
    return {k: v for k, v in d.items() if v not in EMPTY and v != []}


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def load(l):
    names = Names(l)
    d = kg.workdir("gem_trackers")
    if not l.done("steel"):
        wb = openpyxl.load_workbook(kg.download(STEEL, d / "steel.xlsx"), read_only=True)
        rows = wb["Steel Plants"].iter_rows(values_only=True)
        head = next(rows)
        out = []
        for r in map(lambda r: dict(zip(head, r)), rows):
            if not r["Plant ID"]:
                continue
            lat = lon = None
            if r["Coordinates"] and "," in str(r["Coordinates"]):
                lat, lon = geo_ok(*str(r["Coordinates"]).split(",", 1))
            attrs = clean({"owner": r["Owner"], "parent": r["Parent"], "state_owned": r["SOE Status"], "status": r["Capacity operating status"],
                           "crude_steel_ttpa": num(r["Nominal crude steel capacity (ttpa)"]), "iron_ttpa": num(r["Nominal iron capacity (ttpa)"]),
                           "process": r["Main production process"], "equipment": r["Main production equipment"],
                           "products": r["Steel products"], "start_year": r["Start date"], "workforce": r["Workforce size"],
                           "city": r["Municipality"], "province": r["Subnational unit (province/state)"], "country_name": r["Country/Area"],
                           "tracker": "steel"})
            out.append(("steel:" + r["Plant ID"], r["Plant name (English)"], "factory", names.division(names.country(r["Country/Area"]), r["Subnational unit (province/state)"]),
                        lat, lon, None, r["GEM wiki page"], attrs))
        with l.part("steel"):
            bulk_entities(l, out)
    if not l.done("nuclear"):
        out = []
        with open(kg.download(NUCLEAR, d / "nuclear.tsv"), encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                lat, lon = geo_ok(r["Latitude"], r["Longitude"])
                attrs = clean({"fuel": "Nuclear", "capacity_mw": num(r[" Capacity (MW) "]), "status": r["Status"], "reactor_type": r["Reactor Type"],
                               "unit": r["Unit Name"], "owner": r["Owner"], "operator": r["Operator"], "start_year": r["Start Year"],
                               "city": r["City"], "province": r["State/Province"], "country_name": r["Country/Area"], "tracker": "nuclear"})
                out.append(("nuclear:" + r["GEM unit ID"], "%s %s" % (r["Project Name"], r["Unit Name"]) if r["Unit Name"] else r["Project Name"],
                            "power_plant", names.division(names.country(r["Country/Area"]), r["State/Province"]), lat, lon, None, r["Wiki URL"] or None, attrs))
        with l.part("nuclear"):
            bulk_entities(l, out)
    names.report()


def main():
    l = kg.Loader("gem_trackers", name="Global Energy Monitor open trackers: steel plants and nuclear power",
                  publisher="Global Energy Monitor", url="https://globalenergymonitor.org/",
                  data_url="https://zenodo.org/search?q=%22Global%20Energy%20Monitor%22", kinds=["entities"],
                  about="Steel plants (April 2024) and nuclear power units (July 2024) with owner, capacity, status and coordinates; the other trackers are listed separately because their download needs an email form",
                  coverage="World", access="open (Zenodo)", license="CC BY 4.0", found_by="core")
    load(l)
    l.finish()
    kg.cleanup("gem_trackers")
    for slug, (name, page, kind, about) in TRACKERS.items():
        list_only(slug, NOTE, name=name, publisher="Global Energy Monitor", url=PAGE + page, kinds=["entities"],
                  about=about + " with owner, capacity, status, coordinates", coverage="World",
                  access="registration", license="CC BY 4.0", found_by="core")


if __name__ == "__main__":
    main()
