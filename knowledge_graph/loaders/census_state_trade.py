"""US Census international trade by state: each state, partner country, 4-digit HS, annual. Needs a free key in CENSUS_API_KEY."""
import json
import os
import urllib.error
import urllib.request

import kg
from loaders import _trade_helpers as h

API = "https://api.census.gov/data/timeseries/intltrade/%s/statehs"
COUNTRIES = "https://www.census.gov/foreign-trade/schedules/c/country.txt"
# flow, state side is 'from' for exports and 'to' for imports; value column is year-to-date through December
FLOWS = (("exports", "E_COMMODITY", "ALL_VAL_YR", "state_goods_exports_usd", "Goods exported by a US state to a partner country, USD, by state of origin of movement",
          "from = US state where the goods began their trip to the port of export, to = destination country, annual total, 4-digit HS, FAS value."),
         ("imports", "I_COMMODITY", "GEN_VAL_YR", "state_goods_imports_usd", "Goods imported by a US state from a partner country, USD, by state of destination",
          "from = country of origin, to = US state of final destination, annual total, 4-digit HS, general imports customs value."))
YEARS = 5


def get(url, key):
    try:
        with urllib.request.urlopen(urllib.request.Request(url + "&key=" + key, headers={"User-Agent": kg.UA}), timeout=300) as r:
            body = r.read()
            return json.loads(body) if body else []
    except urllib.error.HTTPError as e:
        if e.code in (204, 404):
            return []
        raise


def census_places(l, d):
    """Census Schedule C country code to place id, by ISO2; anything else becomes a census: place."""
    out = {}
    for line in open(kg.download(COUNTRIES, d / "country.txt"), encoding="latin-1"):
        p = [x.strip() for x in line.split("|")]
        if len(p) == 3 and p[0].isdigit():
            out[p[0]] = (l.country(iso2=p[2]) if p[2] else None) or l.other_place("census:" + p[0], p[1])
    l.conn.commit()
    return out


def main():
    fields = dict(name="US state trade in goods by partner country and 4-digit HS", publisher="US Census Bureau, USA Trade Online",
                  url="https://www.census.gov/foreign-trade/statistics/state/data/index.html", data_url=API % "{exports,imports}",
                  kinds=["flows"], about="Each US state's goods exports and imports with each partner country, by 4-digit HS, annual",
                  coverage="50 states and DC, last 5 complete years", access="free-key", license="Public domain", found_by="core")
    key = os.environ.get("CENSUS_API_KEY")
    if not key:
        conn = kg.connect()
        with conn.cursor() as cur:
            kg.add_source(cur, "census_state_trade", **fields)
        conn.commit()
        print("census_state_trade: no CENSUS_API_KEY (free key: https://api.census.gov/data/key_signup.html), left listed")
        return
    l = kg.Loader("census_state_trade", **fields)
    d = kg.workdir("census_state_trade")
    places, sectors = census_places(l, d), h.hs_ids(l)
    l.cur.execute("SELECT code FROM kg.places WHERE code ~ '^US\\.[A-Z]{2}$' ORDER BY code")
    states = [r[0] for r in l.cur.fetchall()]
    year_end = __import__("datetime").date.today().year - 1
    skipped = 0
    for flow, ccol, vcol, slug, name, about in FLOWS:
        m = l.measure(slug, name, "USD", "goods_trade", about)
        for year in range(year_end - YEARS + 1, year_end + 1):
            for st in states:
                part = "%s/%d/%s" % (flow, year, st)
                if l.done(part):
                    continue
                code = st.split(".")[1]
                rows = get("%s?get=%s,CTY_CODE,%s&STATE=%s&COMM_LVL=HS4&SUMMARY_LVL=DET&time=%d-12" % (API % flow, ccol, vcol, code, year), key)
                with l.part(part):
                    for r in rows[1:]:
                        c = dict(zip(rows[0], r))
                        v, pid, sid = float(c[vcol] or 0), places.get(c["CTY_CODE"]), sectors.get(c[ccol])
                        if v <= 0 or not pid or not sid:
                            skipped += v > 0
                            continue
                        state = l.place(st)
                        l.flow(m, year, state if flow == "exports" else pid, pid if flow == "exports" else state, sid, v)
    l.finish("%d rows skipped for unknown country or product" % skipped if skipped else None)
    kg.cleanup("census_state_trade")


if __name__ == "__main__":
    main()
