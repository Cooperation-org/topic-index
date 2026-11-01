# topic-index

One store of full web pages, tagged by topic, searchable by meaning (pgvector) and by words (Postgres full text). Pages come from the You.com search API with full-page extraction; every result is kept, so the store grows with each topic and a page found for one topic serves the others.

Topic-specific tables sit on top of the shared pages. The first is `funds` for fund investment theses.

## Topics

| File | Topic |
|---|---|
| `topics/gp-theses.yaml` | What venture, impact and employee-ownership funds say they invest in |
| `topics/supply-chain-regulation.yaml` | Due diligence, traceability, forced-labour, deforestation and product passport rules, worldwide |
| `topics/employee-ownership-law.yaml` | Employee share plans, stock options, ownership trusts and worker cooperative law, by country |
| `topics/employment-law-cross-border.yaml` | Hiring, contractor classification, dismissal and payroll rules for teams across countries |

A topic file has literal `queries` and `expand` blocks (templates times value lists). `values: {country: countries}` uses the shared list in `topics/_countries.yaml`. The value used is stored on the query as `facets`, so pages can be filtered by country, sector or region.

## Data

Postgres `topic_index` on VM 100, schema in `schema.sql`.

| Table | Holds |
|---|---|
| `pages` | One row per URL: title, description, full markdown, source |
| `chunks` | ~400-word pieces of each page, with `tsv` and a 384-dim `embedding` (all-MiniLM-L6-v2, the model abra uses) |
| `topics` | Topic slugs and names |
| `queries` | Every search sent, with facets and result count; a rerun skips ones already run |
| `page_topics` | Which topic and query found each page, and its rank |
| `funds` | gp-theses: one row per fund site; its pages are the `pages` rows with that host |

## Run

```sh
python3 -m venv .venv && .venv/bin/pip install psycopg[binary] fastembed pyyaml
# .env: DATABASE_URL, OWNER_DATABASE_URL (not committed)
psql "$OWNER_DATABASE_URL" -f schema.sql

./fill.sh                                   # all topics, then fund sites; embeddings alongside
.venv/bin/python run.py topics/gp-theses.yaml --limit 10
.venv/bin/python funds.py discover          # fund sites among stored pages
.venv/bin/python funds.py crawl             # each fund's own thesis pages
.venv/bin/python embed.py                   # fill missing embeddings
.venv/bin/python import_jsonl.py corpus.jsonl gp-theses eo-fund-explorer --funds

.venv/bin/python ask.py "employee ownership trust tax relief" --topic employee-ownership-law
.venv/bin/python ask.py "EUDR" --text
```

The You.com key is read from `$YDC_API_KEY`, `~/.env` or `/opt/shared/tools/ydc.conf`.

## Web

`serve.py`: one page per topic with search (meaning, then words) and the topic's facet values to browse; gp-theses also lists fund sites. Runs as `tmp-topic-index.service` on port 8062, served at https://amebo.linkedtrust.us/topics/ until topics get their own domain.

## Cost

You.com search: $0.005 per call plus $0.001 per page crawled live (cached pages free). A 50-result query is at most $0.055.
