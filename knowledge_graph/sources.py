"""The catalog of data sources, loaded or not.

  .venv/bin/python knowledge_graph/sources.py add <slug> --name N [--publisher P --url U --data-url D --about A
        --kinds flows,stats --coverage C --access open --license L --found-by survey]
  .venv/bin/python knowledge_graph/sources.py list [--status listed] [--search word]
"""
import argparse

import kg


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("slug")
    add.add_argument("--name", required=True)
    for f in ("publisher", "url", "data-url", "about", "coverage", "access", "license", "found-by", "kinds"):
        add.add_argument("--" + f)
    ls = sub.add_parser("list")
    ls.add_argument("--status")
    ls.add_argument("--search")
    args = ap.parse_args()
    with kg.connect() as conn, conn.cursor() as cur:
        if args.cmd == "add":
            fields = {k: v for k, v in vars(args).items() if k not in ("cmd", "slug") and v is not None}
            if "kinds" in fields:
                fields["kinds"] = fields["kinds"].split(",")
            print(kg.add_source(cur, args.slug, **fields))
        else:
            cur.execute("""SELECT status, slug, access, row_count, name FROM kg.sources
                           WHERE (%(s)s::text IS NULL OR status = %(s)s)
                             AND (%(q)s::text IS NULL OR name ILIKE %(q)s OR about ILIKE %(q)s)
                           ORDER BY status, slug""",
                        {"s": args.status, "q": "%%%s%%" % args.search if args.search else None})
            for row in cur.fetchall():
                print("\t".join("" if x is None else str(x) for x in row))


if __name__ == "__main__":
    main()
