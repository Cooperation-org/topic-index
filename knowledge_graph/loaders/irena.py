"""IRENA electricity statistics: installed capacity and generation by country and technology, 2000 onward."""
import csv
import io
import json
import urllib.request

import kg
from loaders._sector_helpers import num, post_json, energy_sector, Unmatched, iso3_place

PAGE = "https://pxweb.irena.org/pxweb/en/IRENASTAT/IRENASTAT__Power%20Capacity%20and%20Generation/"
API = "https://pxweb.irena.org/api/v1/en/IRENASTAT/Power%20Capacity%20and%20Generation/Country_ELECSTAT_2026_H2_PX.px"
TECH = {
    "Total Renewable": "renewable", "Total Non-Renewable": "non-renewable",
    "Renewable hydropower": "hydro", "Pure hydropower": "hydro-pure", "Mixed hydropower": "hydro-mixed",
    "Solar photovoltaic": "solar-pv", "Solar thermal energy": "solar-thermal",
    "Onshore wind energy": "wind-onshore", "Offshore wind energy": "wind-offshore",
    "Solid biofuels": "solid-biofuels", "Gas biofuels": "gas-biofuels", "Liquid biofuels": "liquid-biofuels",
    "Renewable waste": "renewable-waste", "Geothermal energy": "geothermal", "Marine energy": "marine",
    "Coal": "coal", "Natural gas": "gas", "Oil": "oil", "Other fossil fuels": "other-fossil",
    "Oil shale-sands": "oil-shale", "Peat and peat products": "peat", "Nuclear energy": "nuclear",
    "Mechanical storage (Pumped hydro)": "pumped-storage", "Non-renewable waste": "non-renewable-waste",
    "Other non-renewable energy": "other-non-renewable",
}
MEASURE = {"Electricity Generation (GWh)": "generation_gwh", "Electrical Installed Capacity (MW)": "capacity_mw"}


def main():
    l = kg.Loader("irena", name="IRENA electricity capacity and generation",
                  publisher="International Renewable Energy Agency", url=PAGE, data_url=API, kinds=["stats"],
                  about="Installed capacity (MW) and generation (GWh) by country and technology, on-grid and off-grid together",
                  coverage="~220 countries and areas, 2000 to 2025", access="open", license="CC BY 4.0", found_by="survey")
    req = urllib.request.Request(API, headers={"User-Agent": kg.UA})
    meta = json.load(urllib.request.urlopen(req, timeout=60))
    countries = next(v for v in meta["variables"] if v["code"] == "Country/area")
    meas = {k: l.measure(v, "Installed capacity" if v == "capacity_mw" else "Electricity generation",
                         "MW" if v == "capacity_mw" else "GWh", "energy",
                         "Year-end installed capacity" if v == "capacity_mw" else "Gross electricity generation")
            for k, v in MEASURE.items()}
    bad = Unmatched()
    for code, name in zip(countries["values"], countries["valueTexts"]):
        place = iso3_place(l, code)
        if not place:
            bad.add("%s %s" % (code, name))
            continue
        if l.done(code):
            continue
        body = {"query": [{"code": "Country/area", "selection": {"filter": "item", "values": [code]}},
                          {"code": "Grid connection", "selection": {"filter": "item", "values": ["0"]}}],
                "response": {"format": "csv"}}
        with l.part(code):
            for r in csv.DictReader(io.StringIO(post_json(API, body))):
                v = num(r["Electricity statistics"])
                if v is not None and r["Technology"] in TECH:
                    l.stat(meas[r["Data Type"]], int(r["Year"]), place, energy_sector(l, TECH[r["Technology"]]), v)
    bad.report("irena")
    l.finish()


if __name__ == "__main__":
    main()
