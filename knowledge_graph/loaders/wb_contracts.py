"""World Bank contract awards in investment project financing: suppliers (companies) contracted in each borrower country."""
import csv
import re

import kg
from loaders._money_helpers import Countries, bulk_entities, bulk_links

BASE = "https://financesonefiles.worldbank.org/f-one/"
FILES = [  # newest first: its country name and code pairs resolve names in the older files
    ("fy2020_on", BASE + "DS00005/RS00005/Contract_Awards_in_Investment_Project_Financing__Since_FY_2020_.csv"),
    ("fy2017_2019", BASE + "DS04691/RS03933/Contract_Awards_in_Investment_Project_Financing__since_FY_2017___FY_2019_.csv"),
    ("fy2001_2016", BASE + "DS01004/RS00934/Contract_Awards_in_Investment_Project_Financing__since_FY_2001___FY_2016_.csv"),
]
CHUNK = 20000


def pick(r, *names):
    for n in names:
        if n in r:
            return r[n]
    return ""


def main():
    l = kg.Loader("wb_contracts", name="World Bank contract awards in investment project financing", publisher="World Bank",
                  url="https://financesone.worldbank.org/contract-awards-in-investment-project-financing-since-fy-2020/DS00005",
                  data_url=BASE, kinds=["entities", "links"],
                  about="Contracts signed under World Bank financed projects: supplier, supplier country, borrower country, category, method, amount",
                  coverage="Borrower countries, contracts signed since fiscal year 2001", access="open", license="CC BY 4.0", found_by="survey")
    cs = Countries(l)
    names = {}  # country name -> iso2, learned from rows that carry both
    ents = {}   # ext_id -> entity id
    d = kg.workdir("wb_contracts")

    def country(name, code):
        if code:
            names[name.lower()] = code
        # regional and world borrowers (Africa, World) are places of their own, so no contract is dropped
        return cs.get(iso2=code or names.get(name.lower()), name=name, key=name) or l.other_place("wb:" + name, name)

    for part, url in FILES:
        if l.done(part):
            continue
        path = kg.download(url, d / (part + ".csv"))
        with l.part(part), open(path, encoding="utf-8-sig", newline="") as f:
            batch = []

            def flush():
                if not batch:
                    return
                new = {}
                for sup, ext, kind, p, attrs, _ in batch:
                    if ext not in ents:
                        new[ext] = (ext, sup, kind, p, None, attrs)
                if new:
                    ents.update(bulk_entities(l, list(new.values())))
                bulk_links(l, [("contracted_in", ents[ext], None, to, None, year, amt, "USD", la)
                               for sup, ext, kind, p, attrs, (to, year, amt, la) in batch])
                l.flush()
                batch.clear()

            for r in csv.DictReader(f):
                amt = pick(r, "Supplier Contract Amount (USD)", "Supplier Contract Amount (US$)")
                try:
                    amt = float(amt)
                except ValueError:
                    continue
                to = country(r["Borrower Country / Economy"], pick(r, "Borrower Country / Economy Code"))
                if not to:
                    continue
                sname = r["Supplier"].strip()
                scountry = r["Supplier Country / Economy"]
                sp = country(scountry, pick(r, "Supplier Country / Economy Code")) if scountry else None
                year = pick(r, "Contract signed - Calendar year")
                method = r["Procurement Method"]
                if "Individual" in method or sname.upper() == "INDIVIDUAL CONSULTANT":
                    # individual consultants are one anonymous entity per country, no personal names
                    ext, name, kind = "individuals|" + scountry, "Individual consultants (%s)" % (scountry or "unknown country"), "individual"
                else:
                    sid = pick(r, "Supplier ID")
                    ext = sid or "n|" + re.sub(r"\s+", " ", sname.lower()) + "|" + scountry.lower()
                    name, kind = sname, "company"
                batch.append((name, ext, kind, sp, {"country": scountry} if scountry else None,
                              (to, int(year) if year.isdigit() else None, amt,
                               {"project": r["Project ID"], "category": r["Procurement Category"], "method": method,
                                "supplier_country": scountry, "fiscal_year": r["Fiscal Year"]})))
                if len(batch) >= CHUNK:
                    flush()
            flush()
    cs.report()
    l.finish()
    kg.cleanup("wb_contracts")


if __name__ == "__main__":
    main()
