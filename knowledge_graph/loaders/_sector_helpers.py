"""Shared by the sector size loaders."""
import kg


def num(x):
    """Float from a source cell, None when blank or not a number."""
    try:
        v = float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def country_or_other(l, iso3=None, m49=None, name=None, prefix="src"):
    """Country place id; a source's own entity (former state, aggregate) becomes kind 'other'."""
    pid = l.country(iso3=iso3) if iso3 else None
    if not pid and m49 is not None:
        pid = l.country(m49=m49)
    if not pid and name:
        pid = l.country(name=name)
    if not pid and (iso3 or m49 is not None) and name:
        pid = l.other_place("%s:%s" % (prefix, iso3 or m49), name)
    return pid


class Unmatched(set):
    def report(self, slug):
        if self:
            print("%s  unmatched places: %s" % (slug, sorted(self)[:40]), flush=True)


def fao_place(l, code, m49, name):
    """FAOSTAT area to a place id. Regional aggregates (codes 5000 and up) return None; FAO's own non-ISO areas become kind 'other'."""
    if int(code) >= 5000:
        return None
    m = str(m49).lstrip("'")
    return l.country(m49=int(m)) if m.isdigit() and l.country(m49=int(m)) else l.other_place("fao:%s" % code, name)


def post_json(url, body, timeout=120, tries=3):
    """POST a JSON body, return the response text. Retries a few times."""
    import json
    import time
    import urllib.request
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
                "User-Agent": kg.UA, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                try:
                    return raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    return raw.decode("latin-1")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


# Electricity sources, one tree shared by IRENA, Ember and OWID. code -> (name, parent)
ENERGY = {
    "total": ("Total electricity", None),
    "renewable": ("Renewable", "total"),
    "non-renewable": ("Non-renewable", "total"),
    "hydro": ("Hydropower", "renewable"),
    "hydro-pure": ("Pure hydropower", "hydro"),
    "hydro-mixed": ("Mixed hydropower", "hydro"),
    "solar": ("Solar", "renewable"),
    "solar-pv": ("Solar photovoltaic", "solar"),
    "solar-thermal": ("Solar thermal", "solar"),
    "wind": ("Wind", "renewable"),
    "wind-onshore": ("Onshore wind", "wind"),
    "wind-offshore": ("Offshore wind", "wind"),
    "bioenergy": ("Bioenergy", "renewable"),
    "solid-biofuels": ("Solid biofuels", "bioenergy"),
    "gas-biofuels": ("Biogas", "bioenergy"),
    "liquid-biofuels": ("Liquid biofuels", "bioenergy"),
    "renewable-waste": ("Renewable municipal waste", "bioenergy"),
    "geothermal": ("Geothermal", "renewable"),
    "marine": ("Marine", "renewable"),
    "other-renewables": ("Other renewables", "renewable"),
    "coal": ("Coal", "non-renewable"),
    "gas": ("Natural gas", "non-renewable"),
    "oil": ("Oil", "non-renewable"),
    "other-fossil": ("Other fossil", "non-renewable"),
    "oil-shale": ("Oil shale and oil sands", "non-renewable"),
    "peat": ("Peat", "non-renewable"),
    "nuclear": ("Nuclear", "non-renewable"),
    "pumped-storage": ("Pumped hydro storage", "non-renewable"),
    "non-renewable-waste": ("Non-renewable waste", "non-renewable"),
    "other-non-renewable": ("Other non-renewable", "non-renewable"),
}


def energy_sector(l, code):
    """Sector id in scheme energy_tech, parents created first."""
    name, parent = ENERGY[code]
    return l.sector("energy_tech", code, name, energy_sector(l, parent) if parent else None)


def iso3_place(l, iso3, name=None):
    """Country by ISO3; Kosovo, which has no ISO code, becomes its own place XKX."""
    return l.country(iso3=iso3) or (l.other_place("XKX", "Kosovo") if iso3 in ("XKX", "KOS") else None)


WASTE_SPECIAL = ("agricultural", "construction-demolition", "e-waste", "hazardous", "industrial", "medical")


def waste_sector(l, code):
    """Sector id in scheme waste: msw (composition, treatment) and special wastes. Names come from the code."""
    if code in ("msw", "special"):
        parent = None
    elif code in ("composition", "treatment"):
        parent = "msw"
    elif code.startswith(("composition-", "treatment-")):
        parent = code.split("-", 1)[0]
    elif code in WASTE_SPECIAL:
        parent = "special"
    else:
        parent = None
    names = {"msw": "Municipal solid waste", "special": "Special waste", "e-waste": "Electronic waste",
             "composition": "Composition", "treatment": "Treatment",
             "composition-food-organic": "Food and organic", "composition-paper-cardboard": "Paper and cardboard",
             "composition-rubber-leather": "Rubber and leather", "composition-yard-garden": "Yard and garden",
             "composition-other-material": "Other material", "construction-demolition": "Construction and demolition",
             "treatment-landfill-unspecified": "Landfill, unspecified", "treatment-sanitary-landfill": "Sanitary landfill with gas system",
             "treatment-unaccounted": "Unaccounted for", "treatment-waterways-marine": "Waterways and marine",
             "treatment-other-treatment": "Other treatment"}
    name = names.get(code) or code.split("-", 1)[-1].replace("-", " ").capitalize()
    return l.sector("waste", code, name, waste_sector(l, parent) if parent else None)


def norm_name(s):
    """Name for matching places: lower case, letters and digits only, without county/state/province words."""
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(county|city|state|province|region|division|area)\b", " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


def admin_lookup(l, iso2, kind="admin1"):
    """normalized name or alt name -> place id, for the first or second level divisions of one country."""
    l.cur.execute("SELECT id, name, alt_names FROM kg.places WHERE iso2 = %s AND kind = %s ORDER BY id", (iso2, kind))
    out = {}
    for id_, name, alts in l.cur.fetchall():
        for n in [name] + list(alts or []):
            out.setdefault(norm_name(n), id_)
        out[norm_name(name)] = id_
    return out


def download_via_intermediate(url, dest, cert_urls):
    """Download from a server that does not send its intermediate certificates. The missing certificates are
    fetched over verified HTTPS from the CA's own site and added to the trust store for this one request;
    the chain still has to end at a root already trusted by the system."""
    import shutil
    import ssl
    import urllib.request
    from pathlib import Path
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size:
        return dest
    ctx = ssl.create_default_context()
    for u in cert_urls:
        ctx.load_verify_locations(cadata=urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": kg.UA}), timeout=60).read().decode())
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=600, context=ctx) as r, open(tmp, "wb") as out:
        shutil.copyfileobj(r, out, 1 << 20)
    tmp.rename(dest)
    return dest
