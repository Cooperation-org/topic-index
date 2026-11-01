"""UN DESA International Migrant Stock 2024: people living in a country, by country of origin, 1990 to 2024."""
import openpyxl

import kg
from loaders._money_helpers import Countries

BASE = "https://www.un.org/development/desa/pd/sites/www.un.org.development.desa.pd/files/"
FILE = "undesa_pd_2024_ims_stock_by_sex_destination_and_origin.xlsx"


def main():
    l = kg.Loader("un_migrant_stock", name="International Migrant Stock 2024", publisher="UN DESA Population Division",
                  url="https://www.un.org/development/desa/pd/content/international-migrant-stock", data_url=BASE + FILE,
                  kinds=["flows"], about="People living outside their country of birth or citizenship, by destination and origin country",
                  coverage="Destination and origin countries, 1990, 1995, 2000, 2005, 2010, 2015, 2020, 2024", access="open",
                  license="CC BY 3.0 IGO", found_by="survey")
    mid = l.measure("migrants_people", "International migrants, people", "people", "migration",
                    about="from = country of origin (birth or citizenship as the destination reports it), to = destination country, mid-year stock of people living there, both sexes. World, regions and development groups are skipped")
    cs = Countries(l)
    d = kg.workdir("un_migrant_stock")
    wb = openpyxl.load_workbook(kg.download(BASE + FILE, d / FILE), read_only=True)
    rows = wb["Table 1"].iter_rows(values_only=True)
    years = None
    by_dest = {}
    for r in rows:
        if r[0] == "Index":
            years = [int(y) for y in r[7:15]]
            continue
        if years is None or not isinstance(r[0], int):
            continue
        dest, origin = r[4], r[6]
        by_dest.setdefault(dest, []).append((origin, r[5], r[7:15]))
    names = {}
    for dest, rows in sorted(by_dest.items()):
        if l.done(str(dest)):
            continue
        dp = cs.get(m49=dest, key="dest %s" % dest)
        with l.part(str(dest)):
            if not dp:
                continue
            for origin, oname, vals in rows:
                op = cs.get(m49=origin, key="origin %s %s" % (origin, oname)) if origin != dest else None
                if not op:
                    continue
                for y, v in zip(years, vals):
                    if isinstance(v, (int, float)) and v > 0:
                        l.flow(mid, y, op, dp, None, float(v))
    cs.report()
    l.finish()
    kg.cleanup("un_migrant_stock")


if __name__ == "__main__":
    main()
