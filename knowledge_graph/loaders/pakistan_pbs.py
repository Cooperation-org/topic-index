"""Pakistan Bureau of Statistics, National Accounts Table 4: GDP by sector at current basic prices, fiscal years 1999-2000 to 2024-25."""
import re

import kg
from loaders._sector_helpers import num

PAGE = "https://www.pbs.gov.pk/national-accounts-tables/"
LIVE = "https://www.pbs.gov.pk/sites/default/files/tables/national_accounts/2024-25/Table_4.pdf"  # no longer served
SNAPSHOT = "http://web.archive.org/web/20250605035014id_/" + LIVE  # Internet Archive copy of the same file
NUM = re.compile(r"^\(?\d[\d.]*\)?$")
HEADER = re.compile(r"^(Table 4|Gross Domestic Product of Pakistan|\(Rs\. Million\)|Sector/Industry|S\. No|\*|\(?[FRP]\)?$|\d{4}-\d{2}$)")
GROUPS = {"Agriculture, Forestry and Fishing": "agriculture", "Industrial Activities": "industry", "Services": "services"}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def clean(label):
    s = re.sub(r"^[A-M]\s+(?=[A-Z])", "", label)                  # letter of the group
    s = re.sub(r"\(\s*\d+ to \d+\s*[A-Z]?\s*\)?|\(\s*[A-Z]\s*\)|\([+A-Z ]+\)$", "", s)  # '( 1 to 4 A )', '(A+B)'
    s = re.sub(r"^(\d+|[ivx]+)[.)]\s*|^\d+\s+", "", s.strip())
    s = re.sub(r"\s*\(\s*(?:i\+ii\+iii|OD|General Government|Hotels & Restaurants)\s*\)\s*", " ", s)
    return re.sub(r"\s+", " ", s).strip(" ,")


def rows(pdf):
    """(label, {fiscal year end: Rs million}) for each data line on every page, labels joined across wrapped lines."""
    for page in pdf.pages:
        lines = (page.extract_text() or "").splitlines()
        years = sorted(int(m.group(1)) + 1
                       for m in re.finditer(r"(\d{4})-\d{2}", " ".join(l for l in lines if "Sector/Industry" in l or re.fullmatch(r"\d{4}-\d{2}", l.strip()))))
        pending = ""
        for line in lines:
            line = line.strip()
            if HEADER.match(line):
                continue
            toks = line.split()
            n = 0
            while n < len(toks) and NUM.match(toks[-1 - n]):
                n += 1
            n = min(n, len(years))
            if n < len(years):
                pending = (pending + " " + line).strip()
                continue
            label = (pending + " " + " ".join(toks[:-n])).strip()
            pending = ""
            vals = [num(t.strip("()")) * (-1 if t.startswith("(") else 1) for t in toks[-n:]]
            yield label, dict(zip(years, vals))


def main():
    import pdfplumber
    l = kg.Loader("pakistan_pbs", name="Pakistan GDP by sector, national accounts",
                  publisher="Pakistan Bureau of Statistics", url=PAGE, data_url=SNAPSHOT, kinds=["stats"],
                  about="GDP at current basic prices by sector in Pakistani rupees, national, fiscal years labelled by the calendar year they end; the file is no longer served by PBS, read from an Internet Archive copy; no provincial table found",
                  coverage="Pakistan, 2000 to 2025", access="open", license="PBS publication", found_by="survey")
    d = kg.workdir("pakistan_pbs")
    path = kg.download(SNAPSHOT, d / "table4.pdf")
    if l.done("table4"):
        l.finish()
        return
    pkr = l.measure("value_added_pkr", "Value added", "PKR", "output",
                    "Gross value added at current basic prices in rupees by sector; year is the calendar year the fiscal year (July to June) ends")
    pak = l.place("PAK")
    total = l.sector("pk_pbs", "TOTAL", "GDP at basic prices")
    group = item = None
    with l.part("table4"), pdfplumber.open(path) as pdf:
        for label, vals in rows(pdf):
            name = clean(label)
            if label.startswith("D GDP"):
                sid = total
            elif name in GROUPS or name.startswith("Services"):
                group = l.sector("pk_pbs", GROUPS.get(name, "services"), name, total)
                item, sid = None, group
            elif re.match(r"^(\d+[.\s]|\d+$)", label) and group:
                item = l.sector("pk_pbs", slug(name), name, group)
                sid = item
            elif re.match(r"^(i|ii|iii)\)", label) and item:
                sid = l.sector("pk_pbs", slug(name), name, item)
            else:
                continue
            for y, v in vals.items():
                l.stat(pkr, y, pak, sid, v * 1e6)
    l.finish()
    kg.cleanup("pakistan_pbs")


if __name__ == "__main__":
    main()
