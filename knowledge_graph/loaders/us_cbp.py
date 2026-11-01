"""Census County Business Patterns: employment, establishments and payroll by 2 and 3 digit NAICS, every state and every Arizona county."""
import csv
import io
import zipfile

import kg
from loaders._sector_helpers import num

YEAR = 2023
PAGE = "https://www.census.gov/programs-surveys/cbp.html"
BASE = "https://www2.census.gov/programs-surveys/cbp/datasets/%d/" % YEAR
NAICS = "https://www2.census.gov/programs-surveys/cbp/technical-documentation/reference/naics-descriptions/naics.txt"
STATES = "https://www2.census.gov/geo/docs/reference/state.txt"
COUNTY_STATE = "04"  # Arizona


def naics_code(raw):
    """2-digit '11----', 3-digit '111---' (the file pads with - and /); None for other depths. Total is '------'."""
    if raw == "------":
        return "TOTAL", None
    s = raw.rstrip("-/")
    if len(s) == 2:
        return s, "TOTAL"
    return (s, s[:2]) if len(s) == 3 else (None, None)


def rows(zpath):
    with zipfile.ZipFile(zpath) as z:
        name = next(n for n in z.namelist() if n.endswith(".txt"))
        with z.open(name) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", newline=""))


def store(l, it, place_of, measures, sector_of):
    for r in it:
        if r.get("lfo", "-") != "-":
            continue
        code, _ = naics_code(r["naics"])
        place = place_of(r)
        if code is None or place is None:
            continue
        sid = sector_of(r["naics"])
        for col, flag, m, scale in (("emp", "emp_nf", "emp", 1), ("est", None, "est", 1), ("ap", "ap_nf", "ap", 1000)):
            v = num(r[col])
            if v is not None and (flag is None or r[flag] not in ("D", "S")):
                l.stat(measures[m], YEAR, place, sid, v * scale)


def main():
    l = kg.Loader("us_cbp", name="Census County Business Patterns %d" % YEAR,
                  publisher="U.S. Census Bureau", url=PAGE, data_url=BASE, kinds=["stats"],
                  about="Employees, establishments and annual payroll by 2 and 3 digit NAICS for every state and every Arizona county; the API wants a key, these are the bulk files",
                  coverage="50 states and DC, Arizona counties, %d" % YEAR, access="open", license="public domain", found_by="survey")
    d = kg.workdir("us_cbp")
    measures = {
        "emp": l.measure("employment_people", "Employed people", "people", "employment", "Employees in the pay period including March 12"),
        "est": l.measure("establishments_count", "Establishments", "establishments", "employment", "Business locations with paid employees"),
        "ap": l.measure("annual_payroll_usd", "Annual payroll", "USD", "output", "Annual payroll of employees, current dollars"),
    }
    titles = {}
    for line in open(kg.download(NAICS, d / "naics.txt"), encoding="latin-1").read().splitlines()[1:]:
        if line.strip():
            c, t = line[:6], line[6:].strip()
            titles[c] = t
    sectors = {}

    def sector_of(raw):
        if raw not in sectors:
            code, parent = naics_code(raw)
            sectors[raw] = l.sector("naics", code, "Total, all sectors" if code == "TOTAL" else titles.get(raw, code),
                                    l.sector("naics", parent, "Total, all sectors" if parent == "TOTAL" else titles.get(parent + "----", parent)) if parent else None)
        return sectors[raw]

    postal = {}
    for line in open(kg.download(STATES, d / "state.txt")).read().splitlines()[1:]:
        fips, usps = line.split("|")[:2]
        postal[fips] = usps
    if not l.done("states"):
        with l.part("states"):
            store(l, rows(kg.download(BASE + "cbp%dst.zip" % (YEAR % 100), d / "st.zip")),
                  lambda r: l.place("US." + postal[r["fipstate"]]) if r["fipstate"] in postal and l.place("US." + postal[r["fipstate"]]) else None,
                  measures, sector_of)
    if not l.done("az-counties"):
        with l.part("az-counties"):
            store(l, (r for r in rows(kg.download(BASE + "cbp%dco.zip" % (YEAR % 100), d / "co.zip")) if r["fipstate"] == COUNTY_STATE),
                  lambda r: l.place("US.%s.%s" % (postal[COUNTY_STATE], r["fipscty"])), measures, sector_of)
    l.finish()
    kg.cleanup("us_cbp")


if __name__ == "__main__":
    main()
