"""Search the store: semantic (pgvector) by default, --text for full-text.

  .venv/bin/python ask.py "employee ownership trust tax relief" [--topic employee-ownership-law] [-n 10]
"""
import argparse

from fastembed import TextEmbedding

import embed
import ti


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--topic")
    ap.add_argument("--text", action="store_true")
    ap.add_argument("-n", type=int, default=10)
    args = ap.parse_args()
    where = "AND EXISTS (SELECT 1 FROM page_topics t WHERE t.page_id = p.id AND t.topic = %(topic)s)" if args.topic else ""
    if args.text:
        order, params = "ts_rank(c.tsv, q) DESC", {}
        frm = ", plainto_tsquery('simple', %(q)s) q"
        where += " AND c.tsv @@ q"
    else:
        vec = next(TextEmbedding(embed.MODEL, threads=2).embed([args.query])).tolist()
        order, frm = "c.embedding <=> %(vec)s::vector", ""
        params = {"vec": str(vec)}
    params.update(q=args.query, topic=args.topic, n=args.n * 3)
    sql = f"""SELECT p.url, p.title, left(c.text, 200) FROM chunks c JOIN pages p ON p.id = c.page_id {frm}
              WHERE c.embedding IS NOT NULL {where} ORDER BY {order} LIMIT %(n)s"""
    with ti.connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        seen = set()
        for url, title, text in cur.fetchall():
            if url in seen or len(seen) >= args.n:
                continue
            seen.add(url)
            print("%s\n  %s\n  %s\n" % (title, url, text.replace("\n", " ")))


if __name__ == "__main__":
    main()
