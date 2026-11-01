"""World Bank What a Waste 2.0, country level: municipal solid waste generated, its composition, how it is treated, special wastes."""
import csv

import kg
from loaders._sector_helpers import num, Unmatched, iso3_place, waste_sector

PAGE = "https://datacatalog.worldbank.org/search/dataset/0039597/what-a-waste-global-database"
DATA = "https://datacatalogfiles.worldbank.org/ddh-published/0039597/DR0049199/country_level_data.csv"
CODEBOOK = "https://datacatalogfiles.worldbank.org/ddh-published/0039597/DR0049201/country_level_codebook.csv"
SPECIAL = {"agricultural": "agricultural", "construction_and_demolition": "construction-demolition",
           "e_waste": "e-waste", "hazardous": "hazardous", "industrial": "industrial", "medical": "medical"}
COMPOSITION = {"food_organic_waste": "food-organic", "glass": "glass", "metal": "metal", "other": "other-material",
               "paper_cardboard": "paper-cardboard", "plastic": "plastic", "rubber_leather": "rubber-leather",
               "wood": "wood", "yard_garden_green_waste": "yard-garden"}
TREATMENT = {"anaerobic_digestion": "anaerobic-digestion", "compost": "compost", "controlled_landfill": "controlled-landfill",
             "incineration": "incineration", "landfill_unspecified": "landfill-unspecified", "open_dump": "open-dump",
             "other": "other-treatment", "recycling": "recycling",
             "sanitary_landfill_landfill_gas_system": "sanitary-landfill", "unaccounted_for": "unaccounted",
             "waterways_marine": "waterways-marine"}


def main():
    l = kg.Loader("waste", name="World Bank What a Waste 2.0, country level",
                  publisher="World Bank", url=PAGE, data_url=DATA, kinds=["stats"],
                  about="Municipal solid waste generated, composition and treatment shares, and special wastes (e-waste, hazardous, medical and others) by country, each in the year the source gives for it",
                  coverage="~215 countries and areas, reference years mostly 2010 to 2016", access="open",
                  license="CC BY 4.0", found_by="survey")
    d = kg.workdir("waste")
    gen = l.measure("waste_generated_tonnes", "Waste generated", "tonnes", "waste", "Tonnes per year")
    pct = l.measure("waste_share_pct", "Share of municipal waste", "%", "waste", "Composition by material or treatment, percent of municipal solid waste")
    treated = l.measure("waste_treated_tonnes", "Waste treated", "tonnes", "waste",
                        "Treatment share times municipal solid waste generated, same country; computed at load")
    years = {}
    for r in csv.DictReader(open(kg.download(CODEBOOK, d / "codebook.csv"), encoding="utf-8-sig")):
        if r["year"].isdigit():
            years.setdefault((r["iso3c"], r["measurement"]), int(r["year"]))
    bad = Unmatched()
    for r in csv.DictReader(open(kg.download(DATA, d / "country.csv"), encoding="utf-8-sig")):
        iso3 = r["iso3c"]
        place = iso3_place(l, iso3)
        if not place:
            bad.add("%s %s" % (iso3, r["country_name"]))
            continue
        if l.done(iso3):
            continue

        def get(col):
            v = num(r[col])
            y = years.get((iso3, col))
            return (v, y) if v is not None and y else (None, None)

        with l.part(iso3):
            total, ty = get("total_msw_total_msw_generated_tons_year")
            if total is not None:
                l.stat(gen, ty, place, waste_sector(l, "msw"), total)
            for k, code in SPECIAL.items():
                v, y = get("special_waste_%s_waste_tons_year" % k if k != "e_waste" else "special_waste_e_waste_tons_year")
                if v is not None:
                    l.stat(gen, y, place, waste_sector(l, code), v)
            for k, code in COMPOSITION.items():
                v, y = get("composition_%s_percent" % k)
                if v is not None:
                    l.stat(pct, y, place, waste_sector(l, "composition-" + code), v)
            for k, code in TREATMENT.items():
                v, y = get("waste_treatment_%s_percent" % k)
                if v is not None:
                    l.stat(pct, y, place, waste_sector(l, "treatment-" + code), v)
                    if total is not None:
                        l.stat(treated, y, place, waste_sector(l, "treatment-" + code), total * v / 100)
    bad.report("waste")
    l.finish()
    kg.cleanup("waste")


if __name__ == "__main__":
    main()
