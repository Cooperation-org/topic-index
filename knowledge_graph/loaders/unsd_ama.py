"""UN National Accounts Main Aggregates: GDP and value added by ISIC group, current US dollars, by country, all years."""
import kg
from loaders._sector_helpers import num, country_or_other, Unmatched

PAGE = "https://unstats.un.org/unsd/snaama/Downloads"
FILE = "https://unstats.un.org/unsd/amaapi/api/file/2"  # GDP and its breakdown at current prices in US Dollars, all countries
# indicator name -> (isic code, parent code)
ISIC = {
    "Total Value Added": ("TOTAL", None),
    "Agriculture, hunting, forestry, fishing (ISIC A-B)": ("A-B", "TOTAL"),
    "Mining, Manufacturing, Utilities (ISIC C-E)": ("C-E", "TOTAL"),
    "Manufacturing (ISIC D)": ("D", "C-E"),
    "Construction (ISIC F)": ("F", "TOTAL"),
    "Wholesale, retail trade, restaurants and hotels (ISIC G-H)": ("G-H", "TOTAL"),
    "Transport, storage and communication (ISIC I)": ("I", "TOTAL"),
    "Other Activities (ISIC J-P)": ("J-P", "TOTAL"),
}
GDP = "Gross Domestic Product (GDP)"


def main():
    import openpyxl
    l = kg.Loader("unsd_ama", name="UN National Accounts Main Aggregates: GDP and value added by industry",
                  publisher="UN Statistics Division", url=PAGE, data_url=FILE, kinds=["stats"],
                  about="GDP and value added by ISIC group, ISIC Rev.3 style (A-B, C-E, D, F, G-H, I, J-P), current US dollars, by country and year",
                  coverage="~220 countries and areas, 1970 onward", access="open",
                  license="UN data terms of use", found_by="survey")
    d = kg.workdir("unsd_ama")
    path = kg.download(FILE, d / "ama_usd.xlsx")
    va = l.measure("value_added_usd", "Value added", "USD", "output",
                   "Gross value added at current prices by industry, converted to US dollars at market exchange rates")
    gdp = l.measure("gdp_usd", "GDP", "USD", "output", "Gross domestic product at current prices in US dollars")
    # parents first, by order of ISIC above
    sectors = {}
    ids = {}
    for name, (code, parent) in ISIC.items():
        ids[code] = l.sector("isic_ama", code, name, ids.get(parent))
        sectors[name] = ids[code]
    l.conn.commit()
    bad = Unmatched()
    ws = openpyxl.load_workbook(path, read_only=True)["Download-GDPcurrent-USD-countri"]
    rows = ws.iter_rows(values_only=True)
    next(rows), next(rows)
    head = next(rows)
    years = {i: int(y) for i, y in enumerate(head) if i >= 3 and y is not None}
    cur_id, buf = None, []

    def store(cid, buf):
        if cid is None or l.done(str(cid)):
            return
        with l.part(str(cid)):
            for place, ind, r in buf:
                for i, y in years.items():
                    v = num(r[i])
                    if v is None:
                        continue
                    if ind == GDP:
                        l.stat(gdp, y, place, None, v)
                    else:
                        l.stat(va, y, place, sectors[ind], v)

    for r in rows:
        if r[0] is None or r[2] not in ISIC and r[2] != GDP:
            continue
        if r[0] != cur_id:
            store(cur_id, buf)
            cur_id, buf = r[0], []
        place = country_or_other(l, m49=r[0], name=r[1], prefix="m49")
        if not place:
            bad.add(r[1])
            continue
        buf.append((place, r[2], r))
    store(cur_id, buf)
    bad.report("unsd_ama")
    l.finish()
    kg.cleanup("unsd_ama")


if __name__ == "__main__":
    main()
