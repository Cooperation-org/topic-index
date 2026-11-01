"""Kenya National Bureau of Statistics, Gross County Product 2025 report: value added by economic activity for all 47 counties, 2022 to 2024."""
import re

import kg
from loaders._sector_helpers import num, admin_lookup, norm_name, download_via_intermediate, Unmatched

PAGE = "https://www.knbs.or.ke/reports/gross-county-product-2024/"
PDF = "https://www.knbs.or.ke/wp-content/uploads/2025/12/2025-Gross-County-Product.pdf"
# the server sends only its own certificate; these are its issuer and that issuer's cross-signed root, from the CA (Let's Encrypt)
CERTS = ["https://letsencrypt.org/certs/gen-y/int-ye2.pem", "https://letsencrypt.org/certs/gen-y/root-ye-by-x2.pem"]
ANNEX_PAGES = range(51, 58)  # Annexes I-III, each across two pages
# column order of Annexes I-III after the county name, ISIC Rev.4 sections; the last two are the financial services adjustment and the total
ISIC = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "S"]
NAMES = {"A": "Agriculture, forestry and fishing", "B": "Mining and quarrying", "C": "Manufacturing",
         "D": "Electricity supply", "E": "Water supply; sewerage, waste management", "F": "Construction",
         "G": "Wholesale and retail trade; repair of motor vehicles", "H": "Transportation and storage",
         "I": "Accommodation and food service", "J": "Information and communication",
         "K": "Financial and insurance", "L": "Real estate", "M": "Professional, scientific and technical",
         "N": "Administrative and support services", "O": "Public administration and defence",
         "P": "Education", "Q": "Human health and social work", "S": "Other service activities"}
TOLERANCE = 0.005  # the report's own components must add up to its county total


def main():
    import pdfplumber
    l = kg.Loader("knbs_gcp", name="Kenya Gross County Product by economic activity",
                  publisher="Kenya National Bureau of Statistics", url=PAGE, data_url=PDF, kinds=["stats"],
                  about="County value added by ISIC section in Kenya shillings, parsed from Annexes I-III of the GCP 2025 report; county-years whose components do not add up to the county total are left out",
                  coverage="47 counties, 2022 to 2024 (2024 provisional)", access="open", license="KNBS publication", found_by="survey")
    d = kg.workdir("knbs_gcp")
    path = download_via_intermediate(PDF, d / "gcp.pdf", CERTS)
    va = l.measure("value_added_kes", "Value added", "KES", "output", "Value added at current prices in Kenya shillings, by ISIC section")
    gcp = l.measure("gcp_kes", "Gross county product", "KES", "output", "Gross county product at current prices in Kenya shillings")
    counties = admin_lookup(l, "KE")
    counties.update({norm_name("Nairobi City"): counties[norm_name("Nairobi")]})
    total = l.sector("isic", "TOTAL", "Total")
    fisim = l.sector("isic", "FISIM", "Financial services indirectly measured", total)
    bad, rejected, year = Unmatched(), [], None
    with pdfplumber.open(path) as pdf:
        for i in ANNEX_PAGES:
            page = pdf.pages[i]
            m = re.search(r"Current Prices, (\d{4})", page.extract_text() or "")
            year = int(m.group(1)) if m else year
            for table in page.extract_tables():
                if len(table) < 5 or len(table[0]) != 21:
                    continue
                for row in table:
                    name = (row[0] or "").replace("\n", "").strip()
                    vals = [num(c.replace("(", "-").replace(")", "")) if c else None for c in row[1:]]
                    if not re.fullmatch(r"[A-Z][A-Z’' /\-]+", name) or None in vals or name == "COUNTY":
                        continue
                    place = counties.get(norm_name(name.replace("/", " ")))
                    if not place:
                        bad.add(name)
                        continue
                    if abs(sum(vals[:-1]) - vals[-1]) > TOLERANCE * abs(vals[-1]):
                        rejected.append("%s %s" % (name, year))
                        continue
                    part = "%s:%s" % (year, name)
                    if l.done(part):
                        continue
                    with l.part(part):
                        for code, v in zip(ISIC, vals):
                            l.stat(va, year, place, l.sector("isic", code, NAMES[code], total), v * 1e6)
                        l.stat(va, year, place, fisim, vals[-2] * 1e6)
                        l.stat(gcp, year, place, total, vals[-1] * 1e6)
    bad.report("knbs_gcp")
    if rejected:
        print("knbs_gcp  left out, components do not add to total: %s" % rejected, flush=True)
    l.finish(note=("left out, components do not add to total: %s" % ", ".join(rejected)) if rejected else None)
    kg.cleanup("knbs_gcp")


if __name__ == "__main__":
    main()
