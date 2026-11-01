# Knowledge graph

How money, goods and influence move in the world, by place and sector. Lives in database `topic_index` on VM 100, schema `kg`, next to the web pages of topic-index. Served as the Money Map at https://demos.linkedtrust.us/money-map/.

## Data

| Table | Holds |
|---|---|
| `kg.sources` | Every data source known, loaded or only listed |
| `kg.places` | World, UN regions, countries, GeoNames divisions, cities over 15,000 people |
| `kg.sectors` | Each classification's own tree: hs, isic, naics, fao, sctg and others |
| `kg.measures` | What a number is, its unit, and what from and to mean |
| `kg.flows` | Place to place, by year and sector |
| `kg.stats` | A number about a place, by year and sector |
| `kg.entities`, `kg.links` | Organizations and sites, and who owns, funds or contracts whom |
| `kg_raw.<slug>` | Tables pulled ad hoc, all text columns |
| `kg_app.asks` | Questions asked in the chat, with tool calls and token counts |

Schema: `schema.sql`. Summaries the page reads: `rollup.sql`.

## Run

Every dataset is one restartable file in `loaders/`. Nothing is loaded by hand.

```sh
cd knowledge_graph
psql "$OWNER_DATABASE_URL" -f schema.sql
../.venv/bin/python load.py places           # first; everything refers to places
../.venv/bin/python load.py                  # all loaders; parts already stored are skipped
../.venv/bin/python rollup.py                # refresh summaries after any load
../.venv/bin/python sources.py list --status listed
../.venv/bin/python sources.py add <slug> --name "..." --url "..." --about "..."
../.venv/bin/python adhoc.py pull <slug> <url> --name "..."   # a CSV, TSV, XLSX, JSON list, or zip into kg_raw
../.venv/bin/python adhoc.py reload          # pull every ad hoc table again
../.venv/bin/python build_static.py          # country shapes for the page
```

Add a dataset: copy a loader, use `kg.Loader`, wrap each year or file in `with l.part(name):` guarded by `if not l.done(name):`, so a kill loses nothing.

## Web

`web/server.py` (FastAPI, uvicorn :8056, `money-map.service`), `web/agent.py` (chat), `web/static/index.html`. `.env` needs `DATABASE_URL`, `OWNER_DATABASE_URL`, `ANTHROPIC_API_KEY`, `KG_SESSION_SECRET`, `KG_ASK_PASSWORD`. The map and filters are public; the chat needs the team password and allows 200 questions a day. The chat stores pages it finds under topic `ad-hoc` and tables it pulls under `kg_raw`.
