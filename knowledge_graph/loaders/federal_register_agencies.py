"""Federal Register agencies as government entities, plus rules and proposed rules since 2015 that mention supply chain,
forced labor or customs, stored as pages tagged supply-chain-regulation."""
import datetime
import json
import time
import urllib.error
import urllib.parse
import urllib.request

import kg
import ti
from loaders._entity_helpers import add_links, bulk_entities

BASE = "https://www.federalregister.gov/api/v1/"
TOPIC = "supply-chain-regulation"
TERMS = ('"supply chain"', '"forced labor"', "customs")
FIRST_YEAR = 2015
PAUSE = 0.5


def get(url, tries=4, raw=False):
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": kg.UA})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
                return body.decode("utf-8", "replace") if raw else json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(10 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, ValueError):
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("Federal Register request failed: " + url)


def documents(term, year):
    q = [("conditions[term]", term), ("conditions[type][]", "RULE"), ("conditions[type][]", "PRORULE"),
         ("conditions[publication_date][year]", year), ("per_page", 200), ("order", "oldest")]
    q += [("fields[]", f) for f in ("title", "abstract", "html_url", "raw_text_url", "publication_date", "agencies", "type")]
    page = 1
    while True:
        data = get(BASE + "documents.json?" + urllib.parse.urlencode(q + [("page", page)]))
        yield from data.get("results", [])
        if page >= data.get("total_pages", 1):
            return
        page += 1
        time.sleep(PAUSE)


def main():
    l = kg.Loader("federal_register_agencies", name="Federal Register agencies and rules", publisher="US Office of the Federal Register",
                  url="https://www.federalregister.gov/", data_url=BASE, kinds=["entities", "links", "pages"],
                  about="US federal agencies with parent agency, and rules and proposed rules on supply chain, forced labor and customs as pages",
                  coverage="United States, rules from %d" % FIRST_YEAR, access="open", license="US government work, public domain",
                  found_by="core")
    usa = l.country(iso3="USA")
    if not l.done("agencies"):
        agencies = get(BASE + "agencies.json")
        by_id = {a["id"]: a for a in agencies}
        rows = [(a["slug"], a["name"], "government", usa, None, None, None, a.get("url") or None,
                 {k: v for k, v in {"short_name": a.get("short_name"), "description": (a.get("description") or "").strip() or None}.items() if v})
                for a in agencies]
        with l.part("agencies"):
            bulk_entities(l, rows)
            add_links(l, [("parent_agency", a["slug"], by_id[a["parent_id"]]["slug"], None, None, None, None, None)
                          for a in agencies if a.get("parent_id") in by_id])
    for term in TERMS:
        for year in range(datetime.date.today().year, FIRST_YEAR - 1, -1):
            part = "docs:%s:%d" % (term.strip('"'), year)
            if l.done(part):
                continue
            n = 0
            with l.part(part):
                for d in documents(term, year):
                    text = get(d["raw_text_url"], raw=True) if d.get("raw_text_url") else None
                    time.sleep(PAUSE)
                    agency_names = ", ".join(a.get("name") or a.get("raw_name") for a in d.get("agencies") or [])
                    md = "\n\n".join(x for x in (d.get("abstract"), text) if x)
                    if not md:
                        continue
                    pid = ti.store_page(l.cur, d["html_url"], d["title"], "%s, %s, %s" % (d["type"], agency_names, d["publication_date"]),
                                        md, d["publication_date"], "federalregister")
                    ti.tag(l.cur, pid, TOPIC)
                    n += 1
                l.written += n
    l.finish()


if __name__ == "__main__":
    main()
