"""Shared pieces: database, You.com search, storing pages, chunking."""
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import psycopg

HERE = Path(__file__).resolve().parent
SEARCH_URL = "https://api.you.com/v1/search"
YDC_CONF = "/opt/shared/tools/ydc.conf"
CHUNK_WORDS = 400
CHUNK_OVERLAP = 50


def load_env():
    for line in (HERE / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def connect(owner=False):
    load_env()
    return psycopg.connect(os.environ["OWNER_DATABASE_URL" if owner else "DATABASE_URL"])


def ydc_key():
    if os.environ.get("YDC_API_KEY"):
        return os.environ["YDC_API_KEY"]
    for path in (Path("~/.env").expanduser(), Path(YDC_CONF)):
        if path.exists():
            for line in path.read_text().splitlines():
                m = re.match(r"\s*(?:export\s+)?YDC_API_KEY\s*=\s*(.+)", line)
                if m:
                    return m.group(1).strip().strip("'\"")
    raise SystemExit("no YDC_API_KEY in env, ~/.env or %s" % YDC_CONF)


def search(query, count=50, tries=3):
    """You.com web search with full-page markdown for each result."""
    body = {"query": query, "count": count,
            "extraction": {"extraction_mode": "full_page", "extraction_source": "blend"}}
    req = urllib.request.Request(SEARCH_URL, data=json.dumps(body).encode(), method="POST")
    req.add_header("X-API-Key", ydc_key())
    req.add_header("Content-Type", "application/json")
    # Cloudflare in front of api.you.com rejects the default urllib agent.
    req.add_header("User-Agent", "curl/8.5.0")
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp).get("results", {}).get("web", [])
        except urllib.error.HTTPError as e:
            if e.code in (401, 402, 403):
                raise SystemExit("ydc HTTP %s: %s" % (e.code, e.read().decode()[:300]))
            err = e
        except (urllib.error.URLError, TimeoutError) as e:
            err = e
        time.sleep(5 * (attempt + 1))
    raise RuntimeError("ydc search failed: %s" % err)


def host_of(url):
    return urlparse(url).netloc.lower().removeprefix("www.")


def chunks_of(text):
    words = text.split()
    step = CHUNK_WORDS - CHUNK_OVERLAP
    return [" ".join(words[i:i + CHUNK_WORDS]) for i in range(0, max(len(words), 1), step)
            if words[i:i + CHUNK_WORDS]]


def store_page(cur, url, title, description, markdown, page_age, source):
    """Insert or refresh a page and its chunks; returns page id."""
    title, description, markdown = (x.replace("\x00", "") if x else x for x in (title, description, markdown))
    cur.execute(
        """INSERT INTO pages (url, host, title, description, markdown, page_age, source)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (url) DO UPDATE SET
             title = EXCLUDED.title, description = EXCLUDED.description,
             markdown = COALESCE(EXCLUDED.markdown, pages.markdown),
             page_age = EXCLUDED.page_age, fetched_at = now()
           WHERE EXCLUDED.markdown IS NOT NULL AND EXCLUDED.markdown IS DISTINCT FROM pages.markdown
           RETURNING id, (xmax = 0) AS inserted""",
        (url, host_of(url), title, description, markdown, page_age, source))
    row = cur.fetchone()
    if row is None:  # unchanged page already stored
        cur.execute("SELECT id FROM pages WHERE url = %s", (url,))
        return cur.fetchone()[0]
    page_id = row[0]
    cur.execute("DELETE FROM chunks WHERE page_id = %s", (page_id,))
    text = "\n".join(x for x in (title, description, markdown) if x)
    for i, c in enumerate(chunks_of(text)):
        cur.execute("INSERT INTO chunks (page_id, idx, text) VALUES (%s, %s, %s)", (page_id, i, c))
    return page_id


def tag(cur, page_id, topic, query_id=None, rank=None):
    cur.execute("""INSERT INTO page_topics (page_id, topic, query_id, rank) VALUES (%s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""", (page_id, topic, query_id, rank))


def store_results(cur, results, topic, query_id, source):
    for rank, r in enumerate(results):
        md = (r.get("contents") or {}).get("markdown")
        page_id = store_page(cur, r["url"], r.get("title"), r.get("description"), md,
                             r.get("page_age"), source)
        tag(cur, page_id, topic, query_id, rank)
