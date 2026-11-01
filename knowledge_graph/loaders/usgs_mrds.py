"""USGS Mineral Resources Data System: mines, prospects and deposits worldwide."""
import csv
import io
import zipfile

import kg
from loaders._entity_helpers import Names, bulk_entities, geo_ok

URL = "https://mrdata.usgs.gov/mrds/mrds-csv.zip"
BATCH = 50_000


def main():
    l = kg.Loader("usgs_mrds", name="Mineral Resources Data System", publisher="US Geological Survey",
                  url="https://mrdata.usgs.gov/mrds/", data_url=URL, kinds=["entities"],
                  about="Mines, prospects and deposits with commodities, development status, operation and deposit type, coordinates; the file has no operator names",
                  coverage="World, most complete for the US; records through 2016", access="open",
                  license="US government work, public domain", found_by="core")
    names = Names(l)
    path = kg.download(URL, kg.workdir("usgs_mrds") / "mrds.zip")
    batch, n = [], 0

    def flush():
        nonlocal batch, n
        part = "mrds-%04d" % n
        if not l.done(part):
            with l.part(part):
                bulk_entities(l, batch)
        batch, n = [], n + 1

    with zipfile.ZipFile(path) as z, z.open("mrds.csv") as f:
        for i, r in enumerate(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""))):
            lat, lon = geo_ok(r["latitude"], r["longitude"])
            commod = [r[k] for k in ("commod1", "commod2", "commod3") if r[k]]
            country = names.country(r["country"])
            attrs = {"commodities": commod or None, "status": r["dev_stat"], "operation": r["oper_type"],
                     "deposit_type": r["dep_type"], "size": r["prod_size"], "record_type": r["com_type"],
                     "first_production": r["yr_fst_prd"], "last_production": r["yr_lst_prd"],
                     "state": r["state"], "county": r["county"], "country_name": r["country"]}
            batch.append((r["dep_id"], r["site_name"] or "Unknown", "mine",
                          names.division(country, r["state"]), lat, lon, None, r["url"] or None,
                          {k: v for k, v in attrs.items() if v not in (None, "", "Unknown", "NA")}))
            if len(batch) >= BATCH:
                flush()
    flush()
    names.report()
    l.finish()
    kg.cleanup("usgs_mrds")


if __name__ == "__main__":
    main()
