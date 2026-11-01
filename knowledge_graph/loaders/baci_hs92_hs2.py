"""CEPII BACI bilateral goods trade, HS 1992 edition summed to 2-digit chapters, one part per year, for long trends."""
import kg
from loaders import _trade_helpers as h


def main():
    l = kg.Loader("baci_hs92_hs2", name="BACI bilateral goods trade, HS 1992, summed to 2-digit chapters",
                  publisher="CEPII", url=h.BACI_PAGE, data_url=h.BACI % "HS92", kinds=["flows"],
                  about="Goods trade by exporter, importer and HS chapter, 1995 on; 6-digit products are summed to chapter, not stored",
                  coverage="About 200 countries, 1995-2024, 96 chapters", access="open", license="Etalab 2.0", found_by="core")
    d = kg.workdir("baci_hs92_hs2")
    z = kg.download(h.BACI % "HS92", d / "baci.zip")
    places, sectors, m = h.baci_places(l, z), h.hs_ids(l), h.goods_measure(l)
    l.conn.commit()
    unknown = set()
    for year, member in sorted(h.baci_years(z).items()):
        if l.done(str(year)):
            continue
        total = {}
        for i, j, k, v in h.baci_rows(z, member):
            key = (i, j, k[:2])
            total[key] = total.get(key, 0.0) + v
        h.clear_year(l, year)
        with l.part(str(year)):
            for (i, j, ch), v in total.items():
                if ch in sectors:
                    l.flow(m, year, places[i], places[j], sectors[ch], v * 1000)
                else:
                    unknown.add(ch)
    if unknown:
        print("chapters not in the hs tree, skipped:", sorted(unknown))
    l.finish("chapters not in the HS 2022 tree skipped: %s" % ",".join(sorted(unknown)) if unknown else None)
    kg.cleanup("baci_hs92_hs2")


if __name__ == "__main__":
    main()
