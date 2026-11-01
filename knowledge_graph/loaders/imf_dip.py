"""IMF Direct Investment Positions by counterpart economy (formerly CDIS): inward positions, investor to host."""
import json

import kg
from loaders._money_helpers import Countries, imf_place, sdmx_obs

URL = ("https://api.imf.org/external/sdmx/2.1/data/IMF.STA,DIP/*.*.INWD_D_NETLA_FALL_ALL.*.A")
IMF_ACCEPT = {"Accept": "application/json"}


def main():
    l = kg.Loader("imf_dip", name="Direct Investment Positions by Counterpart Economy (formerly CDIS)",
                  publisher="International Monetary Fund", url="https://data.imf.org/en/datasets/IMF.STA:DIP",
                  data_url="https://api.imf.org/external/sdmx/2.1/data/IMF.STA,DIP", kinds=["flows"],
                  about="Inward direct investment positions, net (liabilities less assets), all instruments, by immediate investor economy",
                  coverage="Reporting economies and mirror data, annual, 2009 on", access="open",
                  license="IMF Copyright, https://www.imf.org/external/terms.htm", found_by="survey")
    mid = l.measure("fdi_position_usd", "Direct investment position, inward, USD", "USD", "investment",
                    about="from = immediate investor economy, to = host economy (the reporter), year-end stock of inward direct investment, net liabilities less assets, all instruments, all entities. Reported data preferred over IMF mirror data derived from the investor's own report. Counterparts such as World or Europe are aggregates stored as imf: places, do not add them to countries")
    cs = Countries(l)
    d = kg.workdir("imf_dip")
    doc = json.load(open(kg.download(URL, d / "dip.json", headers=IMF_ACCEPT)))
    best = {}  # (host, investor, year) -> (is_reported, value)
    names = {}
    for dims, year, v, deriv in sdmx_obs(doc):
        host, investor = dims["COUNTRY"], dims["COUNTERPART_COUNTRY"]
        names[host[0]], names[investor[0]] = host[1], investor[1]
        rep = dims["DV_TYPE"][0] == "O"
        k = (host[0], investor[0], year)
        if k not in best or (rep and not best[k][0]):
            best[k] = (rep, v)
    del doc
    by_host = {}
    for (host, investor, year), (_, v) in best.items():
        by_host.setdefault(host, []).append((investor, year, v))
    for host, rows in sorted(by_host.items()):
        if l.done(host):
            continue
        with l.part(host):
            hp = imf_place(l, cs, host, names[host])
            for investor, year, v in rows:
                if investor != host:
                    l.flow(mid, year, imf_place(l, cs, investor, names[investor]), hp, None, v)
    l.conn.commit()
    cs.report()
    l.finish()
    kg.cleanup("imf_dip")


if __name__ == "__main__":
    main()
