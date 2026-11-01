"""The Money Map: a globe over the knowledge graph, with filters and a chat."""
import hmac
import json
import os
import sys
from pathlib import Path

from fastapi import Cookie, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeSerializer
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE)]
import kg  # noqa: E402

kg.ti.load_env()
import agent  # noqa: E402

DAILY_ASKS = 200
COOKIE = "money_map"
pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=8, open=True,
                      kwargs={"options": "-c statement_timeout=30000", "autocommit": True})
signer = URLSafeSerializer(os.environ["KG_SESSION_SECRET"], salt="money-map")
app = FastAPI(title="Money Map")


def rows(sql, params=()):
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def one(sql, params=()):
    found = rows(sql, params)
    return found[0] if found else None


def scope(place):
    """None for the world; else the place id, or its member countries for a region."""
    if not place:
        return None
    p = one("SELECT id, kind FROM kg.places WHERE id = %s", (place,))
    if not p:
        raise HTTPException(404, "no such place")
    if p["kind"] == "world":
        return None
    if p["kind"] != "region":
        return [p["id"]]
    return [r["id"] for r in rows("""WITH RECURSIVE d AS (SELECT id, kind FROM kg.places WHERE id = %s
                                     UNION ALL SELECT c.id, c.kind FROM kg.places c JOIN d ON c.parent_id = d.id
                                     WHERE d.kind = 'region')
                                     SELECT id FROM d WHERE kind = 'country'""", (place,))]


@app.get("/api/datasets")
def datasets():
    return rows("""SELECT d.source_id, d.measure_id, d.kind, d.years, d.has_sector, s.slug AS source, s.name AS source_name, s.url AS source_url,
                          m.slug AS measure, m.name AS measure_name, m.unit, m.family, m.about
                   FROM kg.datasets d JOIN kg.sources s ON s.id = d.source_id JOIN kg.measures m ON m.id = d.measure_id
                   ORDER BY m.family, m.name, s.name""")


@app.get("/api/countries")
def countries():
    return rows("SELECT id, iso3, name FROM kg.places WHERE kind = 'country'")


@app.get("/api/map")
def map_values(source: int, measure: int, year: int, kind: str = "flow", dir: str = "out", sector: int | None = None):
    """Value per place, for shading the globe."""
    col = "from_place" if dir == "out" else "to_place"
    if kind == "stat":
        cond = "st.sector_id IS NULL" if sector is None else \
            "st.sector_id IN (SELECT id FROM kg.sectors WHERE path LIKE (SELECT path FROM kg.sectors WHERE id = %(sector)s) || '%%')"
        if sector is None and not one("""SELECT 1 FROM kg.stats WHERE source_id=%s AND measure_id=%s AND year=%s AND sector_id IS NULL LIMIT 1""",
                                      (source, measure, year)):
            cond = "true"
        sql = f"""SELECT p.id, p.code, p.iso3, p.name, p.kind, p.lat, p.lon, sum(st.value) AS value FROM kg.stats st
                  JOIN kg.places p ON p.id = st.place_id
                  WHERE st.source_id=%(source)s AND st.measure_id=%(measure)s AND st.year=%(year)s AND {cond}
                  GROUP BY p.id ORDER BY value DESC"""
    elif sector is None:
        sql = f"""SELECT p.id, p.code, p.iso3, p.name, p.kind, p.lat, p.lon, sum(f.value) AS value FROM kg.flow_pairs f
                  JOIN kg.places p ON p.id = f.{col}
                  WHERE f.source_id=%(source)s AND f.measure_id=%(measure)s AND f.year=%(year)s
                  GROUP BY p.id ORDER BY value DESC"""
    else:
        sql = f"""SELECT p.id, p.code, p.iso3, p.name, p.kind, p.lat, p.lon, sum(f.value) AS value FROM kg.flows f
                  JOIN kg.places p ON p.id = f.{col}
                  WHERE f.source_id=%(source)s AND f.measure_id=%(measure)s AND f.year=%(year)s
                    AND f.sector_id IN (SELECT id FROM kg.sectors WHERE path LIKE (SELECT path FROM kg.sectors WHERE id = %(sector)s) || '%%')
                  GROUP BY p.id ORDER BY value DESC"""
    return rows(sql, {"source": source, "measure": measure, "year": year, "sector": sector})


