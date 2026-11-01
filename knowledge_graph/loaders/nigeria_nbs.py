"""Nigeria NBS: GDP by activity at current basic prices (national, annual) and internally generated revenue by state."""
import re
import urllib.request
import zipfile

import kg
from loaders._sector_helpers import num

PAGE = "https://microdata.nigerianstat.gov.ng/index.php/catalog/147"
RELATED = PAGE + "/related-materials"
SHEET = "GDP_Curr_K_dfl_%Distrn"
IGR = "https://www.nigerianstat.gov.ng/download/1241579"  # Internally Generated Revenue at State Level, 2023


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def latest_q4_report():
    """Download id of the newest quarterly GDP report for a fourth quarter, which carries full-year totals."""
    html = urllib.request.urlopen(urllib.request.Request(RELATED, headers={"User-Agent": kg.UA}), timeout=60).read().decode("utf-8", "ignore")
    for m in re.finditer(r"Nigerian Gross Domestic Product Report (Q4 \d{4}).{0,1500}?catalog/147/download/(\d+)", html, re.S):
        return m.group(1), m.group(2)
    raise RuntimeError("no Q4 GDP report listed")


def gdp(l, d):
    import openpyxl
    label, rid = latest_q4_report()
    z = kg.download("%s/download/%s" % (PAGE, rid), d / "gdp.zip")
    with zipfile.ZipFile(z) as zf:
        member = next(n for n in zf.namelist() if n.endswith(".xlsx"))
        zf.extract(member, d)
    ws = openpyxl.load_workbook(d / member, read_only=True, data_only=True)[SHEET]
    rows = list(ws.iter_rows(values_only=True))
    years = {}  # column -> year, only the annual Total columns
    for i, r in enumerate(rows[:8]):
        if r[1:2] and isinstance(r[1], int):
            year_row, label_row = r, rows[i + 1]
            for c in range(1, len(r)):
                if isinstance(year_row[c], int):
                    cur = year_row[c]
                if label_row[c] == "Total":
                    years[c] = cur
            break
    ng = l.measure("value_added_ngn", "Value added", "NGN", "output", "Gross value added at current basic prices in naira, by activity, full year")
    total = l.sector("ng_nbs", "TOTAL", "GDP at current basic prices")
    nig = l.place("NGA")
    group = None
    with l.part("gdp:" + label):
        for r in rows[6:]:
            name = (r[0] or "").strip()
            if not name:
                continue
            if name.startswith("GDP") and "Basic" in name:
                for c, y in years.items():
                    l.stat(ng, y, nig, total, num(r[c]) * 1e6)
                break
            vals = {c: num(r[c]) for c in years}
            if all(v is None for v in vals.values()):
                if name.isupper() and name != "ACTIVITY SECTOR":
                    group = l.sector("ng_nbs", slug(name), name.capitalize(), total)
                continue
            clean = re.sub(r"^\d+\.\s*", "", name).strip(" ,")
            clean = clean if not clean.isupper() else clean.capitalize()
            standalone = name[:1].isdigit() and clean.isupper() is False and r[0][:1] != " "
            sid = l.sector("ng_nbs", slug(clean), clean, total if standalone else group)
            for c, y in years.items():
                if vals[c] is not None:
                    l.stat(ng, y, nig, sid, vals[c] * 1e6)
    return label


def igr(l, d):
    import pdfplumber
    from loaders._sector_helpers import admin_lookup, norm_name, Unmatched
    path = kg.download(IGR, d / "igr.pdf")
    states = admin_lookup(l, "NG")
    states[norm_name("FCT")] = states[norm_name("Federal Capital Territory")]
    ngn = l.measure("igr_ngn", "Internally generated revenue", "NGN", "output", "State tax revenue and revenue of state ministries, departments and agencies, naira, full year")
    total = l.sector("ng_igr", "TOTAL", "Internally generated revenue")
    tax = l.sector("ng_igr", "tax", "Tax revenue", total)
    mda = l.sector("ng_igr", "mda", "Ministries, departments and agencies revenue", total)
    bad = Unmatched()
    with pdfplumber.open(path) as pdf:
        year = int(re.search(r"\((\d{4})\)", pdf.pages[0].extract_text()).group(1))
        if l.done("igr:%d" % year):
            return
        with l.part("igr:%d" % year):
            for page in pdf.pages:
                for table in page.extract_tables():
                    if table and table[0][:2] == ["SN", "State"]:
                        for r in table[1:]:
                            vals = [num(c) if c and c != "-" else 0.0 for c in r[2:5]]
                            place = states.get(norm_name(r[1]))
                            if not place:
                                bad.add(r[1])
                            elif abs(vals[0] + vals[1] - vals[2]) <= 0.01 * vals[2]:
                                for sid, v in zip((tax, mda, total), vals):
                                    l.stat(ngn, year, place, sid, v)
    bad.report("nigeria_nbs")


def main():
    l = kg.Loader("nigeria_nbs", name="Nigeria NBS GDP by activity",
                  publisher="Nigeria National Bureau of Statistics", url=PAGE, data_url=RELATED, kinds=["stats"],
                  about="GDP by activity at current basic prices in naira for the country, full years from the latest fourth-quarter GDP report; internally generated revenue by state",
                  coverage="Nigeria, three years ending the latest Q4 report", access="open", license="NBS publication", found_by="survey")
    d = kg.workdir("nigeria_nbs")
    label = gdp(l, d)
    igr(l, d)
    l.finish(note="GDP from the %s report; state level is internally generated revenue (2023), no state GDP table found" % label)
    kg.cleanup("nigeria_nbs")


if __name__ == "__main__":
    main()
