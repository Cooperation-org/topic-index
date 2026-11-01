"""Run a topic's searches and store every result page as it arrives.

  .venv/bin/python run.py topics/gp-theses.yaml [--limit N]

Queries already run are skipped, so a killed run restarts where it stopped.
"""
import argparse
import itertools
import json
import sys

import yaml

import ti


def values_of(v):
    """A list as given, or a name of a shared list in topics/_<name>.yaml."""
    return yaml.safe_load(open(ti.HERE / "topics" / ("_%s.yaml" % v))) if isinstance(v, str) else v


def expand(spec):
    """(query, facets) pairs: the literal queries, then every template x value set."""
    for q in spec.get("queries", []):
        yield q, {}
    for block in spec.get("expand", []):
        names = list(block["values"])
        for combo in itertools.product(*(values_of(block["values"][n]) for n in names)):
            facets = dict(zip(names, combo))
            for t in block["templates"]:
                yield t.format(**facets), facets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topic_file")
    ap.add_argument("--limit", type=int, help="stop after this many new queries")
    ap.add_argument("--count", type=int, default=50, help="results per query")
    args = ap.parse_args()
    spec = yaml.safe_load(open(args.topic_file))
    slug = spec["slug"]

    with ti.connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO topics (slug, name, description) VALUES (%s, %s, %s)
                       ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name,
                       description = EXCLUDED.description""",
                    (slug, spec["name"], spec.get("description")))
        conn.commit()
        done = 0
        for query, facets in expand(spec):
            cur.execute("""INSERT INTO queries (topic, query, facets) VALUES (%s, %s, %s)
                           ON CONFLICT (topic, query) DO UPDATE SET facets = EXCLUDED.facets
                           RETURNING id, run_at""", (slug, query, json.dumps(facets)))
            qid, run_at = cur.fetchone()
            conn.commit()
            if run_at:
                continue
            if args.limit is not None and done >= args.limit:
                break
            try:
                results = ti.search(query, count=args.count)
            except RuntimeError as e:
                print("skip %r: %s" % (query, e), file=sys.stderr, flush=True)
                continue
            ti.store_results(cur, results, slug, qid, "ydc-search")
            cur.execute("UPDATE queries SET results = %s, run_at = now() WHERE id = %s",
                        (len(results), qid))
            conn.commit()
            done += 1
            print("%s  %3d  %s" % (slug, len(results), query), flush=True)


if __name__ == "__main__":
    main()
