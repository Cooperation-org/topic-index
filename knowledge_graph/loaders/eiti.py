"""EITI: payments by oil, gas and mining companies to governments, by country and year, from the open API."""
import re
from concurrent.futures import ThreadPoolExecutor

import kg
from loaders._money_helpers import Countries, bulk_entities, bulk_links, fetch

API = "https://eiti.org/api/v2.0/revenue?per_page=50&page=%d"
PAGE = 50
WORKERS = 4


def main():
    l = kg.Loader("eiti", name="EITI revenue data", publisher="Extractive Industries Transparency Initiative",
                  url="https://eiti.org/open-data", data_url="https://eiti.org/api/v2.0/revenue", kinds=["entities", "links"],
                  about="Payments by extractive companies to governments, by revenue stream, country and year, as the companies report them",
                  coverage="EITI implementing countries, 2000s to latest report year", access="open",
                  license="CC BY 4.0 (EITI open data policy)", found_by="survey")
    cs = Countries(l)
    count = fetch("https://eiti.org/api/v2.0/revenue?per_page=1")["count"]
    pages = [p for p in range(1, count // PAGE + 2) if not l.done("p%d" % p)]
    with ThreadPoolExecutor(WORKERS) as ex:
        for p, doc in zip(pages, ex.map(lambda p: fetch(API % p), pages)):
            with l.part("p%d" % p):
                ents, rows = {}, []
                for r in doc["data"]:
                    if r.get("type") != "company" or r.get("organisation.type") != "company":
                        continue
                    place = cs.get(iso2=r.get("summary_data.iso2"), key=r.get("summary_data.iso2"))
                    try:
                        value = float(r["revenue"])
                    except (TypeError, ValueError):
                        continue
                    if not place:
                        continue
                    name = (r.get("organisation.label") or "").strip()
                    ext = "n|%s|%s" % (re.sub(r"\s+", " ", name.lower()), r.get("summary_data.iso2"))
                    ents[ext] = (ext, name, "company", None, None,
                                 {k: v for k, v in {"identification": r.get("organisation.identification"), "sector": r.get("organisation.sector"),
                                                    "commodities": r.get("organisation.commodities"),
                                                    "reports_in": r.get("summary_data.iso2")}.items() if v})
                    rows.append((ext, place, r))
                ids = bulk_entities(l, list(ents.values())) if ents else {}
                bulk_links(l, [("paid_government_in", ids[ext], None, place, None, int(r.get("summary_data.year")), value_of(r), r.get("currency") or "USD",
                                {k: v for k, v in {"stream": r.get("label"), "gfs": r.get("gfs.code"), "project": r.get("project_name"),
                                                   "sector": r.get("sector"), "in_kind": r.get("payment_made_in_kind")}.items() if v})
                               for ext, place, r in rows if value_of(r) is not None and r.get("summary_data.year")])
    cs.report()
    l.finish()


def value_of(r):
    try:
        return float(r["revenue"])
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    main()
