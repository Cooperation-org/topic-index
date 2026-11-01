"""Shared pieces for knowledge graph loaders: sources, lookups, buffered writes, restart log."""
import csv
import io
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path

import psycopg

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import ti  # noqa: E402

BATCH = 50_000
UA = "Mozilla/5.0 (X11; Linux x86_64) topic-index-knowledge-graph"
SOURCE_FIELDS = ("name", "publisher", "url", "data_url", "about", "kinds", "coverage",
                 "access", "license", "found_by")


def connect():
    return ti.connect()


def add_source(cur, slug, **fields):
    """Insert or update a catalog row; loaded status and counts stay as they are. Returns id."""
    bad = set(fields) - set(SOURCE_FIELDS)
    if bad:
        raise ValueError("unknown source fields: %s" % sorted(bad))
    cols = ["slug"] + list(fields)
    updates = ", ".join("%s = EXCLUDED.%s" % (c, c) for c in fields) or "slug = EXCLUDED.slug"
    cur.execute("INSERT INTO kg.sources (%s) VALUES (%s) ON CONFLICT (slug) DO UPDATE SET %s RETURNING id"
                % (", ".join(cols), ", ".join(["%s"] * len(cols)), updates),
                [slug] + list(fields.values()))
    return cur.fetchone()[0]


def download(url, dest, headers=None, timeout=600):
    """Stream a URL to a file; an existing file is kept, so restarts skip it."""
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size:
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out, 1 << 20)
    tmp.rename(dest)
    return dest


def zip_csv(path, member, **kwargs):
    """Rows as dicts from one CSV inside a zip, read without unpacking it."""
    with zipfile.ZipFile(path) as z, z.open(member) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""), **kwargs)


