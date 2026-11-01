"""BTS/FHWA Freight Analysis Framework 5.7.1, state to state, 42 SCTG commodities, value in 2017 dollars, 2018-2024."""
import csv
import io
import zipfile

import openpyxl

import kg
from loaders import _trade_helpers as h

URL = "https://faf.ornl.gov/faf5/Data/Download_Files/FAF5.7.1_State_2018-2024.zip"
STATES = "https://www2.census.gov/geo/docs/reference/state.txt"
CSV = "FAF5.7.1_State_2018-2024.csv"
ABOUT = ("Freight value moved from the 'from' state to the 'to' state in the year, million 2017 USD stored as USD, summed over "
         "all modes and over domestic, import and export shipments. For imports 'from' is the US state where the shipment "
         "enters, for exports 'to' is the US state where it leaves. Intrastate flows have from = to.")


def main():
    l = kg.Loader("faf5_state", name="Freight Analysis Framework 5.7.1, state to state by commodity",
                  publisher="US DOT Bureau of Transportation Statistics and FHWA, via Oak Ridge National Laboratory",
                  url="https://www.bts.gov/faf", data_url=URL, kinds=["flows"],
                  about="Value and weight of freight moved between US states by 42 commodity groups, all modes, domestic and foreign trade",
                  coverage="50 states and DC, 2018-2024, SCTG 2-digit", access="open", license="Public domain (US government)", found_by="core")
    d = kg.workdir("faf5_state")
    z = kg.download(URL, d / "faf.zip")
    with zipfile.ZipFile(z) as zf:
        wb = openpyxl.load_workbook(io.BytesIO(zf.read("FAF5_metadata.xlsx")), read_only=True)
        names = {r[0]: r[1] for r in list(wb["Commodity (SCTG2)"].iter_rows(values_only=True))[1:] if r[0]}
    sectors = {c: l.sector("sctg", c, n) for c, n in names.items()}
    postal = {r["STATE"]: r["STUSAB"] for r in csv.DictReader(open(kg.download(STATES, d / "state.txt"), encoding="utf-8"), delimiter="|")}
    m = l.measure("freight_value_usd_2017", "Freight value, state to state, 2017 dollars", "USD_2017", "freight", ABOUT)
    l.conn.commit()
    years = list(range(2018, 2025))
    todo = [y for y in years if not l.done(str(y))]
    if todo:
        total = {}
        with zipfile.ZipFile(z) as zf, zf.open(CSV) as f:
            rd = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            for r in rd:
                key = (r["dms_origst"], r["dms_destst"], r["sctg2"])
                t = total.setdefault(key, dict.fromkeys(todo, 0.0))
                for y in todo:
                    t[y] += float(r["value_%d" % y] or 0)
        for y in todo:
            h.clear_year(l, y)
            with l.part(str(y)):
                for (o, dst, s), t in total.items():
                    if t[y]:
                        l.flow(m, y, l.place("US." + postal[o]), l.place("US." + postal[dst]), sectors[s], t[y] * 1e6)
    l.finish()
    kg.cleanup("faf5_state")



if __name__ == "__main__":
    main()
