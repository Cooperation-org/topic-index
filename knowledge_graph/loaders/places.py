"""Places: UN regions and countries, GeoNames first-level and second-level divisions, cities over 15,000 people."""
import csv
import json
import zipfile
import io

import kg

REGIONS_CSV = "https://raw.githubusercontent.com/lukes/ISO-3166-Countries-with-Regional-Codes/master/all/all.csv"
NE_COUNTRIES = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
GN = "https://download.geonames.org/export/dump/"


def upsert(cur, code, name, kind, parent=None, iso2=None, iso3=None, m49=None, gid=None, lat=None, lon=None, pop=None, alt=None):
    cur.execute("""INSERT INTO kg.places (code, name, kind, parent_id, iso2, iso3, m49, geonameid, lat, lon, population, alt_names)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind, parent_id = EXCLUDED.parent_id,
                     iso2 = EXCLUDED.iso2, iso3 = EXCLUDED.iso3, m49 = EXCLUDED.m49, geonameid = EXCLUDED.geonameid,
                     lat = EXCLUDED.lat, lon = EXCLUDED.lon, population = EXCLUDED.population, alt_names = EXCLUDED.alt_names
                   RETURNING id""", (code, name, kind, parent, iso2, iso3, m49, gid, lat, lon, pop, alt))
    return cur.fetchone()[0]


def main():
    l = kg.Loader("places", name="Places: UN M49 regions, Natural Earth, GeoNames",
                  publisher="UN Statistics Division, Natural Earth, GeoNames",
                  url="https://www.geonames.org/", data_url=GN, kinds=["places"],
                  about="Regions, countries, first and second level divisions, cities over 15,000 people, with coordinates and population",
                  coverage="World", access="open", license="CC BY 4.0 (GeoNames), public domain (Natural Earth)", found_by="core")
    d = kg.workdir("places")
    cur = l.cur
    world = upsert(cur, "world", "World", "world", lat=0, lon=0)
    points = {}
    for f in json.load(open(kg.download(NE_COUNTRIES, d / "ne.geojson")))["features"]:
        p = f["properties"]
        points[p["ISO_A3_EH"]] = (p["LABEL_Y"], p["LABEL_X"], p.get("POP_EST"))

    countries, seen = {}, {}
    rows = list(csv.DictReader(open(kg.download(REGIONS_CSV, d / "regions.csv"), encoding="utf-8")))
    for r in rows:
        parent = world
        for level in ("region", "sub-region"):
            name = r[level]
            if name:
                code = "region:" + name.lower().replace(" ", "-")
                if code not in seen:
                    seen[code] = upsert(cur, code, name, "region", parent=parent, m49=int(r[level + "-code"]))
                parent = seen[code]
        lat, lon, pop = points.get(r["alpha-3"], (None, None, None))
        countries[r["alpha-2"]] = upsert(cur, r["alpha-3"], r["name"], "country", parent=parent, iso2=r["alpha-2"],
                                         iso3=r["alpha-3"], m49=int(r["country-code"]), lat=lat, lon=lon,
                                         pop=int(pop) if pop else None)
    l.conn.commit()

    # GeoNames dump columns: id, name, ascii, alt, lat, lon, class, feature, country, cc2, admin1, admin2, admin3, admin4, population, ...
    adm1, adm2 = {}, []
    with zipfile.ZipFile(kg.download(GN + "allCountries.zip", d / "allCountries.zip")) as z, z.open("allCountries.txt") as f:
        for line in io.TextIOWrapper(f, encoding="utf-8"):
            c = line.split("\t", 8)
            if c[7] not in ("ADM1", "ADM2"):
                continue
            c = line.rstrip("\n").split("\t")
            if c[8] in countries and c[10]:
                if c[7] == "ADM1":
                    adm1["%s.%s" % (c[8], c[10])] = upsert(
                        cur, "%s.%s" % (c[8], c[10]), c[1], "admin1", parent=countries[c[8]], iso2=c[8], gid=int(c[0]),
                        lat=float(c[4]), lon=float(c[5]), pop=int(c[14] or 0) or None, alt=c[3].split(",")[:20] if c[3] else None)
                elif c[11]:
                    adm2.append(c)
    l.conn.commit()
    for i, c in enumerate(adm2):
        parent = adm1.get("%s.%s" % (c[8], c[10]))
        if parent:
            upsert(cur, "%s.%s.%s" % (c[8], c[10], c[11]), c[1], "admin2", parent=parent, iso2=c[8], gid=int(c[0]),
                   lat=float(c[4]), lon=float(c[5]), pop=int(c[14] or 0) or None)
        if i % 5000 == 0:
            l.conn.commit()
    l.conn.commit()

    with zipfile.ZipFile(kg.download(GN + "cities15000.zip", d / "cities.zip")) as z, z.open("cities15000.txt") as f:
        for i, line in enumerate(io.TextIOWrapper(f, encoding="utf-8")):
            c = line.rstrip("\n").split("\t")
            parent = adm1.get("%s.%s" % (c[8], c[10])) or countries.get(c[8])
            if parent:
                upsert(cur, "gn:" + c[0], c[1], "city", parent=parent, iso2=c[8], gid=int(c[0]), lat=float(c[4]),
                       lon=float(c[5]), pop=int(c[14] or 0) or None, alt=c[3].split(",")[:20] if c[3] else None)
            if i % 5000 == 0:
                l.conn.commit()
    l.conn.commit()
    cur.execute("SELECT count(*) FROM kg.places")
    n = cur.fetchone()[0]
    l.written = n
    l.flush()
    cur.execute("UPDATE kg.sources SET status = 'loaded', row_count = %s, loaded_at = now() WHERE id = %s", (n, l.source_id))
    l.conn.commit()
    print("places", n)
    kg.cleanup("places")


if __name__ == "__main__":
    main()
