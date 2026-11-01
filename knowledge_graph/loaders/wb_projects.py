"""World Bank projects: financing by country and year, with borrower and implementing agencies as government entities."""
import kg
from loaders._money_helpers import Countries, bulk_entities, bulk_links, fetch

API = "https://search.worldbank.org/api/v2/projects"
FIELDS = "id,project_name,countrycode,countryname,totalcommamt,boardapprovaldate,closingdate,status,borrower,impagency,mjsector_namecode,lendinginstr,regionname,projectfinancialtype,url"
ROWS = 500


LEGACY_ISO2 = {"ZR": "COD", "TP": "TLS"}  # codes the API still uses for Zaire and East Timor


def money(s):
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


def main():
    l = kg.Loader("wb_projects", name="World Bank projects and operations", publisher="World Bank",
                  url="https://projects.worldbank.org/", data_url=API, kinds=["entities", "links"],
                  about="World Bank financed projects: country, commitment, approval and closing dates, borrower, implementing agency, major sector",
                  coverage="Projects approved since 1947, all borrower countries", access="open", license="CC BY 4.0", found_by="survey")
    cs = Countries(l)
    total = int(fetch("%s?format=json&rows=1&fl=id" % API)["total"])
    for offset in range(0, total, ROWS):
        part = "os%d" % offset
        if l.done(part):
            continue
        projects = fetch("%s?format=json&rows=%d&os=%d&fl=%s&srt=id" % (API, ROWS, offset, FIELDS))["projects"]
        with l.part(part):
            proj, agencies, rows = [], {}, []
            for p in projects.values():
                places = [x for x in (cs.get(iso3=LEGACY_ISO2.get(c), iso2=c, key=c) for c in p.get("countrycode", [])) if x]
                if not places:
                    continue
                sector = (p.get("mjsector_namecode") or [{}])[0]
                sid = l.sector("wb_sector", sector["code"], sector["name"]) if sector.get("code") else None
                amount = money(p.get("totalcommamt"))
                year = (p.get("boardapprovaldate") or "")[:4]
                attrs = {k: v for k, v in {
                    "lending_instrument": p.get("lendinginstr"), "status": p.get("status"), "approved": (p.get("boardapprovaldate") or "")[:10],
                    "closing": p.get("closingdate"), "borrower": p.get("borrower"), "implementing_agency": p.get("impagency"),
                    "financing": p.get("projectfinancialtype"), "region": p.get("regionname"), "commitment_usd": amount,
                    "countries": len(places)}.items() if v}
                proj.append((p["id"], p["project_name"], "project", places[0], sid, attrs, p, places, amount, year))
                countrynames = {n.lower() for n in p.get("countryname", [])}
                for role, name in (("implements", p.get("impagency")), ("borrows_for", p.get("borrower"))):
                    if name and name.strip().lower() not in countrynames:
                        agencies[(name.strip(), places[0])] = (role, p["id"])
            ids = bulk_entities(l, [(e, n, k, pl, s, a) for e, n, k, pl, s, a, *_ in proj])
            gov = {}
            for (name, place), (role, pid) in agencies.items():
                gov["agency|%d|%s" % (place, name.lower())] = (name, place)
            gids = bulk_entities(l, [(e, n, "government", pl, None, None) for e, (n, pl) in gov.items()])
            for e, n, k, pl, s, a, p, places, amount, year in proj:
                for pl2 in places:
                    rows.append(("financed_in", ids[e], None, pl2, s, int(year) if year.isdigit() else None,
                                 amount / len(places) if amount is not None else None, "USD", {"project": e}))
                for role, name in (("implements", p.get("impagency")), ("borrows_for", p.get("borrower"))):
                    g = gids.get("agency|%d|%s" % (places[0], name.strip().lower())) if name else None
                    if g:
                        rows.append((role, g, ids[e], None, None, int(year) if year.isdigit() else None, None, None, None))
            bulk_links(l, rows)
    cs.report()
    l.finish()


if __name__ == "__main__":
    main()
