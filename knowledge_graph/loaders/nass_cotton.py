"""USDA NASS Quick Stats bulk files: state and national crop and livestock statistics, latest 10 years, by commodity (includes cotton).

Annual totals only: calendar year or marketing year (where crop values are published), plus first of January inventories."""
import csv
import datetime
import gzip
import io
import re
import urllib.request

import kg
from loaders._sector_helpers import num

PAGE = "https://www.nass.usda.gov/datasets/"
FILES = ("qs.crops_", "qs.animals_products_")
FIRST_YEAR = datetime.date.today().year - 10
ALL = ("ALL PRODUCTION PRACTICES", "ALL UTILIZATION PRACTICES")


def links():
    html = urllib.request.urlopen(urllib.request.Request(PAGE, headers={"User-Agent": kg.UA}), timeout=60).read().decode()
    return {p: re.search(r'href="(/datasets/%s\d+\.txt\.gz)"' % re.escape(p), html).group(1) for p in FILES}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower().replace("$", "usd")).strip("_")


def read(path):
    """State and national rows as dicts, annual totals only. First of January inventory counts too."""
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if (r["AGG_LEVEL_DESC"] in ("STATE", "NATIONAL") and r["YEAR"].isdigit() and int(r["YEAR"]) >= FIRST_YEAR
                    and r["DOMAIN_DESC"] == "TOTAL" and (r["PRODN_PRACTICE_DESC"], r["UTIL_PRACTICE_DESC"]) == ALL
                    and ((r["FREQ_DESC"] == "ANNUAL" and r["REFERENCE_PERIOD_DESC"] in ("YEAR", "MARKETING YEAR"))
                         or (r["STATISTICCAT_DESC"] == "INVENTORY" and r["REFERENCE_PERIOD_DESC"] == "FIRST OF JAN"))):
                yield r


def main():
    l = kg.Loader("nass_cotton", name="USDA NASS Quick Stats: crops and livestock by state",
                  publisher="USDA National Agricultural Statistics Service", url=PAGE, data_url=PAGE, kinds=["stats"],
                  about="Production, area, yield, inventory, sales and value by commodity for each state and the US, annual totals, survey preferred over census",
                  coverage="50 states and US, last 10 years", access="open", license="public domain", found_by="survey")
    d = kg.workdir("nass_cotton")
    for prefix, href in links().items():
        if l.done(prefix):
            continue
        path = kg.download("https://www.nass.usda.gov" + href, d / (prefix + "txt.gz"))
        best = {}  # (state, year, measure, sector) -> ((census?, marketing year?), value); survey beats census, calendar year beats marketing year
        meta = {}
        for r in read(path):
            v = num(r["VALUE"])
            if v is None:
                continue
            place = "USA" if r["AGG_LEVEL_DESC"] == "NATIONAL" else "US." + r["STATE_ALPHA"]
            m = "nass_%s_%s" % (slug(r["STATISTICCAT_DESC"]), slug(r["UNIT_DESC"]))
            meta[m] = (r["STATISTICCAT_DESC"].title(), r["UNIT_DESC"])
            s = (r["SECTOR_DESC"], r["GROUP_DESC"], r["COMMODITY_DESC"], r["CLASS_DESC"])
            k = (place, int(r["YEAR"]), m, s)
            flag = (r["SOURCE_DESC"] != "SURVEY", r["REFERENCE_PERIOD_DESC"] != "YEAR")
            if k not in best or flag < best[k][0]:
                best[k] = (flag, v)
        path.unlink()
        with l.part(prefix):
            for (place, y, m, s), (_, v) in best.items():
                pid = l.place(place)
                if not pid:
                    continue
                parent = None
                for i in range(3 if s[3] == "ALL CLASSES" else 4):
                    code = s[0] if i == 0 else ": ".join(s[1:i + 1])  # commodity and group names repeat across groups
                    parent = l.sector("nass", code, s[i], parent)
                l.stat(l.measure(m, "%s (%s)" % meta[m], meta[m][1], "production",
                                 "As published in Quick Stats, annual totals for all practices and utilization"), y, pid, parent, v)
    l.finish()
    kg.cleanup("nass_cotton")


if __name__ == "__main__":
    main()