@app.get("/api/partners")
def partners(source: int, measure: int, year: int, place: int | None = None, dir: str = "out",
             sector: int | None = None, limit: int = 25):
    """Biggest partners of a place, or biggest pairs in the world, in one direction."""
    ids = scope(place)
    a, b = ("from_place", "to_place") if dir == "out" else ("to_place", "from_place")
    table = "kg.flow_pairs" if sector is None else "kg.flows"
    sector_cond = "" if sector is None else \
        "AND f.sector_id IN (SELECT id FROM kg.sectors WHERE path LIKE (SELECT path FROM kg.sectors WHERE id = %(sector)s) || '%%')"
    params = {"source": source, "measure": measure, "year": year, "ids": ids, "sector": sector, "limit": min(limit, 100)}
    if ids is None:
        sql = f"""SELECT a.id AS a_id, a.name AS a_name, a.lat AS a_lat, a.lon AS a_lon, b.id AS b_id, b.name AS b_name,
                         b.lat AS b_lat, b.lon AS b_lon, b.code AS b_code, sum(f.value) AS value
                  FROM {table} f JOIN kg.places a ON a.id = f.{a} JOIN kg.places b ON b.id = f.{b}
                  WHERE f.source_id=%(source)s AND f.measure_id=%(measure)s AND f.year=%(year)s {sector_cond}
                    AND a.id <> b.id AND a.kind NOT IN ('other', 'world') AND b.kind NOT IN ('other', 'world')
                  GROUP BY a.id, b.id ORDER BY value DESC LIMIT %(limit)s"""
    else:
        sql = f"""SELECT min(a.id) AS a_id, min(a.name) AS a_name, avg(a.lat) AS a_lat, avg(a.lon) AS a_lon, b.id AS b_id, b.name AS b_name,
                         b.lat AS b_lat, b.lon AS b_lon, b.code AS b_code, sum(f.value) AS value
                  FROM {table} f JOIN kg.places a ON a.id = f.{a} JOIN kg.places b ON b.id = f.{b}
                  WHERE f.source_id=%(source)s AND f.measure_id=%(measure)s AND f.year=%(year)s {sector_cond}
                    AND f.{a} = ANY(%(ids)s) AND NOT f.{b} = ANY(%(ids)s) AND b.kind NOT IN ('other', 'world')
                  GROUP BY b.id ORDER BY value DESC LIMIT %(limit)s"""
    return rows(sql, params)


@app.get("/api/sizes")
def sizes(source: int, measure: int, year: int, kind: str = "flow", place: int | None = None, dir: str = "out",
          parent: int | None = None, limit: int = 30):
    """Sector sizes one level under parent, for a place or the world."""
    ids = scope(place)
    depth = 2
    prefix = None
    if parent:
        s = one("SELECT path FROM kg.sectors WHERE id = %s", (parent,))
        prefix = s["path"] if s else None
        depth = prefix.count("/") + 2 if prefix else 2
    params = {"source": source, "measure": measure, "year": year, "ids": ids, "prefix": (prefix + "/%") if prefix else "%",
              "depth": depth, "limit": min(limit, 100)}
    if kind == "stat":
        if ids is None:
            base = """SELECT st.sector_id, st.value FROM kg.stats st JOIN kg.places p ON p.id = st.place_id
                      WHERE st.source_id=%(source)s AND st.measure_id=%(measure)s AND st.year=%(year)s AND p.kind = 'country' AND st.sector_id IS NOT NULL"""
        else:
            base = """SELECT st.sector_id, st.value FROM kg.stats st
                      WHERE st.source_id=%(source)s AND st.measure_id=%(measure)s AND st.year=%(year)s AND st.place_id = ANY(%(ids)s) AND st.sector_id IS NOT NULL"""
    elif ids is None:
        base = """SELECT sector_id, value FROM kg.flow_sectors WHERE source_id=%(source)s AND measure_id=%(measure)s AND year=%(year)s"""
    else:
        col = "from_place" if dir == "out" else "to_place"
        base = f"""SELECT sector_id, value FROM kg.flows WHERE source_id=%(source)s AND measure_id=%(measure)s AND year=%(year)s
                   AND {col} = ANY(%(ids)s) AND sector_id IS NOT NULL"""
    return rows(f"""WITH b AS ({base}),
                    r AS (SELECT array_to_string((string_to_array(s.path, '/'))[1:%(depth)s], '/') AS p, sum(b.value) AS value
                          FROM b JOIN kg.sectors s ON s.id = b.sector_id WHERE s.path LIKE %(prefix)s GROUP BY 1)
                    SELECT s.id, s.code, s.name, s.scheme, r.value,
                           EXISTS (SELECT 1 FROM kg.sectors c WHERE c.parent_id = s.id) AS has_children
                    FROM r JOIN kg.sectors s ON s.path = r.p ORDER BY r.value DESC LIMIT %(limit)s""", params)


