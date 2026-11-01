-- One store of full pages; topics and topic-specific tables sit on top.
CREATE TABLE IF NOT EXISTS pages (
    id          bigserial PRIMARY KEY,
    url         text UNIQUE NOT NULL,
    host        text NOT NULL,
    title       text,
    description text,
    markdown    text,
    page_age    timestamptz,
    source      text NOT NULL,            -- ydc-search, ydc-site, import:<name>
    fetched_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pages_host ON pages (host);

CREATE TABLE IF NOT EXISTS chunks (
    id         bigserial PRIMARY KEY,
    page_id    bigint NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    idx        int NOT NULL,
    text       text NOT NULL,
    tsv        tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
    embedding  vector(384),               -- all-MiniLM-L6-v2, same model as abra
    UNIQUE (page_id, idx)
);
CREATE INDEX IF NOT EXISTS chunks_tsv ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS topics (
    slug        text PRIMARY KEY,
    name        text NOT NULL,
    description text
);

-- Every search sent, so a rerun skips what is already done.
CREATE TABLE IF NOT EXISTS queries (
    id         bigserial PRIMARY KEY,
    topic      text NOT NULL REFERENCES topics(slug),
    query      text NOT NULL,
    facets     jsonb NOT NULL DEFAULT '{}',  -- e.g. {"country": "Kenya"}
    results    int,
    run_at     timestamptz,
    UNIQUE (topic, query)
);

CREATE TABLE IF NOT EXISTS page_topics (
    page_id  bigint NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    topic    text NOT NULL REFERENCES topics(slug),
    query_id bigint REFERENCES queries(id) ON DELETE SET NULL,
    rank     int,
    UNIQUE NULLS NOT DISTINCT (page_id, topic, query_id)
);
CREATE INDEX IF NOT EXISTS page_topics_topic ON page_topics (topic);

-- gp-theses: one row per fund site; its own pages are pages with the same host.
CREATE TABLE IF NOT EXISTS funds (
    host        text PRIMARY KEY,
    name        text,
    found_via   text NOT NULL,            -- page url or import name
    crawled_at  timestamptz
);
