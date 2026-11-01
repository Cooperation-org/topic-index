"""Wikidata businesses and enterprises per country: name, headquarters or item coordinates, industry, website, parent, owner.

Queries Wikidata Query Service one request at a time, grouped countries per request, one company class per request
(a single query across all classes times out). Restart unit is country and class. Owner and parent links are built at
the end from the stored Q-numbers; only owners that are stored companies become links, so people owners are dropped."""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import kg
from loaders._entity_helpers import bulk_entities, geo_ok

ENDPOINT = "https://query.wikidata.org/sparql"
UA = "topic-index-knowledge-graph/0.1 (https://github.com/Cooperation-org; research on corporate ownership)"
PAUSE = 2.0
BATCH_ITEMS = 1500  # items per request; Wikidata times out around 60 seconds
CLASSES = {  # direct P31 values; None is any non-human item with an industry
    "business": "Q4830453", "enterprise": "Q6881511", "company": "Q783794", "public_company": "Q891723",
    "privately_held": "Q1589009", "subsidiary": "Q658255", "holding": "Q219577", "state_owned": "Q270791",
    "corporation": "Q167037", "plc": "Q5225895", "bank": "Q22687", "insurer": "Q2143354", "software": "Q1058914",
    "technology": "Q18388277", "telecom": "Q2401749", "carmaker": "Q786820", "aerospace": "Q936518",
    "transport": "Q740752", "airline": "Q46970", "retail_chain": "Q507619", "has_industry": None}

QUERY = """SELECT ?item ?country (SAMPLE(?n) AS ?name) (SAMPLE(?co) AS ?coord) (SAMPLE(?hc) AS ?hqcoord) (SAMPLE(?w) AS ?web)
  (GROUP_CONCAT(DISTINCT CONCAT(STRAFTER(STR(?i), "entity/"), "~", ?il); separator="|") AS ?ind)
  (GROUP_CONCAT(DISTINCT STRAFTER(STR(?par), "entity/"); separator="|") AS ?parents)
  (GROUP_CONCAT(DISTINCT STRAFTER(STR(?own), "entity/"); separator="|") AS ?owners)
WHERE {
  VALUES ?country { %(countries)s }
  ?item wdt:P17 ?country .
  %(cls)s
  ?item rdfs:label ?n . FILTER(LANG(?n) = "en")
  OPTIONAL { ?item wdt:P625 ?co }
  OPTIONAL { ?item wdt:P159/wdt:P625 ?hc }
  OPTIONAL { ?item wdt:P856 ?w }
  OPTIONAL { ?item wdt:P452 ?i . ?i rdfs:label ?il . FILTER(LANG(?il) = "en") }
  OPTIONAL { ?item wdt:P749 ?par }
  OPTIONAL { ?item wdt:P127 ?own }
} GROUP BY ?item ?country"""


