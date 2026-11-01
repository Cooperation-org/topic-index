"""IMF Portfolio Investment Positions by counterpart economy (formerly CPIS): holdings of securities, holder to issuer."""
import json

import kg
from loaders._money_helpers import Countries, imf_place, sdmx_obs

URL = "https://api.imf.org/external/sdmx/2.1/data/IMF.STA,PIP/*.A.P_TOTINV_P_USD.S1.S1.*.A"


def main():
    l = kg.Loader("imf_cpis", name="Portfolio Investment Positions by Counterpart Economy (formerly CPIS)",
                  publisher="International Monetary Fund", url="https://data.imf.org/en/datasets/IMF.STA:PIP",
                  data_url="https://api.imf.org/external/sdmx/2.1/data/IMF.STA,PIP", kinds=["flows"],
                  about="Cross-border holdings of equity and debt securities, all sectors, by economy of the issuer",
                  coverage="About 90 reporting economies, annual, 1997 on", access="open",
                  license="IMF Copyright, https://www.imf.org/external/terms.htm", found_by="survey")
    mid = l.measure("portfolio_position_usd", "Portfolio investment position, assets, USD", "USD", "investment",
                    about="from = holder economy (the reporter), to = economy of the issuer of the securities held, year-end stock of equity and debt securities at market value, all sectors. Only the holder's own assets are stored; liabilities rows are the same holdings seen from the issuer. Aggregates such as World are imf: places")
    cs = Countries(l)
    d = kg.workdir("imf_cpis")
    doc = json.load(open(kg.download(URL, d / "pip.json", headers={"Accept": "application/json"})))
    by_holder, names = {}, {}
    for dims, year, v, _ in sdmx_obs(doc):
        holder, issuer = dims["COUNTRY"], dims["COUNTERPART_COUNTRY"]
        names[holder[0]], names[issuer[0]] = holder[1], issuer[1]
        by_holder.setdefault(holder[0], {})[(issuer[0], year)] = v
    del doc
    for holder, rows in sorted(by_holder.items()):
        if l.done(holder):
            continue
        with l.part(holder):
            hp = imf_place(l, cs, holder, names[holder])
            for (issuer, year), v in rows.items():
                if issuer != holder:
                    l.flow(mid, year, hp, imf_place(l, cs, issuer, names[issuer]), None, v)
    cs.report()
    l.finish()
    kg.cleanup("imf_cpis")


if __name__ == "__main__":
    main()
