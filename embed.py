"""Fill chunk embeddings that are still empty, a batch at a time.

  .venv/bin/python embed.py            (once)
  .venv/bin/python embed.py --follow   (keep going as searches add chunks)
"""
import argparse
import time

from fastembed import TextEmbedding

import ti

MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # same model as abra, 384 dims
BATCH = 256


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--follow", action="store_true")
    args = ap.parse_args()
    # Two threads: this VM is shared.
    model = TextEmbedding(MODEL, threads=2)
    with ti.connect() as conn, conn.cursor() as cur:
        while True:
            cur.execute("SELECT id, text FROM chunks WHERE embedding IS NULL ORDER BY id LIMIT %s", (BATCH,))
            rows = cur.fetchall()
            if not rows:
                if not args.follow:
                    break
                time.sleep(60)
                continue
            vecs = model.embed([t for _, t in rows])
            for (cid, _), v in zip(rows, vecs):
                cur.execute("UPDATE chunks SET embedding = %s::vector WHERE id = %s", (str(v.tolist()), cid))
            conn.commit()
            print("embedded %d" % len(rows), flush=True)


if __name__ == "__main__":
    main()
