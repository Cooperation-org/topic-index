"""Create and refresh the summaries the page reads: .venv/bin/python knowledge_graph/rollup.py [view ...]"""
import sys

import kg

VIEWS = ("place_country", "flow_pairs", "flow_sectors", "datasets", "place_datasets")  # datasets reads the two before it


def main():
    with kg.ti.connect(owner=True) as conn, conn.cursor() as cur:
        conn.autocommit = True
        cur.execute((kg.HERE / "rollup.sql").read_text())
        cur.execute("GRANT SELECT ON ALL TABLES IN SCHEMA kg TO topic_index_user")
        for v in sys.argv[1:] or VIEWS:
            cur.execute("REFRESH MATERIALIZED VIEW kg.%s" % v)
            print("refreshed", v, flush=True)
        cur.execute("""SELECT pg_size_pretty(sum(pg_total_relation_size(c.oid))) FROM pg_class c
                       JOIN pg_namespace n ON n.oid = c.relnamespace
                       WHERE n.nspname IN ('kg', 'kg_raw') AND c.relkind IN ('r', 'm')""")
        print("knowledge graph size", cur.fetchone()[0])


if __name__ == "__main__":
    main()
