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


class Countries:
    """Resolve a source's country identifiers to place ids; misses are counted by key."""

    def __init__(self, loader):
        self.l = loader
        self.misses = {}

    def get(self, iso3=None, iso2=None, m49=None, name=None, key=None):
        l = self.l
        pid = (iso3 and l.country(iso3=iso3)) or (iso2 and l.country(iso2=iso2)) \
            or (m49 is not None and l.country(m49=m49)) or (name and l.country(name=name))
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
