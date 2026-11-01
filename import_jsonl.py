"""Load an existing crawl, one JSON object per line with url/title/text, into the store.

  .venv/bin/python import_jsonl.py <file.jsonl> <topic> <source-name> [--funds]

--funds also records each line's "entity" as a fund (gp-theses), keyed by site host.
"""
import json
import sys

import ti


def main():
    path, topic, name = sys.argv[1:4]
    as_funds = "--funds" in sys.argv[4:]
    with ti.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM topics WHERE slug = %s", (topic,))
        if not cur.fetchone():
            raise SystemExit("unknown topic %s; run its topic file first" % topic)
        n = 0
        for line in open(path):
            r = json.loads(line)
            page_id = ti.store_page(cur, r["url"], r.get("title"), r.get("entity"), r["text"], None,
                                    "import:" + name)
            ti.tag(cur, page_id, topic)
            if as_funds and r.get("entity"):
                cur.execute("""INSERT INTO funds (host, name, found_via) VALUES (%s, %s, %s)
                               ON CONFLICT (host) DO NOTHING""",
                            (ti.host_of(r["url"]), r["entity"], "import:" + name))
            conn.commit()
            n += 1
        print("imported %d pages" % n)


if __name__ == "__main__":
    main()