def sparql(query, tries=4):
    data = urllib.parse.urlencode({"query": query}).encode()
    for attempt in range(tries):
        req = urllib.request.Request(ENDPOINT, data=data, headers={"Accept": "application/sparql-results+json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=100) as r:
                return json.load(r)["results"]["bindings"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(int(e.headers.get("Retry-After", 30)) + 5)
            elif e.code in (500, 502, 503, 504):
                return None  # query too heavy; caller splits
            else:
                raise
        except (urllib.error.URLError, TimeoutError, ValueError):  # ValueError: response cut off at the timeout
            time.sleep(10 * (attempt + 1))
    return None


def point(wkt):
    m = re.match(r"Point\(([-\d.eE+]+) ([-\d.eE+]+)\)", wkt or "")
    return geo_ok(m.group(2), m.group(1)) if m else (None, None)


def val(b, k):
    return b[k]["value"] if k in b and b[k]["value"] else None


def main():
    l = kg.Loader("wikidata_companies", name="Wikidata companies", publisher="Wikimedia Foundation",
                  url="https://www.wikidata.org/", data_url=ENDPOINT, kinds=["entities", "links"],
                  about="Businesses and enterprises per country with industry, coordinates, website, parent and owner",
                  coverage="World; items typed as business, enterprise, company and common company classes, or with an industry",
                  access="open", license="CC0 1.0", found_by="core")
    rows = sparql("SELECT ?c ?iso WHERE { ?c wdt:P297 ?iso }")
    if rows is None:
        return l.fail("could not list countries from Wikidata")
    country_q = {}
    for b in rows:
        pid = l.country(iso2=b["iso"]["value"])
        if pid:
            country_q[b["iso"]["value"]] = (b["c"]["value"].rsplit("/", 1)[1], pid)
    isos = sorted(country_q)
    failed = []

    def store(cls, iso, items):
        part = "%s:%s" % (cls, iso)
        pid = country_q[iso][1]
        out = []
        for b in items:
            lat, lon = point(val(b, "coord"))
            if lat is None:
                lat, lon = point(val(b, "hqcoord"))
            inds = [x.split("~", 1) for x in (val(b, "ind") or "").split("|") if "~" in x]
            sector = l.sector("wikidata_industry", inds[0][0], inds[0][1]) if inds else None
            attrs = {"industries": [x[1] for x in inds] or None,
                     "parent_ids": (val(b, "parents") or "").split("|") if val(b, "parents") else None,
                     "owner_ids": (val(b, "owners") or "").split("|") if val(b, "owners") else None}
            out.append((b["item"]["value"].rsplit("/", 1)[1], val(b, "name"), "company", pid, lat, lon, sector,
                        val(b, "web"), {k: v for k, v in attrs.items() if v}))
        with l.part(part):
            bulk_entities(l, out)

    batch_items = BATCH_ITEMS
    order = list(CLASSES.items())
    if os.environ.get("KG_REVERSE"):  # a second worker starts from the other end; finished parts are skipped
        order.reverse()
    for cls, qid in order:
        pattern = ("?item wdt:P31 wd:%s ." % qid) if qid else "?item wdt:P452 [] . FILTER NOT EXISTS { ?item wdt:P31 wd:Q5 }"
        todo = [i for i in isos if not l.done("%s:%s" % (cls, i))]
        if not todo:
            continue
        # items per country for this class, so empty countries cost nothing and small ones share a request
        counts = sparql("SELECT ?country (COUNT(DISTINCT ?item) AS ?n) WHERE { ?item wdt:P17 ?country . %s } GROUP BY ?country" % pattern)
        time.sleep(PAUSE)
        n_of = {}
        for b in counts or []:
            n_of[b["country"]["value"].rsplit("/", 1)[1]] = int(b["n"]["value"])
        known = counts is not None
        for i in todo:
            if known and country_q[i][0] not in n_of:
                with l.part("%s:%s" % (cls, i)):
                    pass
        todo = sorted((i for i in todo if not known or country_q[i][0] in n_of), key=lambda i: -n_of.get(country_q[i][0], 0))
        while todo:
            unit, total = [todo[0]], n_of.get(country_q[todo[0]][0], 0)
            while known and len(unit) < len(todo) and total + n_of[country_q[todo[len(unit)]][0]] <= batch_items:
                total += n_of[country_q[todo[len(unit)]][0]]
                unit.append(todo[len(unit)])
            items = sparql(QUERY % {"countries": " ".join("wd:" + country_q[i][0] for i in unit), "cls": pattern})
            time.sleep(PAUSE)
            if items is None:
                if len(unit) > 1:  # too heavy together: smaller batches
                    batch_items = max(100, total // 2)
                else:
                    failed.append("%s:%s" % (cls, unit[0]))
                    todo = todo[1:]
                continue
            by = {i: [] for i in unit}
            qs = {country_q[i][0]: i for i in unit}
            for b in items:
                by[qs[b["country"]["value"].rsplit("/", 1)[1]]].append(b)
            for i in unit:
                store(cls, i, by[i])
            todo = todo[len(unit):]

    if not failed and not l.done("links"):
        with l.part("links"):
            for kind, key in (("owned_by", "owner_ids"), ("parent_org", "parent_ids")):
                l.cur.execute("DELETE FROM kg.links WHERE source_id = %s AND kind = %s", (l.source_id, kind))
                l.cur.execute("""INSERT INTO kg.links (source_id, kind, from_entity, to_entity)
                                 SELECT DISTINCT a.source_id, %s, a.id, b.id
                                 FROM kg.entities a CROSS JOIN LATERAL jsonb_array_elements_text(a.attrs -> %s) AS t(q)
                                 JOIN kg.entities b ON b.source_id = a.source_id AND b.ext_id = t.q AND b.id <> a.id
                                 WHERE a.source_id = %s AND a.attrs ? %s""", (kind, key, l.source_id, key))
                l.written += l.cur.rowcount
            l.cur.execute("UPDATE kg.entities SET attrs = attrs - 'owner_ids' - 'parent_ids' WHERE source_id = %s", (l.source_id,))
    if failed:
        print("wikidata_companies: %d country/class queries failed, rerun to retry: %s" % (len(failed), failed[:20]), flush=True)
        l.cur.execute("UPDATE kg.sources SET status = 'loading', status_note = %s WHERE id = %s",
                      ("%d queries failed, rerun" % len(failed), l.source_id))
        l.conn.commit()
        return
    l.finish()


if __name__ == "__main__":
    main()
