"""Our World in Data energy dataset: primary energy consumption by source and fossil fuel production. Electricity columns are Ember's and skipped."""
import csv
import collections

import kg
from loaders._sector_helpers import num, energy_sector, Unmatched, iso3_place

PAGE = "https://github.com/owid/energy-data"
DATA = "https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv"
CONSUMPTION = {"primary_energy_consumption": "total", "coal_consumption": "coal", "oil_consumption": "oil",
               "gas_consumption": "gas", "nuclear_consumption": "nuclear", "hydro_consumption": "hydro",
               "solar_consumption": "solar", "wind_consumption": "wind", "biofuel_consumption": "bioenergy",
               "other_renewable_consumption": "other-renewables", "renewables_consumption": "renewable"}
PRODUCTION = {"coal_production": "coal", "oil_production": "oil", "gas_production": "gas"}


def main():
    l = kg.Loader("owid_energy", name="Our World in Data energy dataset",
                  publisher="Our World in Data, from the Energy Institute and others", url=PAGE, data_url=DATA,
                  kinds=["stats"],
                  about="Primary energy consumption by source and coal, oil and gas production, by country and year; electricity columns left to Ember",
                  coverage="~220 countries, 1900 onward", access="open", license="CC BY 4.0", found_by="survey")
    d = kg.workdir("owid_energy")
    cons = l.measure("primary_energy_twh", "Primary energy consumption", "TWh", "energy",
                     "Primary energy, substitution method")
    prod = l.measure("energy_production_twh", "Fossil fuel production", "TWh", "energy", "Production of coal, oil and gas in energy terms")
    by = collections.defaultdict(list)
    for r in csv.DictReader(open(kg.download(DATA, d / "owid.csv"), encoding="utf-8")):
        if r["iso_code"] and not r["iso_code"].startswith("OWID"):
            by[r["iso_code"]].append(r)
    bad = Unmatched()
    for iso3, rows in sorted(by.items()):
        place = iso3_place(l, iso3)
        if not place:
            bad.add("%s %s" % (iso3, rows[0]["country"]))
            continue
        if l.done(iso3):
            continue
        with l.part(iso3):
            for r in rows:
                for cols, m in ((CONSUMPTION, cons), (PRODUCTION, prod)):
                    for col, code in cols.items():
                        v = num(r[col])
                        if v is not None:
                            l.stat(m, int(r["year"]), place, energy_sector(l, code), v)
    bad.report("owid_energy")
    l.finish()
    kg.cleanup("owid_energy")


if __name__ == "__main__":
    main()
