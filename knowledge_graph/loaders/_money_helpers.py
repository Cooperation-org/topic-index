"""Shared by the money and influence loaders: retrying fetches and country lookup with misses counted."""
import json
import time
import urllib.error
import urllib.request

import kg


def fetch(url, headers=None, tries=4, timeout=300, raw=False):
    """GET with retries and backoff; JSON by default. A 429 waits out the rate window and does not use up a try."""
    err, i, waits = None, 0, 0
    while i < tries:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": kg.UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            return body if raw else json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404):
                raise
            err = e
            if e.code == 429 and waits < 15:
                waits += 1
                time.sleep(65)
                continue
        except Exception as e:  # network, timeout, bad json
            err = e
        time.sleep(2 ** i * 3)
        i += 1
    raise err


# country names that sources spell differently from the ISO names in kg.places
NAME_ALIASES = {
    "vietnam": "VNM", "viet nam": "VNM", "congo, democratic republic of": "COD", "congo, dem. rep.": "COD",
    "democratic republic of congo": "COD", "congo, republic of": "COG", "congo, rep.": "COG", "turkey": "TUR",
    "turkiye": "TUR", "yemen, republic of": "YEM", "yemen, rep.": "YEM", "west bank and gaza": "PSE", "palestine": "PSE",
    "somalia, federal republic of": "SOM", "st. kitts and nevis": "KNA", "st. lucia": "LCA",
    "st. vincent and the grenadines": "VCT", "korea, republic of": "KOR", "korea, rep.": "KOR", "south korea": "KOR",
    "korea, democratic people's republic of": "PRK", "north korea": "PRK", "iran, islamic republic of": "IRN",
    "iran": "IRN", "russia": "RUS", "russian federation": "RUS", "syria": "SYR", "laos": "LAO", "bolivia": "BOL",
    "venezuela": "VEN", "venezuela, rb": "VEN", "tanzania": "TZA", "moldova": "MDA", "brunei": "BRN",
    "cote d'ivoire": "CIV", "cabo verde": "CPV", "cape verde": "CPV", "egypt, arab rep.": "EGY", "egypt": "EGY",
    "gambia, the": "GMB", "gambia": "GMB", "bahamas, the": "BHS", "micronesia, federated states of": "FSM",
    "micronesia, fed. sts.": "FSM", "kyrgyz republic": "KGZ", "slovak republic": "SVK", "lao pdr": "LAO",
    "czech republic": "CZE", "czechia": "CZE", "north macedonia": "MKD", "macedonia, fyr": "MKD", "swaziland": "SWZ",
    "eswatini": "SWZ", "myanmar": "MMR", "burma": "MMR", "hong kong sar, china": "HKG", "macao sar, china": "MAC",
    "taiwan": "TWN", "taiwan, china": "TWN", "timor-leste": "TLS", "east timor": "TLS", "united states": "USA",
    "united kingdom": "GBR", "netherlands": "NLD", "bosnia-herzegovina": "BIH", "bosnia and herzegovina": "BIH",
    "holy see": "VAT", "vatican": "VAT", "kosovo": "XKX", "curacao": "CUW", "sint maarten (dutch part)": "SXM",
    "st. martin (french part)": "MAF", "virgin islands (u.s.)": "VIR", "british virgin islands": "VGB",
    "china, people's republic of": "CHN", "china": "CHN", "hong kong": "HKG", "macao": "MAC",
}


class Countries:
    """Resolve a source's country identifiers to place ids; misses are counted by key."""

    def __init__(self, loader):
        self.l = loader
        self.misses = {}

    def get(self, iso3=None, iso2=None, m49=None, name=None, key=None):
        l = self.l
        pid = (iso3 and l.country(iso3=iso3)) or (iso2 and l.country(iso2=iso2)) \
            or (m49 is not None and l.country(m49=m49)) \
            or (name and (l.country(iso3=NAME_ALIASES.get(name.lower())) or l.country(name=name)))
        if not pid:
            k = key or iso3 or iso2 or m49 or name
            self.misses[k] = self.misses.get(k, 0) + 1
        return pid

    def report(self):
        if self.misses:
            top = sorted(self.misses.items(), key=lambda x: -x[1])[:25]
            print("unmatched:", ", ".join("%s(%d)" % kv for kv in top), flush=True)


