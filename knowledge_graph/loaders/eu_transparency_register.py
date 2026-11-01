"""EU Transparency Register: organizations that lobby the EU institutions, with category, country, interests, spending.
People are stored as numbers only (full-time equivalents and Parliament pass holders). Client lists are organization names."""
import re
import xml.etree.ElementTree as ET

import kg
from loaders._entity_helpers import Names, bulk_entities

URL = "https://transparency-register.europa.eu/odplastorganisationxml_en"
BAD_REF = re.compile(r"&#(?:x([0-9a-fA-F]+)|(\d+));")


def fix_ref(m):
    c = int(m.group(1), 16) if m.group(1) else int(m.group(2))
    ok = c in (9, 10, 13) or (c >= 32 and c not in (0xFFFE, 0xFFFF) and not 0xD800 <= c <= 0xDFFF)
    return m.group(0) if ok else " "


class Cleaned:
    """The export is XML 1.1 and carries character references that XML 1.0 parsers reject; blank them while reading."""

    def __init__(self, path):
        self.f = open(path, encoding="utf-8", errors="replace")
        self.buf = ""

    def read(self, n):
        while len(self.buf) < n:
            line = self.f.readline()
            if not line:
                break
            self.buf += BAD_REF.sub(fix_ref, line)
        out, self.buf = self.buf[:n], self.buf[n:]
        return out.encode("utf-8")


def text(el, path):
    x = el.find(path)
    return x.text.strip() if x is not None and x.text and x.text.strip() else None


def number(el, path):
    t = text(el, path)
    try:
        return float(t) if t is not None else None
    except ValueError:
        return None


def main():
    l = kg.Loader("eu_transparency_register", name="EU Transparency Register", publisher="European Commission and European Parliament",
                  url="https://transparency-register.europa.eu/", data_url=URL, kinds=["entities"],
                  about="Organizations registered to lobby the EU institutions: category, head office country, policy interests, annual lobbying cost, staff FTE",
                  coverage="EU, current register", access="open", license="CC BY 4.0", found_by="core")
    if l.done("register"):
        return l.finish()
    names = Names(l)
    path = kg.download(URL, kg.workdir("eu_transparency_register") / "register.xml")
    rows = []
    for _, el in ET.iterparse(Cleaned(path)):
        if el.tag != "interestRepresentative":
            continue
        closed = el.find("financialData/closedYear")
        clients = []
        if closed is not None:
            clients = [t for t in (c.findtext("name") for c in closed.findall("clients/client")) if t][:50]
        interests = [i.findtext("name") for i in el.findall("interests/interest") if i.findtext("name")]
        year = text(closed, "endDate")[:4] if closed is not None and text(closed, "endDate") else None
        attrs = {"acronym": text(el, "acronym"), "category": text(el, "registrationCategory"), "entity_form": text(el, "entityForm"),
                 "city": text(el, "headOffice/city"), "interests": interests or None, "year": year,
                 "lobbying_cost_eur_min": number(closed, "costs/range/min") if closed is not None else None,
                 "lobbying_cost_eur_max": number(closed, "costs/range/max") if closed is not None else None,
                 "budget_eur": number(closed, "totalBudget/absoluteCost") if closed is not None else None,
                 "people_fte": number(el, "members/membersFTE"), "people": number(el, "members/members"),
                 "ep_pass_holders": number(el, "EPAccreditedNumber"), "clients": clients or None,
                 "represents": text(el, "interestRepresented"), "registered": (text(el, "registrationDate") or "")[:10] or None}
        rows.append((text(el, "identificationCode"), text(el, "name/originalName") or text(el, "acronym") or "Unnamed", "lobbyist",
                     names.country(text(el, "headOffice/country")), None, None, None, text(el, "webSiteURL"),
                     {k: v for k, v in attrs.items() if v is not None}))
        el.clear()
    names.report()
    with l.part("register"):
        bulk_entities(l, rows)
    l.finish()
    kg.cleanup("eu_transparency_register")


if __name__ == "__main__":
    main()
