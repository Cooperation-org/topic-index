"""Pull a table from a URL into kg_raw.<slug> and record it in the catalog. Any CSV, TSV, XLSX, JSON list, or a zip holding one.

  .venv/bin/python knowledge_graph/adhoc.py pull <slug> <url> --name "..." [--about "..."] [--publisher "..."]
  .venv/bin/python knowledge_graph/adhoc.py reload     # pull every ad hoc source again
"""
import argparse
import csv
import io
import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.request
import zipfile

import kg

MAX_BYTES = 500_000_000
BATCH = 5000


def check_url(url):
    """Public http(s) only: this runs on a request from the chat."""
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("http or https URL only")
    for info in socket.getaddrinfo(u.hostname, None):
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError("not a public address: %s" % u.hostname)


def fetch(url):
    check_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": kg.UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("over %d MB: write a loader for this one" % (MAX_BYTES // 1_000_000))
    return data


def rows_of(data, url):
    """(header, rows) from bytes, by content rather than by trusting the extension."""
    if data[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(data))
        names = z.namelist()
        if "xl/workbook.xml" in names:
            import openpyxl
            ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
            it = ws.iter_rows(values_only=True)
            head = next(r for r in it if sum(c is not None for c in r) > 1)
            return [str(c or "") for c in head], (["" if c is None else str(c) for c in r] for r in it)
        tables = [n for n in names if re.search(r"\.(csv|tsv|txt)$", n, re.I)]
        if not tables:
            raise ValueError("no table in zip: %s" % names[:10])
        biggest = max(tables, key=lambda n: z.getinfo(n).file_size)
        return rows_of(z.read(biggest), biggest)
    text = data.decode("utf-8-sig", errors="replace")
    if text.lstrip()[:1] in "[{":
        obj = json.loads(text)
        if isinstance(obj, dict):
            obj = next((v for v in obj.values() if isinstance(v, list) and v and isinstance(v[0], dict)), None)
        if not obj:
            raise ValueError("no list of records in JSON")
        head = list({k: 1 for r in obj[:1000] for k in r})
        return head, ([json.dumps(v) if isinstance(v, (dict, list)) else "" if v is None else str(v)
                       for v in (r.get(k) for k in head)] for r in obj)
    if text.lstrip()[:1] == "<":
        raise ValueError("got a web page, not a table")
    delim = "\t" if text.split("\n", 1)[0].count("\t") > text.split("\n", 1)[0].count(",") else ","
    rd = csv.reader(io.StringIO(text), delimiter=delim)
    return next(rd), rd


def column_names(head):
    seen, out = {}, []
    for i, h in enumerate(head):
        c = re.sub(r"[^a-z0-9]+", "_", str(h).lower()).strip("_")[:50] or "col%d" % i
        seen[c] = seen.get(c, 0) + 1
        out.append(c if seen[c] == 1 else "%s_%d" % (c, seen[c]))
    return out


def pull(slug, url, **fields):
    slug = re.sub(r"[^a-z0-9_]+", "_", slug.lower())[:50]
    head, rows = rows_of(fetch(url), url)
    cols = column_names(head)
    with kg.ti.connect(owner=True) as conn, conn.cursor() as cur:
        fields = {"found_by": "ad-hoc", "kinds": ["table"], "data_url": url, **fields}
        sid = kg.add_source(cur, slug, **fields)
        cur.execute('DROP TABLE IF EXISTS kg_raw."%s"' % slug)
        cur.execute('CREATE TABLE kg_raw."%s" (%s)' % (slug, ", ".join('"%s" text' % c for c in cols)))
        n = 0
        with cur.copy('COPY kg_raw."%s" FROM STDIN' % slug) as c:
            for r in rows:
                r = [(x or "").replace("\x00", "") for x in list(r)[:len(cols)]]
                c.write_row(r + [None] * (len(cols) - len(r)))
                n += 1
        cur.execute('GRANT SELECT ON kg_raw."%s" TO topic_index_user' % slug)
        cur.execute("""UPDATE kg.sources SET status = 'loaded', status_note = %s, row_count = %s, loaded_at = now()
                       WHERE id = %s""", ('table kg_raw."%s"' % slug, n, sid))
    return {"table": 'kg_raw."%s"' % slug, "columns": cols, "rows": n}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pull")
    p.add_argument("slug")
    p.add_argument("url")
    p.add_argument("--name", required=True)
    p.add_argument("--about")
    p.add_argument("--publisher")
    sub.add_parser("reload")
    args = ap.parse_args()
    if args.cmd == "pull":
        extra = {k: getattr(args, k) for k in ("about", "publisher") if getattr(args, k)}
        print(pull(args.slug, args.url, name=args.name, **extra))
    else:
        with kg.connect() as conn:
            for slug, url, name in conn.execute(
                    "SELECT slug, data_url, name FROM kg.sources WHERE found_by = 'ad-hoc' AND status = 'loaded'").fetchall():
                print(slug, pull(slug, url, name=name)["rows"])


if __name__ == "__main__":
    main()