@app.get("/api/datasets_for_scheme")
def datasets_for_scheme(scheme: str):
    """Datasets whose sector rows use this classification, biggest source first."""
    keys = []
    for table, kind in (("flow_sectors", "flow"), ("stats", "stat")):
        keys += rows(f"""SELECT source_id || ':' || measure_id || ':{kind}' AS k FROM (
                           SELECT DISTINCT source_id, measure_id FROM kg.{table} t JOIN kg.sectors s ON s.id = t.sector_id
                           WHERE s.scheme = %s) d""", (scheme,))
    return [k["k"] for k in keys]


@app.get("/api/place/{place_id}")
def place(place_id: int):
    p = one("SELECT id, code, name, kind, iso3, lat, lon, population, parent_id FROM kg.places WHERE id = %s", (place_id,))
    if not p:
        raise HTTPException(404, "no such place")
    p["path"] = rows("""WITH RECURSIVE u AS (SELECT id, name, parent_id, 0 AS n FROM kg.places WHERE id = %s
                        UNION ALL SELECT a.id, a.name, a.parent_id, u.n + 1 FROM kg.places a JOIN u ON a.id = u.parent_id)
                        SELECT id, name FROM u ORDER BY n DESC""", (place_id,))
    p["children"] = rows("""SELECT id, name, kind FROM kg.places WHERE parent_id = %s AND kind IN ('region', 'country', 'admin1', 'admin2')
                            ORDER BY population DESC NULLS LAST, name LIMIT 60""", (place_id,))
    p["headline"] = rows("""SELECT DISTINCT ON (st.measure_id) m.name, m.unit, st.year, st.value, s.slug AS source
                            FROM kg.stats st JOIN kg.measures m ON m.id = st.measure_id JOIN kg.sources s ON s.id = st.source_id
                            WHERE st.place_id = %s AND st.sector_id IS NULL
                            ORDER BY st.measure_id, st.year DESC LIMIT 40""", (place_id,))
    p["datasets"] = [r["k"] for r in rows("""SELECT source_id || ':' || measure_id || ':' || kind AS k FROM kg.place_datasets WHERE place_id = %s""", (place_id,))]
    p["entities"] = rows("""SELECT kind, count(*) AS n FROM kg.entities e
                            WHERE e.place_id = %(p)s OR e.place_id IN (SELECT id FROM kg.places WHERE parent_id = %(p)s)
                               OR e.place_id IN (SELECT place_id FROM kg.place_country WHERE country_id = %(p)s)
                            GROUP BY kind ORDER BY n DESC""", {"p": place_id})
    return p


@app.get("/api/place/{place_id}/entities")
def place_entities(place_id: int, kind: str | None = None, q: str | None = None, limit: int = 50):
    return rows("""SELECT e.id, e.name, e.kind, e.url, e.lat, e.lon, s.slug AS source FROM kg.entities e JOIN kg.sources s ON s.id = e.source_id
                   WHERE (e.place_id = %(p)s OR e.place_id IN (SELECT id FROM kg.places WHERE parent_id = %(p)s)
                          OR e.place_id IN (SELECT place_id FROM kg.place_country WHERE country_id = %(p)s))
                     AND (%(kind)s::text IS NULL OR e.kind = %(kind)s) AND (%(q)s::text IS NULL OR e.name ILIKE %(q)s)
                   ORDER BY e.name LIMIT %(limit)s""",
                {"p": place_id, "kind": kind, "q": "%%%s%%" % q if q else None, "limit": min(limit, 200)})


@app.get("/api/place/{place_id}/owners")
def place_owners(place_id: int, limit: int = 25):
    """Who owns the companies registered here, from outside the country."""
    return rows("""SELECT par.name AS parent, c.name AS country, c.id AS country_id, count(*) AS children
                   FROM kg.place_country here
                   JOIN kg.entities e ON e.place_id = here.place_id
                   JOIN kg.links l ON l.from_entity = e.id AND l.kind IN ('ultimate_parent', 'owned_by')
                   JOIN kg.entities par ON par.id = l.to_entity
                   JOIN kg.place_country pc ON pc.place_id = par.place_id
                   JOIN kg.places c ON c.id = pc.country_id
                   WHERE pc.country_id <> here.country_id
                     AND (here.country_id = %(p)s OR here.place_id = %(p)s
                          OR here.place_id IN (SELECT id FROM kg.places WHERE parent_id = %(p)s))
                   GROUP BY 1, 2, 3 ORDER BY children DESC LIMIT %(limit)s""", {"p": place_id, "limit": min(limit, 100)})


