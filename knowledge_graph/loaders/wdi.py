"""World Bank World Development Indicators: country stats, 1990 to latest, via the open v2 API."""
import kg
from loaders._money_helpers import Countries, fetch

API = "https://api.worldbank.org/v2/"
# code: (slug, name, unit, family)
INDICATORS = {
    "NY.GDP.MKTP.CD": ("gdp_usd", "GDP", "USD", "output"),
    "SP.POP.TOTL": ("population", "Population, total", "people", "demography"),
    "NV.AGR.TOTL.CD": ("va_agriculture_usd", "Agriculture, forestry, fishing value added", "USD", "output"),
    "NV.IND.TOTL.CD": ("va_industry_usd", "Industry (incl. construction) value added", "USD", "output"),
    "NV.IND.MANF.CD": ("va_manufacturing_usd", "Manufacturing value added", "USD", "output"),
    "NV.SRV.TOTL.CD": ("va_services_usd", "Services value added", "USD", "output"),
    "NE.EXP.GNFS.CD": ("exports_goods_services_usd", "Exports of goods and services", "USD", "trade"),
    "NE.IMP.GNFS.CD": ("imports_goods_services_usd", "Imports of goods and services", "USD", "trade"),
    "BX.KLT.DINV.CD.WD": ("fdi_inflow_usd", "Foreign direct investment, net inflows", "USD", "investment"),
    "BM.KLT.DINV.CD.WD": ("fdi_outflow_usd", "Foreign direct investment, net outflows", "USD", "investment"),
    "BX.TRF.PWKR.CD.DT": ("remittances_received_usd", "Personal remittances, received", "USD", "remittances"),
    "BM.TRF.PWKR.CD.DT": ("remittances_paid_usd", "Personal remittances, paid", "USD", "remittances"),
    "DT.ODA.ODAT.CD": ("aid_received_net_usd", "Net official development assistance and official aid received", "USD", "aid"),
    "MS.MIL.XPND.CD": ("military_spending_usd", "Military expenditure", "USD", "military"),
    "EG.USE.PCAP.KG.OE": ("energy_use_kg_oe_per_capita", "Energy use, kg of oil equivalent per capita", "kg_oe", "energy"),
    "GC.TAX.TOTL.GD.ZS": ("tax_revenue_pct_gdp", "Tax revenue, % of GDP", "percent", "fiscal"),
    "EG.FEC.RNEW.ZS": ("renewable_share_final_energy_pct", "Renewable energy consumption, % of total final energy consumption", "percent", "energy"),
}


def main():
    l = kg.Loader("wdi", name="World Development Indicators", publisher="World Bank",
                  url="https://databank.worldbank.org/source/world-development-indicators",
                  data_url=API, kinds=["stats"],
                  about="Country indicators: GDP, population, sector value added, trade, FDI, remittances, aid, military, energy, tax",
                  coverage="Countries and aggregates, 1990 to latest", access="open", license="CC BY 4.0", found_by="survey")
    cs = Countries(l)
    world = l.place("world")
    # indicator rows carry the 2-letter code when countryiso3code is blank (income groups)
    meta = fetch(API + "country?format=json&per_page=400")[1]
    iso3_of = {c["iso2Code"]: c["id"] for c in meta}
    names = {c["id"]: c["name"] for c in meta}
    for code, (slug, name, unit, family) in INDICATORS.items():
        if l.done(code):
            continue
        mid = l.measure(slug, name, unit, family,
                        about="World Bank indicator %s: value for the country (stat, no from/to)" % code)
        with l.part(code):
            page = 1
            while True:
                meta, rows = fetch("%scountry/all/indicator/%s?format=json&per_page=20000&date=1990:2030&page=%d"
                                   % (API, code, page))
                for r in rows or []:
                    if r["value"] is None:
                        continue
                    iso3 = r["countryiso3code"] or iso3_of.get(r["country"]["id"]) or r["country"]["id"]
                    pid = world if iso3 == "WLD" else cs.get(iso3=iso3, key=iso3)
                    if not pid and iso3.isalpha() and len(iso3) == 3:
                        # aggregate such as EUU or SAS
                        pid = l.other_place("agg:" + iso3, names.get(iso3, r["country"]["value"]))
                    if pid:
                        l.stat(mid, int(r["date"]), pid, None, r["value"])
                if page >= meta["pages"]:
                    break
                page += 1
    cs.report()
    l.finish("aggregates stored as agg: places")


if __name__ == "__main__":
    main()
