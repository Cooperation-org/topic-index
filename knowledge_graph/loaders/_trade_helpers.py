"""Shared by the trade loaders: BACI places and files, HS sector ids, restart-safe year parts."""
import io
import re
import zipfile

import kg

BACI = "https://www.cepii.fr/DATA_DOWNLOAD/baci/data/BACI_%s_V202601.zip"
BACI_PAGE = "https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37"
HISTORIC = re.compile(r"\(\.\.\.\d{4}\)")
GOODS_ABOUT = ("Goods exported from the 'from' place to the 'to' place in the year, USD, free on board (CEPII reconciles "
               "exporter and importer reports and removes freight from import values). Taiwan is not reported separately "
               "by the UN; its trade sits in place baci:490 (Other Asia, nes).")


def goods_measure(l):
    return l.measure("goods_trade_usd", "Goods trade, exporter to importer", "USD", "goods_trade", GOODS_ABOUT)


def hs_ids(l):
    """HS code to sector id for the whole scheme, read once."""
    l.cur.execute("SELECT code, id FROM kg.sectors WHERE scheme = 'hs'")
    return dict(l.cur.fetchall())


def baci_places(l, zip_path):
    """BACI country code to place id. Current countries by ISO3; former states and aggregates become 'other' places."""
    out = {}
    for r in kg.zip_csv(zip_path, "country_codes_V202601.csv"):
        code, name = r["country_code"], r["country_name"]
        pid = None if HISTORIC.search(name) else l.country(iso3=r["country_iso3"])
        if not pid and HISTORIC.search(name):
            pid = l.place("m49:" + code)
        out[code] = pid or l.other_place("baci:" + code, name)
    l.conn.commit()
    return out


def baci_years(zip_path):
    """{year: member name} for the yearly CSVs in a BACI zip."""
    with zipfile.ZipFile(zip_path) as z:
        return {int(re.search(r"_Y(\d{4})_", n).group(1)): n for n in z.namelist() if re.search(r"_Y\d{4}_", n)}


def baci_rows(zip_path, member):
    """Yield (exporter, importer, product, value_thousand_usd) as strings and a float, skipping the header."""
    with zipfile.ZipFile(zip_path) as z, z.open(member) as f:
        lines = io.TextIOWrapper(f, encoding="utf-8")
        next(lines)
        for line in lines:
            t, i, j, k, v, _q = line.split(",")
            yield i, j, k, float(v)


def clear_year(l, year):
    """A killed load can leave part of a year with no log entry: drop it before reloading that year."""
    l.cur.execute("DELETE FROM kg.flows WHERE source_id = %s AND year = %s", (l.source_id, year))
    l.conn.commit()
