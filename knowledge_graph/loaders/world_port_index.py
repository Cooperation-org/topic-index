"""NGA World Port Index (Pub 150): ports with coordinates, size, type and facilities."""
import csv

import kg
from loaders._entity_helpers import Names, bulk_entities, geo_ok

URL = "https://msi.nga.mil/api/publications/download?type=view&key=16920959/SFH00000/UpdatedPub150.csv"
FACILITIES = ("Wharves", "Anchorage", "Dangerous Cargo Anchorage", "Ro-Ro", "Solid Bulk", "Liquid Bulk", "Container",
              "Breakbulk", "Oil Terminal", "LNG Terminal")


def main():
    l = kg.Loader("world_port_index", name="World Port Index", publisher="US National Geospatial-Intelligence Agency",
                  url="https://msi.nga.mil/Publications/WPI", data_url=URL, kinds=["entities"],
                  about="Ports and terminals worldwide with coordinates, harbor size and type, cargo facilities, UN/LOCODE",
                  coverage="World, about 3,800 ports", access="open", license="US government work, public domain",
                  found_by="core")
    if l.done("ports"):
        return l.finish()
    names = Names(l)
    path = kg.download(URL, kg.workdir("world_port_index") / "wpi.csv")
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            lat, lon = geo_ok(r["Latitude"], r["Longitude"])
            fac = [x for x in FACILITIES if r.get("Facilities - " + x) == "Yes"]
            locode = r["UN/LOCODE"].strip()
            attrs = {"harbor_size": r["Harbor Size"], "harbor_type": r["Harbor Type"], "harbor_use": r["Harbor Use"],
                     "water_body": r["World Water Body"], "unlocode": locode, "alt_name": r["Alternate Port Name"].strip(),
                     "facilities": fac or None, "country_name": r["Country Code"]}
            rows.append(("%d" % float(r["World Port Index Number"]), r["Main Port Name"], "port",
                         names.country(r["Country Code"]), lat, lon, None, None,
                         {k: v for k, v in attrs.items() if v}))
    names.report()
    with l.part("ports"):
        bulk_entities(l, rows)
    l.finish()
    kg.cleanup("world_port_index")


if __name__ == "__main__":
    main()
