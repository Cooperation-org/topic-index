"""gp-theses: find fund sites among stored pages, then pull each fund's own thesis pages.

  .venv/bin/python funds.py discover    record hosts whose pages speak as a fund ("we invest in ...")
  .venv/bin/python funds.py crawl       one site: search per fund not yet crawled; stores as it goes
"""
import re
import sys
from urllib.parse import urlparse

import ti

TOPIC = "gp-theses"
# First-person statements a fund makes about itself; directory and advice pages rarely use two.
FUND_VOICE = re.compile(r"\b(we invest in|we back|our investment thesis|our thesis|our portfolio companies|"
                        r"we partner with founders|we lead (?:seed|pre-seed|series a)|our fund invests|"
                        r"check sizes? (?:of|from|between)|we write checks)\b", re.I)
# A fund describes itself on its home, about or thesis pages, not in articles.
SELF_PATH = re.compile(r"^/?$|about|thesis|approach|focus|strategy|invest|criteria|who-we|what-we|philosophy|fund", re.I)
ARTICLE_PATH = re.compile(r"/(blog|news|insights|articles?|posts?|resources|learn|guides?|library)/|/\d{4}/", re.I)
SITE_QUERY = "site:{host} investment thesis focus what we invest in criteria"


def discover(cur):
    cur.execute("""SELECT p.host, p.url, p.title, p.markdown FROM pages p
                   JOIN page_topics t ON t.page_id = p.id AND t.topic = %s
                   WHERE p.markdown IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM funds f WHERE f.host = p.host)""", (TOPIC,))
    found = 0
    for host, url, title, md in cur.fetchall():
        path = urlparse(url).path
        if (SELF_PATH.search(path) and not ARTICLE_PATH.search(path)
                and len(set(m.lower() for m in FUND_VOICE.findall(md))) >= 2):
            cur.execute("""INSERT INTO funds (host, name, found_via) VALUES (%s, %s, %s)
                           ON CONFLICT (host) DO NOTHING""", (host, (title or host)[:200], url))
            found += cur.rowcount
    print("new funds: %d" % found)


def crawl(conn, cur):
    cur.execute("SELECT host FROM funds WHERE crawled_at IS NULL ORDER BY host")
    for (host,) in cur.fetchall():
        try:
            results = ti.search(SITE_QUERY.format(host=host), count=20)
        except RuntimeError as e:
            print("skip %s: %s" % (host, e), file=sys.stderr, flush=True)
            continue
        results = [r for r in results if ti.host_of(r["url"]).endswith(host)]
        ti.store_results(cur, results, TOPIC, None, "ydc-site")
        cur.execute("UPDATE funds SET crawled_at = now() WHERE host = %s", (host,))
        conn.commit()
        print("%3d  %s" % (len(results), host), flush=True)


if __name__ == "__main__":
    with ti.connect() as conn, conn.cursor() as cur:
        {"discover": lambda: discover(cur), "crawl": lambda: crawl(conn, cur)}[sys.argv[1]]()
        conn.commit()
