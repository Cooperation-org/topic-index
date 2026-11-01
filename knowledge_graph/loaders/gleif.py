"""GLEIF Golden Copy: active issued LEI records (Level 1) and direct and ultimate parent links (Level 2).
Sole proprietors are skipped: organizations only."""
import csv
import io
import json
import sys
import urllib.request
import zipfile

import kg
from loaders._entity_helpers import bulk_entities, replace_links

API = "https://goldencopy.gleif.org/api/v2/golden-copies/publishes/latest"
CHUNK = 250_000
REL = {"IS_DIRECTLY_CONSOLIDATED_BY": "direct_parent", "IS_ULTIMATELY_CONSOLIDATED_BY": "ultimate_parent"}


def latest():
    req = urllib.request.Request(API, headers={"User-Agent": kg.UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)["data"]
    return d["lei2"]["full_file"]["csv"]["url"], d["rr"]["full_file"]["csv"]["url"], d["publish_date"]


def rows(path):
    csv.field_size_limit(sys.maxsize)
    with zipfile.ZipFile(path) as z:
        with z.open(z.namelist()[0]) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", newline=""))


def main():
    lei_url, rr_url, published = latest()
    l = kg.Loader("gleif", name="GLEIF Golden Copy: legal entities and parents",
                  publisher="Global Legal Entity Identifier Foundation",
                  url="https://www.gleif.org/en/lei-data/gleif-golden-copy",
                  data_url="https://goldencopy.gleif.org/api/v2/golden-copies/publishes/latest",
                  kinds=["entities", "links"],
                  about="Active issued LEI records with legal and headquarters country, city, region, category, plus direct and ultimate parent",
                  coverage="World, published " + published[:10], access="open", license="CC0 1.0", found_by="core")
    d = kg.workdir("gleif")
    lei_zip = kg.download(lei_url, d / lei_url.rsplit("/", 1)[1])
    rr_zip = kg.download(rr_url, d / rr_url.rsplit("/", 1)[1])

    def place(country, region):
        if not country:
            return None
        return (region and l.place(region.replace("-", ".", 1))) or l.country(iso2=country)

    batch, chunk, seen = [], 0, 0
    skip = l.done("entities-0000")

    def flush():
        nonlocal batch, chunk, skip
        if not skip:
            with l.part("entities-%04d" % chunk):
                bulk_entities(l, batch)
        batch = []
        chunk += 1
        skip = l.done("entities-%04d" % chunk)

    for r in rows(lei_zip):
        seen += 1
        if (r["Entity.EntityStatus"] == "ACTIVE" and r["Registration.RegistrationStatus"] == "ISSUED"
                and r["Entity.EntityCategory"] != "SOLE_PROPRIETOR") and not skip:
            hq, legal = r["Entity.HeadquartersAddress.Country"], r["Entity.LegalAddress.Country"]
            if hq:
                country, region, city = hq, r["Entity.HeadquartersAddress.Region"], r["Entity.HeadquartersAddress.City"]
            else:
                country, region, city = legal, r["Entity.LegalAddress.Region"], r["Entity.LegalAddress.City"]
            attrs = {"category": r["Entity.EntityCategory"], "legal_country": legal, "hq_country": hq,
                     "city": city, "region": region, "legal_form": r.get("Entity.LegalForm.EntityLegalFormCode")}
            batch.append((r["LEI"], r["Entity.LegalName"], "company", place(country, region), None, None, None, None,
                          {k: v for k, v in attrs.items() if v}))
        if seen % CHUNK == 0:
            flush()
    flush()

    if not l.done("links"):
        def links():
            for r in rows(rr_zip):
                kind = REL.get(r["Relationship.RelationshipType"])
                if kind and r["Relationship.RelationshipStatus"] == "ACTIVE":
                    yield kind, r["Relationship.StartNode.NodeID"], r["Relationship.EndNode.NodeID"]
        by_kind = {k: [] for k in REL.values()}
        for kind, a, b in links():
            by_kind[kind].append((a, b, None, None))
        with l.part("links"):
            for kind, lst in by_kind.items():
                got, dropped = replace_links(l, kind, lst)
                print("gleif %s: %d stored, %d dropped (end not stored)" % (kind, got, dropped), flush=True)
    l.finish()
    kg.cleanup("gleif")


if __name__ == "__main__":
    main()
