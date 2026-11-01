"""US Senate LDA quarterly lobbying reports, last 3 years: registrants (firms and self-filers), their clients, issue areas, amounts.
No lobbyist names are read or stored. Original quarterly reports only (types Q1 to Q4); amendments are skipped.
Anonymous API access is throttled to about 15 requests a minute, so this takes hours; it restarts by page chunk.

  registrant -lobbies_for-> client      one link per issue code and report, sector = issue code, year, attrs.period
  registrant -lobbying_spend-> client   one link per report, value = income (firms) or expenses (self-filers) in USD"""
import datetime
import json
import re
import time
import urllib.error
import urllib.request

import kg
from loaders._entity_helpers import add_links, bulk_entities

API = "https://lda.gov/api/v1/filings/"
PAGE = 25
CHUNK_PAGES = 20
PAUSE = 4.2
TYPES = ("Q4", "Q3", "Q2", "Q1")


def get(url, tries=6):
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": kg.UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 429:
                m = re.search(r"in (\d+) seconds", body)
                time.sleep(int(m.group(1)) + 1 if m else 15)
            elif e.code in (500, 502, 503, 504):
                time.sleep(15 * (attempt + 1))
            else:
                raise
        except (urllib.error.URLError, TimeoutError, ValueError):
            time.sleep(15 * (attempt + 1))
    raise RuntimeError("LDA API failed: " + url)


def amount(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def main():
    l = kg.Loader("us_lobbying", name="US Senate Lobbying Disclosure Act reports", publisher="US Senate Office of Public Records",
                  url="https://lda.gov/", data_url=API, kinds=["entities", "links"],
                  about="Quarterly lobbying reports: registrants, clients, issue areas and amounts, last 3 years",
                  coverage="United States federal lobbying", access="open (anonymous API throttled to about 15 requests a minute)",
                  license="US government work, public domain", found_by="core")
    this_year = datetime.date.today().year

    def where(country, state):
        return (country == "US" and state and l.place("US." + state)) or l.country(iso2=country or "")

    def clean(d):
        return {k: v for k, v in d.items() if v}

    for year in range(this_year, this_year - 3, -1):
        for ftype in TYPES:
            base = "%s?filing_year=%d&filing_type=%s&page_size=%d&ordering=dt_posted" % (API, year, ftype, PAGE)
            first = get(base + "&page=1")
            time.sleep(PAUSE)
            pages = max(1, -(-first["count"] // PAGE))
            for start in range(1, pages + 1, CHUNK_PAGES):
                part = "%d-%s-p%05d" % (year, ftype, start)
                if l.done(part):
                    continue
                ents, links = [], []
                for page in range(start, min(start + CHUNK_PAGES, pages + 1)):
                    if page == 1:
                        data = first
                    else:
                        try:
                            data = get("%s&page=%d" % (base, page))
                        except urllib.error.HTTPError as e:
                            if e.code == 404:  # fewer pages than counted
                                break
                            raise
                        time.sleep(PAUSE)
                    for f in data["results"]:
                        reg, cli = f["registrant"], f["client"]
                        rid, cid = "R:%s" % reg["id"], "C:%s" % cli["id"]
                        ents.append((rid, reg["name"], "lobbyist", where(reg.get("country"), reg.get("state")), None, None, None, None,
                                     clean({"country": reg.get("country"), "state": reg.get("state"), "city": reg.get("city")})))
                        ents.append((cid, cli["name"], "lobby_client", where(cli.get("country"), cli.get("state")), None, None, None, None,
                                     clean({"description": cli.get("general_description"), "country": cli.get("country"),
                                            "state": cli.get("state")})))
                        attrs = {"period": f["filing_period"], "filing": f["filing_uuid"]}
                        for a in f.get("lobbying_activities") or []:
                            if a.get("general_issue_code"):
                                sec = l.sector("lda_issue", a["general_issue_code"], a.get("general_issue_code_display"))
                                links.append(("lobbies_for", rid, cid, sec, f["filing_year"], None, None, attrs))
                        value = amount(f.get("income")) if f.get("income") is not None else amount(f.get("expenses"))
                        if value is not None:
                            links.append(("lobbying_spend", rid, cid, None, f["filing_year"], value, "USD", attrs))
                with l.part(part):
                    bulk_entities(l, ents)
                    add_links(l, links)
    l.finish("last 3 years of Q1 to Q4 original reports")
    kg.cleanup("us_lobbying")


if __name__ == "__main__":
    main()
