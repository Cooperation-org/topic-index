"""WRI Global Power Plant Database v1.3.0: about 35,000 power plants with fuel, capacity, owner, coordinates."""
import csv
import io
import zipfile

import kg
from loaders._entity_helpers import bulk_entities, geo_ok

URL = ("https://datasets.wri.org/private-admin/dataset/53623dfd-3df6-4f15-a091-67457cdb571f/resource/"
       "66bcdacc-3d0e-46ad-9271-a5a76b1853d2/download/globalpowerplantdatabasev130.zip")


def main():
    l = kg.Loader("wri_power_plants", name="Global Power Plant Database",
                  publisher="World Resources Institute", url="https://datasets.wri.org/datasets/global-power-plant-database",
                  data_url=URL, kinds=["entities"],
                  about="Power plants with primary fuel, capacity in MW, owner, commissioning year and coordinates (version 1.3.0, 2021)",
                  coverage="World, 167 countries", access="open", license="CC BY 4.0", found_by="core")
    if l.done("plants"):
        return l.finish()
    z = kg.download(URL, kg.workdir("wri_power_plants") / "gppd.zip")
    rows = []
    with zipfile.ZipFile(z) as zf, zf.open("global_power_plant_database.csv") as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline="")):
            lat, lon = geo_ok(r["latitude"], r["longitude"])
            fuels = [r[k] for k in ("other_fuel1", "other_fuel2", "other_fuel3") if r[k]]
            attrs = {"fuel": r["primary_fuel"], "other_fuels": fuels or None,
                     "capacity_mw": float(r["capacity_mw"]) if r["capacity_mw"] else None,
                     "commissioned": int(float(r["commissioning_year"])) if r["commissioning_year"] else None,
                     "owner": r["owner"], "data_source": r["source"], "country_name": r["country_long"]}
            rows.append((r["gppd_idnr"], r["name"], "power_plant", l.country(iso3=r["country"]), lat, lon, None,
                         r["url"] or None, {k: v for k, v in attrs.items() if v not in (None, "")}))
    with l.part("plants"):
        bulk_entities(l, rows)
    l.finish()
    kg.cleanup("wri_power_plants")


if __name__ == "__main__":
    main()
