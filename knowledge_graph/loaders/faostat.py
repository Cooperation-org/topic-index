"""FAOSTAT: crop and livestock production, value of agricultural production, and the detailed trade matrix (from 2010)."""
import csv
import io
import zipfile

import kg
from loaders._sector_helpers import num, fao_place

PAGE = "https://www.fao.org/faostat/en/#data"
BULK = "https://bulks-faostat.fao.org/production/"
PROD = "Production_Crops_Livestock_E_All_Data_(Normalized)"
VALUE = "Value_of_Production_E_All_Data_(Normalized)"
TRADE = "Trade_DetailedTradeMatrix_E_All_Data_(Normalized)"
TRADE_FROM = 2010
# element code -> (measure slug, name, unit, scale to unit)
PROD_EL = {
    "5510": ("production_tonnes", "Production", "tonnes", 1),
    "5513": ("production_thousand_units", "Production, in thousands (eggs, hides and similar)", "thousand units", 1),
    "5312": ("area_harvested_ha", "Area harvested", "ha", 1),
    "5111": ("livestock_stocks_heads", "Livestock stocks", "animals", 1),
    "5112": ("livestock_stocks_heads", "Livestock stocks", "animals", 1000),
}
VALUE_EL = {
    "57": ("production_value_usd", "Gross production value, current US dollars", "USD", 1000),
    "58": ("production_value_usd_2015", "Gross production value, constant 2014-2016 US dollars", "USD_2015", 1000),
}


def rows(path, name):
    with zipfile.ZipFile(path) as z, z.open(name + ".csv") as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""))


def by_area(it, key):
    """Consecutive runs of rows with the same key. A key coming back later means the file is not sorted."""
    seen, cur, buf = set(), None, []
    for r in it:
        k = r[key]
        if k != cur:
            if buf:
                yield cur, buf
            if k in seen:
                raise RuntimeError("file not sorted by %s: %s again" % (key, k))
            seen.add(k)
            cur, buf = k, []
        buf.append(r)
    if buf:
        yield cur, buf


def part_rows(l, label, path, name, elements):
    for code, buf in by_area(rows(path, name), "Area Code"):
        part = "%s:%s" % (label, code)
        if l.done(part):
            continue
        place = fao_place(l, code, buf[0]["Area Code (M49)"], buf[0]["Area"])
        seen = set()  # stocks come in animals and in thousands: first one wins
        with l.part(part):
            if place:
                for r in buf:
                    el = elements.get(r["Element Code"])
                    v = num(r["Value"])
                    key = (el[0] if el else None, r["Item Code"], r["Year"])
                    if el and v is not None and key not in seen:
                        seen.add(key)
                        sid = l.sector("fao", r["Item Code"], r["Item"])
                        l.stat(l.measure(el[0], el[1], el[2], "production"), int(r["Year"]), place, sid, v * el[3])


def split_trade(path, out):
    """One pass over the unsorted trade matrix: value rows from TRADE_FROM on, written to one file per exporter.
    An export row (reporter exports to partner) and an import row (reporter imports from partner) both land
    in the exporter's file, tagged E or I."""
    done = out / "split.done"
    if done.exists():
        return
    files = {}
    with zipfile.ZipFile(path) as z, z.open(TRADE + ".csv") as f:
        rd = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""))
        next(rd)
        for r in rd:
            # reporter code, m49, name, partner code, m49, name, item code, cpc, item, element code, element, year code, year, unit, value, flag
            if r[9] not in ("5922", "5622") or int(r[12]) < TRADE_FROM or not r[14]:
                continue
            exp, imp = (r[0:3], r[3:6]) if r[9] == "5922" else (r[3:6], r[0:3])
            fh = files.get(exp[0])
            if fh is None:
                fh = files[exp[0]] = open(out / ("x%s.csv" % exp[0]), "w", newline="")
            csv.writer(fh).writerow(["E" if r[9] == "5922" else "I"] + exp + imp + [r[6], r[8], r[12], r[14]])
    for fh in files.values():
        fh.close()
    done.write_text("ok")


def trade(l, d):
    path = kg.download(BULK + TRADE.replace(" ", "%20") + ".zip", d / "trade.zip")
    out = d / "trade"
    out.mkdir(exist_ok=True)
    split_trade(path, out)
    measure = l.measure("agri_trade_usd", "Agricultural trade value", "USD", "goods_trade",
                        "from = exporter, to = importer. The exporter's reported export value, or the importer's reported import value for pairs the exporter did not report")
    for f in sorted(out.glob("x*.csv")):
        part = "trade:" + f.stem[1:]
        if l.done(part):
            continue
        best = {}  # (importer, item, year) -> (kind, value); an export report beats an import report
        meta = {}
        with open(f, newline="") as fh:
            for kind, ec, em, en, ic, im, iname, item, iname2, year, v in csv.reader(fh):
                k = (ic, item, int(year))
                meta[ic], meta[ec] = (im, iname), (em, en)
                if k not in best or kind == "E":
                    best[k] = (kind, float(v) * 1000, iname2)
        exp = f.stem[1:]
        with l.part(part):
            src = fao_place(l, exp, meta[exp][0], meta[exp][1])
            if src:
                for (ic, item, year), (kind, v, name) in best.items():
                    dst = fao_place(l, ic, meta[ic][0], meta[ic][1])
                    if dst:
                        l.flow(measure, year, src, dst, l.sector("fao", item, name), v)


def main():
    l = kg.Loader("faostat", name="FAOSTAT production, value of production and trade",
                  publisher="Food and Agriculture Organization of the United Nations", url=PAGE, data_url=BULK,
                  kinds=["stats", "flows"],
                  about="Crop and livestock production (tonnes, area, stocks), gross production value in US dollars, and the detailed trade matrix of agricultural goods by exporter, importer and item",
                  coverage="Production 1961 onward, value 1961 onward, trade from 2010; all countries, ~500 items",
                  access="open", license="CC BY-NC-SA 3.0 IGO", found_by="survey")
    d = kg.workdir("faostat")
    for label, name, els in (("prod", PROD, PROD_EL), ("value", VALUE, VALUE_EL)):
        path = kg.download(BULK + name.replace(" ", "%20") + ".zip", d / (label + ".zip"))
        part_rows(l, label, path, name, els)
        path.unlink()
    trade(l, d)
    l.finish()
    kg.cleanup("faostat")


if __name__ == "__main__":
    main()
