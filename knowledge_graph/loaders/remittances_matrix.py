"""World Bank KNOMAD bilateral remittance matrix, estimated from migrant stocks and incomes, via the Data360 API."""
import kg
from loaders._money_helpers import Countries, fetch

API = "https://data360api.worldbank.org/data360/data?DATABASE_ID=WB_KNOMAD&INDICATOR=WB_KNOMAD_BRE&skip=%d"
PAGE = 1000


def main():
    l = kg.Loader("remittances_matrix", name="Bilateral remittance estimates (KNOMAD)", publisher="World Bank KNOMAD",
                  url="https://www.knomad.org/data/remittances", data_url="https://data360.worldbank.org/en/dataset/WB_KNOMAD",
                  kinds=["flows"], about="Estimated remittances between each pair of countries, from migrant stocks, host country incomes and origin country incomes",
                  coverage="Sending and receiving countries, latest estimate year", access="open", license="CC BY 4.0", found_by="survey")
    mid = l.measure("remittances_usd", "Bilateral remittances, USD", "USD", "remittances",
                    about="from = sending country (where migrants earn, the host), to = receiving country (where migrants come from), estimated annual remittances in current USD, modeled from migrant stocks and incomes, not reported by banks. World total rows are skipped")
    cs = Countries(l)
    skip = 0
    while True:
        if l.done("skip%d" % skip):
            skip += PAGE
            if skip > 12000:
                break
            continue
        doc = fetch(API % skip)
        with l.part("skip%d" % skip):
            for r in doc["value"]:
                if r["OBS_VALUE"] in (None, "", "NaN") or r["UNIT_MEASURE"] != "USD_CUR":
                    continue
                dest = r["COMP_BREAKDOWN_1"].replace("WB_KNOMAD_", "")
                if dest == "WLD":
                    continue
                fp, tp = cs.get(iso3=r["REF_AREA"]), cs.get(iso3=dest)
                if fp and tp:
                    l.flow(mid, int(r["TIME_PERIOD"]), fp, tp, None, float(r["OBS_VALUE"]) * 1e6 * 10 ** int(r["UNIT_MULT"] or 0))
        skip += PAGE
        if skip >= doc["count"]:
            break
    cs.report()
    l.finish()


if __name__ == "__main__":
    main()
