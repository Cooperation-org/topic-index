"""Batched writes of entities and links for big files. Nothing here commits: call inside `with l.part(...)`."""
import json

import psycopg

ENTITY_COLS = "ext_id, name, kind, place_id, lat, lon, sector_id, url, attrs"


def bulk_entities(l, rows):
    """rows: (ext_id, name, kind, place_id, lat, lon, sector_id, url, attrs dict or None). Upsert by (source, ext_id)."""
    seen = {}
    for r in rows:
        seen[str(r[0])] = r
    if not seen:
        return 0
    cur = l.cur
    cur.execute("""CREATE TEMP TABLE IF NOT EXISTS kg_in_entities (ext_id text, name text, kind text, place_id int,
                   lat float8, lon float8, sector_id int, url text, attrs text)""")
    cur.execute("TRUNCATE kg_in_entities")
    with cur.copy("COPY kg_in_entities (%s) FROM STDIN" % ENTITY_COLS) as c:
        for r in seen.values():
            attrs = json.dumps(r[8], ensure_ascii=False).replace("\\u0000", "") if r[8] else None
            c.write_row((str(r[0]), (r[1] or "").replace("\x00", ""), r[2], r[3], r[4], r[5], r[6], r[7], attrs))
    cur.execute("""INSERT INTO kg.entities (source_id, ext_id, name, kind, place_id, lat, lon, sector_id, url, attrs)
                   SELECT %s, ext_id, name, kind, place_id, lat, lon, sector_id, url, attrs::jsonb FROM kg_in_entities
                   ON CONFLICT (source_id, ext_id) DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind,
                     place_id = EXCLUDED.place_id, lat = EXCLUDED.lat, lon = EXCLUDED.lon,
                     sector_id = EXCLUDED.sector_id, url = EXCLUDED.url, attrs = EXCLUDED.attrs""", (l.source_id,))
    l.written += len(seen)
    return len(seen)


def replace_links(l, kind, rows, to_source_id=None):
    """Replace this source's links of one kind. rows: (from_ext_id, to_ext_id, attrs dict or None, year or None).
    Both ends resolve to entities of this source (to end: to_source_id when given). Unresolved rows are dropped."""
    cur = l.cur
    cur.execute("CREATE TEMP TABLE IF NOT EXISTS kg_in_links (f text, t text, attrs text, year smallint)")
    cur.execute("TRUNCATE kg_in_links")
    n = 0
    with cur.copy("COPY kg_in_links FROM STDIN") as c:
        for f, t, attrs, year in rows:
            c.write_row((str(f), str(t), json.dumps(attrs, ensure_ascii=False) if attrs else None, year))
            n += 1
    cur.execute("DELETE FROM kg.links WHERE source_id = %s AND kind = %s", (l.source_id, kind))
    cur.execute("""INSERT INTO kg.links (source_id, kind, from_entity, to_entity, year, attrs)
                   SELECT %s, %s, a.id, b.id, i.year, i.attrs::jsonb
                   FROM kg_in_links i JOIN kg.entities a ON a.source_id = %s AND a.ext_id = i.f
                                      JOIN kg.entities b ON b.source_id = %s AND b.ext_id = i.t""",
                (l.source_id, kind, l.source_id, to_source_id or l.source_id))
    got = cur.rowcount
    l.written += got
    return got, n - got


def geo_ok(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None
    if -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0):
        return lat, lon
    return None, None


