"""ILOSTAT: employment by sex and economic activity, annual, 2011 onward. All sexes, ISIC Rev.4 and Rev.3.1, plus broad sectors."""
import csv
import collections

import kg
from loaders._sector_helpers import num, Unmatched, iso3_place

PAGE = "https://ilostat.ilo.org/data/"
API = "https://rplumber.ilo.org/data/indicator/?id=EMP_TEMP_SEX_ECO_NB_A&type=code&format=.csv&lang=en"
DIC = "https://rplumber.ilo.org/metadata/dic/?var=classif1&lang=en&format=.csv"
FIRST_YEAR = 2011
SCHEMES = {"ECO_ISIC4_": "isic", "ECO_ISIC3_": "isic3", "ECO_SECTOR_": "ilo_broad"}
SKIP = {"ECO_SECTOR_NAG", "ECO_SECTOR_X", "ECO_ISIC4_X", "ECO_ISIC3_X"}  # not-elsewhere-classified and the complement of agriculture


def main():
    l = kg.Loader("ilostat_sector", name="ILOSTAT employment by economic activity",
                  publisher="International Labour Organization", url=PAGE, data_url=API, kinds=["stats"],
                  about="Employed people by ISIC Rev.4 section (Rev.3.1 and broad agriculture/industry/services where that is all a country reports), all sexes",
                  coverage="~190 countries, 2011 to latest; one source per country and year", access="open",
                  license="CC BY 4.0", found_by="survey")
    d = kg.workdir("ilostat_sector")
    emp = l.measure("employment_people", "Employed people", "people", "employment",
                    "Employment by economic activity, all sexes. Where a country has several surveys for a year the one with most sectors is kept")
    labels = {r["classif1"]: r["classif1.label"].split(": ", 1)[-1] for r in
              csv.DictReader(open(kg.download(DIC, d / "dic.csv"), encoding="utf-8-sig"))}
    rows = collections.defaultdict(lambda: collections.defaultdict(dict))  # country -> (year, source) -> code -> value
    for r in csv.DictReader(open(kg.download(API, d / "emp.csv"), encoding="utf-8-sig")):
        c = r["classif1"]
        if r["sex"] != "SEX_T" or c in SKIP or not r["time"].isdigit() or int(r["time"]) < FIRST_YEAR:
            continue
        pre = next((p for p in SCHEMES if c.startswith(p)), None)
        v = num(r["obs_value"])
        if pre and v is not None:
            rows[r["ref_area"]][(int(r["time"]), r["source"])][c] = v * 1000
    bad = Unmatched()
    for iso3, by in sorted(rows.items()):
        place = iso3_place(l, iso3)
        if not place:
            bad.add(iso3)
            continue
        if l.done(iso3):
            continue
        best = {}
        for (y, src), vals in by.items():
            groups = {}
            for c, v in vals.items():
                groups.setdefault(next(p for p in SCHEMES if c.startswith(p)), {})[c] = v
            # one source per country, year and scheme: the one reporting most sectors
            for pre, g in groups.items():
                if (y, pre) not in best or (len(g), src) > (len(best[(y, pre)][1]), best[(y, pre)][0]):
                    best[(y, pre)] = (src, g)
        with l.part(iso3):
            for (y, pre), (src, g) in best.items():
                for c, v in g.items():
                    code = c[len(pre):]
                    sid = l.sector(SCHEMES[pre], code, labels.get(c, code).replace("%s. " % code, "", 1),
                                   None if code == "TOTAL" else l.sector(SCHEMES[pre], "TOTAL", "Total"))
                    l.stat(emp, y, place, sid, v)
    bad.report("ilostat_sector")
    l.finish()
    kg.cleanup("ilostat_sector")


if __name__ == "__main__":
    main()
