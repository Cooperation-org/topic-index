"""CEPII BACI bilateral goods trade, HS 2022 edition at 6-digit, one part per year."""
import kg
from loaders import _trade_helpers as h


def main():
    l = kg.Loader("baci_hs22", name="BACI bilateral goods trade, HS 2022, 6-digit",
                  publisher="CEPII", url=h.BACI_PAGE, data_url=h.BACI % "HS22", kinds=["flows"],
                  about="Goods trade by exporter, importer and 6-digit product; values reconciled across both countries' reports, in USD",
                  coverage="About 200 countries, 2022-2024, 5,600 products", access="open", license="Etalab 2.0", found_by="core")
    d = kg.workdir("baci_hs22")
    z = kg.download(h.BACI % "HS22", d / "baci.zip")
    places, sectors, m = h.baci_places(l, z), h.hs_ids(l), h.goods_measure(l)
    l.conn.commit()
    for year, member in sorted(h.baci_years(z).items()):
        if l.done(str(year)):
            continue
        h.clear_year(l, year)
        with l.part(str(year)):
            for i, j, k, v in h.baci_rows(z, member):
                l.flow(m, year, places[i], places[j], sectors[k], v * 1000)
    l.finish()
    kg.cleanup("baci_hs22")


if __name__ == "__main__":
    main()