ALIASES = {
    "united states": "united states of america", "us": "united states of america", "usa": "united states of america",
    "russia": "russian federation", "south korea": "korea, republic of", "north korea": "korea, democratic people's republic of",
    "iran": "iran, islamic republic of", "syria": "syrian arab republic", "vietnam": "viet nam",
    "laos": "lao people's democratic republic", "bolivia": "bolivia, plurinational state of",
    "venezuela": "venezuela, bolivarian republic of", "tanzania": "tanzania, united republic of",
    "moldova": "moldova, republic of", "brunei": "brunei darussalam", "czech republic": "czechia", "turkey": "türkiye",
    "united kingdom": "united kingdom of great britain and northern ireland", "uk": "united kingdom of great britain and northern ireland",
    "burma": "myanmar", "ivory coast": "côte d'ivoire", "cote d'ivoire": "côte d'ivoire", "swaziland": "eswatini",
    "macedonia": "north macedonia", "cape verde": "cabo verde", "east timor": "timor-leste",
    "democratic republic of the congo": "congo, democratic republic of the", "zaire": "congo, democratic republic of the",
    "republic of the congo": "congo", "gambia, the": "gambia", "bahamas, the": "bahamas", "palestine": "palestine, state of",
    "west bank": "palestine, state of", "taiwan": "taiwan, province of china", "macau": "macao",
    "netherlands": "netherlands, kingdom of the", "the netherlands": "netherlands, kingdom of the",
    "micronesia": "micronesia, federated states of", "falkland islands": "falkland islands (malvinas)",
    "vatican": "holy see", "vatican city": "holy see", "saint martin": "saint martin (french part)",
    "sint maarten": "sint maarten (dutch part)", "british virgin islands": "virgin islands (british)",
    "virgin islands": "virgin islands (u.s.)", "us virgin islands": "virgin islands (u.s.)",
    "u.s. virgin islands": "virgin islands (u.s.)", "reunion": "réunion", "curacao": "curaçao",
    "congo (brazzaville)": "congo", "congo (kinshasa)": "congo, democratic republic of the",
    "federated states of micronesia": "micronesia, federated states of", "korea, south": "korea, republic of",
    "korea, north": "korea, democratic people's republic of", "caribbean netherlands": "bonaire, sint eustatius and saba",
    "south georgia and south sandwich islands": "south georgia and the south sandwich islands", "svalbard": "svalbard and jan mayen",
    "saint helena, ascension, and tristan da cunha": "saint helena, ascension and tristan da cunha",
    "falkland islands (islas malvinas)": "falkland islands (malvinas)", "saint barthelemy": "saint barthélemy",
    "bosnia-herzegovina": "bosnia and herzegovina", "palestine (*)": "palestine, state of",
    "congo, democratic republic of": "congo, democratic republic of the", "laos, people's democratic republic": "lao people's democratic republic",
    "russia, federation of": "russian federation", "cocos islands": "cocos (keeling) islands", "st. helena": "saint helena, ascension and tristan da cunha",
}


class Names:
    """Country and first-level division lookups by name, for sources that give names, not codes."""

    def __init__(self, l):
        self.l = l
        self.missing = {}
        l.cur.execute("SELECT id, parent_id, name, alt_names, kind, iso3 FROM kg.places WHERE kind IN ('country', 'admin1')")
        self.admin1 = {}
        self.iso3 = {}
        for id_, parent, name, alts, kind, iso3 in l.cur.fetchall():
            if kind == "admin1":
                for n in [name] + (alts or []):
                    self.admin1.setdefault((parent, n.lower()), id_)
            else:
                self.iso3[iso3] = id_

    def country(self, name):
        if not name:
            return None
        n = name.strip().lower()
        pid = self.l.country(name=n) or self.l.country(name=ALIASES.get(n, n))
        if not pid and n.startswith("the "):
            pid = self.l.country(name=n[4:])
        if not pid:
            self.missing[name] = self.missing.get(name, 0) + 1
        return pid

    def division(self, country_id, name):
        """admin1 place id by name within a country, else the country."""
        return (country_id and name and self.admin1.get((country_id, name.strip().lower()))) or country_id

    def report(self):
        if self.missing:
            top = sorted(self.missing.items(), key=lambda kv: -kv[1])[:15]
            print("unmatched country names:", top, flush=True)


def add_links(l, rows):
    """Append links. rows: (kind, from_ext_id, to_ext_id, sector_id, year, value, unit, attrs dict or None).
    Both ends are entities of this source; unresolved rows are dropped. Returns stored count."""
    cur = l.cur
    cur.execute("""CREATE TEMP TABLE IF NOT EXISTS kg_in_links2 (kind text, f text, t text, sector int, year smallint,
                   value float8, unit text, attrs text)""")
    cur.execute("TRUNCATE kg_in_links2")
    with cur.copy("COPY kg_in_links2 FROM STDIN") as c:
        for kind, f, t, sector, year, value, unit, attrs in rows:
            c.write_row((kind, str(f), str(t), sector, year, value, unit, json.dumps(attrs, ensure_ascii=False) if attrs else None))
    cur.execute("""INSERT INTO kg.links (source_id, kind, from_entity, to_entity, sector_id, year, value, unit, attrs)
                   SELECT %s, i.kind, a.id, b.id, i.sector, i.year, i.value, i.unit, i.attrs::jsonb
                   FROM kg_in_links2 i JOIN kg.entities a ON a.source_id = %s AND a.ext_id = i.f
                                       JOIN kg.entities b ON b.source_id = %s AND b.ext_id = i.t""",
                (l.source_id, l.source_id, l.source_id))
    l.written += cur.rowcount
    return cur.rowcount


def list_only(slug, note, **fields):
    """Catalog row for a source that is not loaded: access is set, status stays listed, the note says why."""
    import kg
    conn = kg.connect()
    cur = conn.cursor()
    sid = kg.add_source(cur, slug, **fields)
    cur.execute("UPDATE kg.sources SET status_note = %s WHERE id = %s AND status = 'listed'", (note, sid))
    conn.commit()
    conn.close()
    print("%s  listed  %s" % (slug, note), flush=True)
