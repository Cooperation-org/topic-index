"""BIS locational banking statistics: cross-border bank claims, reporting country to counterparty country, year-end."""
import csv
import io
import zipfile

import kg
from loaders._money_helpers import Countries

URL = "https://data.bis.org/static/bulk/WS_LBS_D_PUB_csv_flat.zip"
MEMBER = "WS_LBS_D_PUB_csv_flat.csv"
# FREQ, MEASURE, POSITION, INSTRUMENT, DENOMINATION, CURRENCY TYPE: quarterly stocks of total claims, all instruments and currencies
PREFIX = ",Q: Quarterly,S: Amounts outstanding / Stocks,C: Total claims,A: All instruments,TO1: All currencies,A: All currencies"


def code(cell):
    return cell.split(":", 1)[0].strip()


def main():
    l = kg.Loader("bis_lbs", name="Locational banking statistics", publisher="Bank for International Settlements",
                  url="https://data.bis.org/topics/LBS", data_url="https://data.bis.org/bulkdownload", kinds=["flows"],
                  about="Cross-border claims of banks in each reporting country on borrowers in each counterparty country",
                  coverage="About 50 reporting countries, counterparty countries, quarterly from 1977, stored at year-end",
                  access="open", license="BIS terms, https://www.bis.org/terms_conditions.htm", found_by="survey")
    mid = l.measure("bank_claims_usd", "Cross-border bank claims, USD", "USD", "banking",
                    about="from = reporting country (where the lending bank offices sit), to = counterparty country (residence of the borrower), year-end (Q4) stock of total cross-border claims, all instruments, all currencies, all reporting banks, all counterparty sectors, by residence. Counterparties such as All countries are aggregates stored as bis: places, do not add them to countries")
    cs = Countries(l)
    d = kg.workdir("bis_lbs")
    path = kg.download(URL, d / "lbs.zip")
    stock, names, seen = {}, {}, {}
    with zipfile.ZipFile(path) as z, z.open(MEMBER) as f:
        lines = io.TextIOWrapper(f, encoding="utf-8-sig", newline="")
        for n, line in enumerate(lines):
            if PREFIX not in line:
                continue
            row = next(csv.reader([line]))
            period = row[15]
            if not period.endswith("-Q4") or not row[16]:
                continue
            # parent country all, all institution types, cross-border position
            if code(row[9]) != "5J" or code(row[10]) != "A" or code(row[14]) != "N":
                continue
            rep, cp = code(row[11]), code(row[13])
            if rep == "5A" or rep == cp:
                continue
            names[rep], names[cp] = row[11].split(": ", 1)[1], row[13].split(": ", 1)[1]
            sector = code(row[12])
            seen[sector] = seen.get(sector, 0) + 1
            stock.setdefault((rep, cp, int(period[:4])), {})[sector] = float(row[16]) * 1e6
    print("sectors seen:", seen, flush=True)
    # one row per pair and year: all sectors (A) when given, else sum of banks (B) and non-banks (P, U)
    by_rep = {}
    for (rep, cp, year), s in stock.items():
        v = s["A"] if "A" in s else (s.get("B", 0) + s.get("P", 0) + s.get("U", 0) if ("B" in s) else None)
        if v is not None:
            by_rep.setdefault(rep, []).append((cp, year, v))
    del stock
    for rep, rows in sorted(by_rep.items()):
        if l.done(rep):
            continue
        with l.part(rep):
            rp = cs.get(iso2=rep) or l.other_place("bis:" + rep, names[rep])
            for cp, year, v in rows:
                l.flow(mid, year, rp, cs.get(iso2=cp) or l.other_place("bis:" + cp, names[cp]), None, v)
    cs.report()
    l.finish()
    kg.cleanup("bis_lbs")


if __name__ == "__main__":
    main()
