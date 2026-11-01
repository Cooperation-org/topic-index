"""Web pages over the store: one page per topic, with search and the facet values to browse.

  .venv/bin/uvicorn serve:app --port 8062 --root-path /topics
"""
import html
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastembed import TextEmbedding

import embed
import ti

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
model = TextEmbedding(embed.MODEL, threads=2)
PER_PAGE = 30
e = html.escape

STYLE = """
:root { --bg:#fff; --fg:#1a1a1a; --mute:#666; --line:#e5e5e5; --link:#0b57d0; }
@media (prefers-color-scheme: dark) { :root { --bg:#121212; --fg:#e8e8e8; --mute:#9a9a9a; --line:#2a2a2a; --link:#8ab4f8; } }
* { box-sizing: border-box; }
body { margin:0; padding:16px 24px; background:var(--bg); color:var(--fg);
       font:16px/1.45 system-ui, -apple-system, Segoe UI, sans-serif; }
a { color:var(--link); text-decoration:none; } a:hover { text-decoration:underline; }
header { display:flex; flex-wrap:wrap; gap:12px 24px; align-items:baseline; margin-bottom:16px; }
h1 { font-size:22px; margin:0; }
form { display:flex; gap:8px; flex:1; min-width:260px; }
input[type=search] { flex:1; font:inherit; padding:8px 10px; border:1px solid var(--line); border-radius:6px;
                     background:var(--bg); color:var(--fg); }
select, button { font:inherit; padding:8px 10px; border:1px solid var(--line); border-radius:6px;
                 background:var(--bg); color:var(--fg); }
.r { padding:10px 0; border-top:1px solid var(--line); }
.r .u { color:var(--mute); font-size:13px; }
.r p { margin:2px 0 0; color:var(--mute); font-size:14px; }
.facets { columns: 220px; column-gap:24px; }
.facets a { display:block; padding:2px 0; }
.n { color:var(--mute); font-size:13px; }
nav.more { padding:12px 0; }
"""


def page(title, body):
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>{e(title)}</title><style>{STYLE}</style></head><body>{body}</body></html>""")


def topic_row(cur, slug):
    cur.execute("SELECT slug, name, description FROM topics WHERE slug = %s", (slug,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(404)
    return row


def facet_key(cur, slug):
    cur.execute("""SELECT k FROM queries, jsonb_object_keys(facets) k WHERE topic = %s
                   GROUP BY k ORDER BY count(*) DESC LIMIT 1""", (slug,))
    row = cur.fetchone()
    return row[0] if row else None


@app.get("/", response_class=HTMLResponse)
def index():
    with ti.connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT t.slug, t.name, count(DISTINCT pt.page_id) FROM topics t
                       LEFT JOIN page_topics pt ON pt.topic = t.slug GROUP BY t.slug, t.name ORDER BY t.name""")
        rows = cur.fetchall()
    items = "".join(f'<div class="r"><a href="{e(s)}/">{e(n)}</a> <span class="n">{c:,} pages</span></div>'
                    for s, n, c in rows)
    return page("Topics", f"<header><h1>Topics</h1></header>{items}")


@app.get("/{slug}/", response_class=HTMLResponse)
def topic(slug: str, q: str = "", f: str = "", site: str = "", start: int = 0):
    with ti.connect() as conn, conn.cursor() as cur:
        slug, name, _ = topic_row(cur, slug)
        key = facet_key(cur, slug)
        cur.execute(f"""SELECT q.facets->>%s v, count(DISTINCT pt.page_id) FROM queries q
                        JOIN page_topics pt ON pt.query_id = q.id
                        WHERE q.topic = %s AND q.facets ? %s GROUP BY v ORDER BY v""", (key, slug, key))
        values = cur.fetchall() if key else []
        options = "".join(f'<option value="{e(v)}"{" selected" if v == f else ""}>{e(v)}</option>' for v, _ in values)
        select = f'<select name="f"><option value="">All</option>{options}</select>' if key else ""
        head = f"""<header><h1><a href="../">Topics</a> / {e(name)}</h1>
<form><input type="search" name="q" value="{e(q)}" autofocus>{select}<button>Search</button></form></header>"""
        if q or f or site:
            body = results(cur, slug, key, q, f, site, start)
        else:
            body = browse(cur, slug, key, values)
    return page(name, head + body)


