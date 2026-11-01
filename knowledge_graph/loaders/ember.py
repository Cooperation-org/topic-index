"""Ember yearly electricity data: generation, capacity and demand by country, by fuel."""
import csv
import collections

import kg
from loaders._sector_helpers import num, energy_sector, Unmatched, iso3_place

PAGE = "https://ember-energy.org/data/yearly-electricity-data/"
DATA = "https://files.ember-energy.org/public-downloads/yearly_full_release_long_format.csv"
FUEL = {"Bioenergy": "bioenergy", "Coal": "coal", "Gas": "gas", "Hydro": "hydro", "Nuclear": "nuclear",
        "Other Fossil": "other-fossil", "Other Renewables": "other-renewables", "Solar": "solar", "Wind": "wind"}


def main():
    l = kg.Loader("ember", name="Ember yearly electricity data",
                  publisher="Ember", url=PAGE, data_url=DATA, kinds=["stats"],
                  about="Electricity generation and installed capacity by fuel, and demand, by country and year",
                  coverage="~210 countries and economies, 2000 onward", access="open", license="CC BY 4.0", found_by="survey")
    d = kg.workdir("ember")
    gen = l.measure("generation_gwh", "Electricity generation", "GWh", "energy", "Gross electricity generation")
    cap = l.measure("capacity_mw", "Installed capacity", "MW", "energy", "Year-end installed capacity")
    dem = l.measure("electricity_demand_gwh", "Electricity demand", "GWh", "energy", "Generation plus net imports")
    by = collections.defaultdict(list)
    for r in csv.DictReader(open(kg.download(DATA, d / "ember.csv"), encoding="utf-8-sig")):
        if r["Area type"] == "Country or economy" and r["ISO 3 code"]:
            by[r["ISO 3 code"]].append(r)
    bad = Unmatched()
    for iso3, rows in sorted(by.items()):
        place = iso3_place(l, iso3)
        if not place:
            bad.add("%s %s" % (iso3, rows[0]["Area"]))
            continue
        if l.done(iso3):
            continue
        with l.part(iso3):
            for r in rows:
                v = num(r["Value"])
                if v is None:
                    continue
                y, cat, sub, var, unit = int(r["Year"]), r["Category"], r["Subcategory"], r["Variable"], r["Unit"]
                if cat == "Electricity generation" and unit == "TWh":
                    if sub == "Total":
                        l.stat(gen, y, place, energy_sector(l, "total"), v * 1000)
                    elif sub == "Fuel":
                        l.stat(gen, y, place, energy_sector(l, FUEL[var]), v * 1000)
                elif cat == "Capacity" and sub == "Fuel":
                    l.stat(cap, y, place, energy_sector(l, FUEL[var]), v * 1000)
                elif cat == "Electricity demand" and sub == "Demand":
                    l.stat(dem, y, place, energy_sector(l, "total"), v * 1000)
    bad.report("ember")
    l.finish()
    kg.cleanup("ember")


if __name__ == "__main__":
    main()