@app.get("/api/entities")
def entities(west: float, south: float, east: float, north: float, kinds: str = "", limit: int = 3000):
    """Sites and organizations with coordinates inside the view. West above east crosses the date line."""
    lon = "e.lon BETWEEN %(w)s AND %(e)s" if west <= east else "(e.lon >= %(w)s OR e.lon <= %(e)s)"
    return rows(f"""SELECT e.id, e.name, e.kind, e.lat, e.lon, e.url, s.slug AS source FROM kg.entities e JOIN kg.sources s ON s.id = e.source_id
                    WHERE e.lat BETWEEN %(s)s AND %(n)s AND {lon} AND (%(k)s::text[] = '{{}}' OR e.kind = ANY(%(k)s)) LIMIT %(limit)s""",
                {"w": west, "e": east, "s": south, "n": north, "k": [k for k in kinds.split(",") if k], "limit": min(limit, 5000)})


@app.get("/api/entity_kinds")
def entity_kinds():
    return rows("SELECT kind, count(*) AS n, count(lat) AS with_coords FROM kg.entities GROUP BY kind ORDER BY n DESC")


@app.get("/api/search")
def search(q: str):
    like = "%%%s%%" % q
    return {"places": rows("""SELECT id, name, kind, code, iso3, lat, lon, (SELECT name FROM kg.places x WHERE x.id = p.parent_id) AS parent
                              FROM kg.places p WHERE (name ILIKE %(l)s OR iso3 = upper(%(q)s)) AND kind <> 'other'
                              ORDER BY name ILIKE %(q)s DESC,
                                       array_position(ARRAY['world','region','country','admin1','city','admin2'], kind),
                                       population DESC NULLS LAST LIMIT 12""", {"l": like, "q": q}),
            "sectors": rows("""SELECT id, scheme, code, name FROM kg.sectors WHERE name ILIKE %(l)s OR code = %(q)s
                               ORDER BY length(code), length(name) LIMIT 20""", {"l": like, "q": q})}


@app.get("/api/sector/{sector_id}")
def sector(sector_id: int):
    s = one("SELECT id, scheme, code, name, parent_id FROM kg.sectors WHERE id = %s", (sector_id,))
    if not s:
        raise HTTPException(404, "no such sector")
    s["path"] = rows("""WITH RECURSIVE u AS (SELECT id, name, parent_id, 0 AS n FROM kg.sectors WHERE id = %s
                        UNION ALL SELECT a.id, a.name, a.parent_id, u.n + 1 FROM kg.sectors a JOIN u ON a.id = u.parent_id)
                        SELECT id, name FROM u ORDER BY n DESC""", (sector_id,))
    return s


@app.get("/api/sources")
def sources():
    return rows("""SELECT slug, name, publisher, url, data_url, about, coverage, access, license, status, status_note, row_count, loaded_at
                   FROM kg.sources ORDER BY status = 'loaded' DESC, name""")


class Login(BaseModel):
    password: str


class Ask(BaseModel):
    question: str
    history: list[tuple[str, str]] = []


def signed_in(cookie):
    try:
        return bool(cookie and signer.loads(cookie))
    except BadSignature:
        return False


@app.get("/api/me")
def me(money_map: str | None = Cookie(default=None)):
    return {"signed_in": signed_in(money_map)}


@app.post("/api/login")
def login(body: Login, response: Response):
    if not hmac.compare_digest(body.password, os.environ["KG_ASK_PASSWORD"]):
        raise HTTPException(401, "wrong password")
    response.set_cookie(COOKIE, signer.dumps("team"), max_age=90 * 86400, httponly=True, samesite="lax", secure=True)
    return {"signed_in": True}


@app.post("/api/ask")
def ask(body: Ask, money_map: str | None = Cookie(default=None)):
    if not signed_in(money_map):
        raise HTTPException(401, "sign in to ask")
    if one("SELECT count(*) AS n FROM kg_app.asks WHERE asked_at > now() - interval '1 day'")["n"] >= DAILY_ASKS:
        raise HTTPException(429, "daily limit of %d questions reached" % DAILY_ASKS)
    out = agent.ask(body.question[:4000], body.history[-6:])
    one("""INSERT INTO kg_app.asks (asked_by, question, answer, tool_calls, tokens_in, tokens_out)
           VALUES ('team', %s, %s, %s, %s, %s) RETURNING id""",
        (body.question[:4000], out["answer"], json.dumps(out["tools"]), out["tokens_in"], out["tokens_out"]))
    return JSONResponse({"answer": out["answer"], "map": out["map"]})


@app.get("/health")
def health():
    return one("SELECT count(*) AS places FROM kg.places")


@app.get("/")
def index():
    return FileResponse(HERE / "static/index.html", headers={"Cache-Control": "no-store"})


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