def results(cur, slug, key, q, f, site, start):
    where, params = ["pt.topic = %(slug)s"], {"slug": slug, "key": key, "f": f, "q": q, "site": site}
    if f:
        where.append("q.facets->>%(key)s = %(f)s")
    if site:
        where.append("p.host = %(site)s")
    joins = "JOIN page_topics pt ON pt.page_id = p.id LEFT JOIN queries q ON q.id = pt.query_id"
    if q:
        params["vec"] = str(next(model.embed([q])).tolist())
        # Pages ranked by their best chunk: meaning first, then word matches for chunks not yet embedded.
        sql = f"""SELECT p.url, p.title, p.host, p.page_age, best.text FROM (
                    SELECT DISTINCT ON (c.page_id) c.page_id, c.text,
                           CASE WHEN c.embedding IS NOT NULL THEN c.embedding <=> %(vec)s::vector
                                ELSE 2 - ts_rank(c.tsv, plainto_tsquery('simple', %(q)s)) END AS d
                    FROM chunks c
                    WHERE c.page_id IN (SELECT p.id FROM pages p {joins} WHERE {' AND '.join(where)})
                      AND (c.embedding IS NOT NULL OR c.tsv @@ plainto_tsquery('simple', %(q)s))
                    ORDER BY c.page_id, d) best
                  JOIN pages p ON p.id = best.page_id
                  ORDER BY best.d LIMIT {PER_PAGE + 1} OFFSET %(start)s"""
    else:
        sql = f"""SELECT p.url, p.title, p.host, p.page_age, p.description FROM pages p
                  WHERE p.id IN (SELECT p.id FROM pages p {joins} WHERE {' AND '.join(where)})
                  ORDER BY p.page_age DESC NULLS LAST LIMIT {PER_PAGE + 1} OFFSET %(start)s"""
    params["start"] = start
    cur.execute(sql, params)
    rows = cur.fetchall()
    out = "".join(result_row(*r) for r in rows[:PER_PAGE])
    if len(rows) > PER_PAGE:
        out += f'<nav class="more"><a href="?{urlencode(dict(q=q, f=f, site=site, start=start + PER_PAGE))}">More</a></nav>'
    return out or '<div class="r">No pages</div>'


def result_row(url, title, host, page_age, text):
    snippet = " ".join((text or "").split())[:240]
    date = f" · {page_age:%Y-%m-%d}" if page_age else ""
    return (f'<div class="r"><a href="{e(url)}" rel="noopener">{e(title or url)}</a>'
            f'<div class="u">{e(host)}{date}</div><p>{e(snippet)}</p></div>')


def browse(cur, slug, key, values):
    out = ""
    if slug == "gp-theses":
        cur.execute("""SELECT f.host, f.name, count(p.id) FROM funds f LEFT JOIN pages p ON p.host = f.host
                       GROUP BY f.host, f.name ORDER BY lower(f.name)""")
        funds = cur.fetchall()
        out += f'<h2>Funds <span class="n">{len(funds):,}</span></h2><div class="facets">' + "".join(
            f'<a href="?{urlencode(dict(site=h))}">{e(n)} <span class="n">{c:,}</span></a>' for h, n, c in funds) + "</div>"
    if values:
        out += f'<h2>{e(key.title())}</h2><div class="facets">' + "".join(
            f'<a href="?{urlencode(dict(f=v))}">{e(v)} <span class="n">{c:,}</span></a>' for v, c in values) + "</div>"
    return out