def sdmx_obs(doc):
    """Observations of an SDMX-JSON data message as (dims, year, value, derivation).
    dims maps each series dimension id to (code, name); derivation is the observation's DERIVATION_TYPE code."""
    s = doc["structure"]
    sdims = s["dimensions"]["series"]
    times = s["dimensions"]["observation"][0]["values"]
    oattrs = s["attributes"].get("observation", [])
    dpos = next((i for i, a in enumerate(oattrs) if a["id"] == "DERIVATION_TYPE"), None)
    for key, ser in doc["dataSets"][0]["series"].items():
        idx = [int(i) for i in key.split(":")]
        dims = {d["id"]: (d["values"][i]["id"], d["values"][i]["name"]) for d, i in zip(sdims, idx)}
        for t, o in ser["observations"].items():
            if o[0] is None:
                continue
            deriv = None
            if dpos is not None and o[1 + dpos] is not None:
                deriv = oattrs[dpos]["values"][o[1 + dpos]]["id"]
            yield dims, int(times[int(t)]["id"][:4]), float(o[0]), deriv


def imf_place(l, cs, code, name):
    """An IMF area code: a country by ISO3, otherwise the source's aggregate or unallocated bucket."""
    return cs.get(iso3=code) or l.other_place("imf:" + code, name)


def sdmx_codelist(xml_bytes, codelist_id):
    """{code: (name, parent)} for one codelist in an SDMX-ML structure message (English names)."""
    import xml.etree.ElementTree as ET
    out = {}
    ns = "{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure}"
    for cl in ET.fromstring(xml_bytes).iter(ns + "Codelist"):
        if cl.get("id") != codelist_id:
            continue
        for c in cl.iter(ns + "Code"):
            name = next((n.text for n in c.findall("{*}Name") if n.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"), c.get("id"))
            ref = c.find("{*}Parent/{*}Ref")
            out[c.get("id")] = (name, ref.get("id") if ref is not None else None)
    return out


def bulk_entities(l, rows):
    """Upsert entities in one round trip: rows of (ext_id, name, kind, place_id, sector_id, attrs dict). Returns {ext_id: id}."""
    import psycopg
    l.cur.executemany("""INSERT INTO kg.entities (source_id, ext_id, name, kind, place_id, sector_id, attrs)
                         VALUES (%s, %s, %s, %s, %s, %s, %s)
                         ON CONFLICT (source_id, ext_id) DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind,
                           place_id = EXCLUDED.place_id, sector_id = EXCLUDED.sector_id, attrs = EXCLUDED.attrs""",
                      [(l.source_id, e, n, k, p, s, psycopg.types.json.Jsonb(a) if a else None) for e, n, k, p, s, a in rows])
    ids = [e for e, *_ in rows]
    l.cur.execute("SELECT ext_id, id FROM kg.entities WHERE source_id = %s AND ext_id = ANY(%s)", (l.source_id, ids))
    l.written += len(rows)
    return dict(l.cur.fetchall())


def bulk_links(l, rows):
    """COPY links: rows of (kind, from_entity, to_entity, to_place, sector_id, year, value, unit, attrs dict)."""
    import psycopg
    with l.cur.copy("""COPY kg.links (source_id, kind, from_entity, to_entity, to_place, sector_id, year, value, unit, attrs)
                       FROM STDIN""") as c:
        for k, f, te, tp, s, y, v, u, a in rows:
            c.write_row((l.source_id, k, f, te, tp, s, y, v, u, psycopg.types.json.Jsonb(a) if a else None))
    l.written += len(rows)