class Loader:
    """One source being stored. Rows go out in batches and commit as they go."""

    def __init__(self, slug, **source_fields):
        self.conn = connect()
        self.cur = self.conn.cursor()
        self.slug = slug
        self.source_id = add_source(self.cur, slug, **source_fields)
        self.cur.execute("UPDATE kg.sources SET status = 'loading', status_note = NULL WHERE id = %s",
                         (self.source_id,))
        self.conn.commit()
        self._places = {}
        self._sectors = {}
        self._measures = {}
        self._flows = []
        self._stats = []
        self.written = 0

    # lookups
    def _place_cache(self):
        if not self._places:
            self.cur.execute("SELECT id, code, iso2, iso3, m49, name, kind FROM kg.places")
            for id_, code, iso2, iso3, m49, name, kind in self.cur.fetchall():
                self._places[code] = id_
                if kind == "country":
                    if iso2:
                        self._places["iso2:" + iso2] = id_
                    if m49 is not None:
                        self._places["m49:%d" % m49] = id_
                    self._places["name:" + name.lower()] = id_
        return self._places

    def place(self, code):
        """Place id by code: PAK, US.AZ, US.AZ.013, region:asia, world. None when unknown."""
        return self._place_cache().get(code)

    def country(self, iso3=None, iso2=None, m49=None, name=None):
        c = self._place_cache()
        if iso3:
            return c.get(iso3)
        if iso2:
            return c.get("iso2:" + iso2)
        if m49 is not None:
            return c.get("m49:%d" % int(m49))
        return c.get("name:" + name.lower()) if name else None

    def other_place(self, code, name, lat=None, lon=None):
        """A place outside the standard list: a source's aggregate or unallocated bucket."""
        pid = self.place(code)
        if pid:
            return pid
        self.cur.execute("""INSERT INTO kg.places (code, name, kind, lat, lon) VALUES (%s, %s, 'other', %s, %s)
                            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name RETURNING id""",
                         (code, name, lat, lon))
        pid = self.cur.fetchone()[0]
        self._places[code] = pid
        return pid

    def sector(self, scheme, code, name=None, parent=None):
        """Sector id, created on first use. parent is a sector id."""
        key = (scheme, str(code))
        if key in self._sectors:
            return self._sectors[key]
        parent_path = None
        if parent:
            self.cur.execute("SELECT path FROM kg.sectors WHERE id = %s", (parent,))
            parent_path = self.cur.fetchone()[0]
        path = "%s/%s" % (parent_path or scheme, code)
        self.cur.execute("""INSERT INTO kg.sectors (scheme, code, name, parent_id, path) VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (scheme, code) DO UPDATE SET name = COALESCE(EXCLUDED.name, kg.sectors.name),
                              parent_id = COALESCE(EXCLUDED.parent_id, kg.sectors.parent_id),
                              path = COALESCE(CASE WHEN EXCLUDED.parent_id IS NOT NULL THEN EXCLUDED.path END, kg.sectors.path)
                            RETURNING id""",
                         (scheme, str(code), name or str(code), parent, path))
        self._sectors[key] = self.cur.fetchone()[0]
        return self._sectors[key]

    def measure(self, slug, name, unit, family, about=None):
        if slug not in self._measures:
            self.cur.execute("""INSERT INTO kg.measures (slug, name, unit, family, about) VALUES (%s, %s, %s, %s, %s)
                                ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name, unit = EXCLUDED.unit,
                                  family = EXCLUDED.family, about = COALESCE(EXCLUDED.about, kg.measures.about)
                                RETURNING id""", (slug, name, unit, family, about))
            self._measures[slug] = self.cur.fetchone()[0]
        return self._measures[slug]

    # writes
    def flow(self, measure_id, year, from_place, to_place, sector_id, value):
        self._flows.append((self.source_id, measure_id, year, from_place, to_place, sector_id, value))
        if len(self._flows) >= BATCH:
            self.flush()

    def stat(self, measure_id, year, place_id, sector_id, value):
        self._stats.append((self.source_id, measure_id, year, place_id, sector_id, value))
        if len(self._stats) >= BATCH:
            self.flush()

    def flush(self):
        if self._flows:
            with self.cur.copy("""COPY kg.flows (source_id, measure_id, year, from_place, to_place, sector_id, value)
                                  FROM STDIN""") as c:
                for r in self._flows:
                    c.write_row(r)
            self.written += len(self._flows)
            self._flows = []
        if self._stats:
            with self.cur.copy("""COPY kg.stats (source_id, measure_id, year, place_id, sector_id, value)
                                  FROM STDIN""") as c:
                for r in self._stats:
                    c.write_row(r)
            self.written += len(self._stats)
            self._stats = []
        self.conn.commit()

    def entity(self, ext_id, name, kind, place_id=None, lat=None, lon=None, sector_id=None, url=None, attrs=None):
        """Insert or update an entity; returns id. attrs is a dict."""
        self.cur.execute("""INSERT INTO kg.entities (source_id, ext_id, name, kind, place_id, lat, lon, sector_id, url, attrs)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (source_id, ext_id) DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind,
                              place_id = EXCLUDED.place_id, lat = EXCLUDED.lat, lon = EXCLUDED.lon,
                              sector_id = EXCLUDED.sector_id, url = EXCLUDED.url, attrs = EXCLUDED.attrs
                            RETURNING id""",
                         (self.source_id, str(ext_id), name, kind, place_id, lat, lon, sector_id, url,
                          psycopg.types.json.Jsonb(attrs) if attrs else None))
        self.written += 1
        return self.cur.fetchone()[0]

    def link(self, kind, from_entity, to_entity=None, to_place=None, sector_id=None, year=None,
             value=None, unit=None, attrs=None):
        self.cur.execute("""INSERT INTO kg.links (source_id, kind, from_entity, to_entity, to_place, sector_id, year, value, unit, attrs)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                         (self.source_id, kind, from_entity, to_entity, to_place, sector_id, year, value, unit,
                          psycopg.types.json.Jsonb(attrs) if attrs else None))
        self.written += 1

    # restart log
    def done(self, part):
        self.cur.execute("SELECT 1 FROM kg.load_log WHERE source_id = %s AND part = %s", (self.source_id, part))
        return self.cur.fetchone() is not None

    @contextmanager
    def part(self, name):
        """Rows written inside commit with the log entry. Use `if not l.done(x)` first; rerun skips it."""
        start = self.written
        yield
        self.flush()
        self.cur.execute("""INSERT INTO kg.load_log (source_id, part, row_count) VALUES (%s, %s, %s)
                            ON CONFLICT (source_id, part) DO UPDATE SET row_count = EXCLUDED.row_count, done_at = now()""",
                         (self.source_id, name, self.written - start))
        self.conn.commit()
        print("%s  %s  %d rows" % (self.slug, name, self.written - start), flush=True)

    def replace(self, table="both"):
        """Clear this source's rows before a full reload."""
        for t in ("flows", "stats") if table == "both" else (table,):
            self.cur.execute("DELETE FROM kg.%s WHERE source_id = %%s" % t, (self.source_id,))
        self.cur.execute("DELETE FROM kg.load_log WHERE source_id = %s", (self.source_id,))
        self.conn.commit()

    def finish(self, note=None):
        self.flush()
        self.cur.execute("""UPDATE kg.sources s SET status = 'loaded', status_note = %s, loaded_at = now(),
              row_count = (SELECT count(*) FROM kg.flows WHERE source_id = s.id)
                        + (SELECT count(*) FROM kg.stats WHERE source_id = s.id)
                        + (SELECT count(*) FROM kg.entities WHERE source_id = s.id)
                        + (SELECT count(*) FROM kg.links WHERE source_id = s.id)
              WHERE id = %s RETURNING row_count""", (note, self.source_id))
        print("%s  loaded  %d rows" % (self.slug, self.cur.fetchone()[0]), flush=True)
        self.conn.commit()

    def fail(self, note):
        self.conn.rollback()
        self.cur.execute("UPDATE kg.sources SET status = 'failed', status_note = %s WHERE id = %s",
                         (str(note)[:500], self.source_id))
        self.conn.commit()


def workdir(slug):
    """Empty download folder for one source, outside the repo. Delete when loaded."""
    d = Path(tempfile.gettempdir()) / "kg-downloads" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def cleanup(slug):
    shutil.rmtree(Path(tempfile.gettempdir()) / "kg-downloads" / slug, ignore_errors=True)
