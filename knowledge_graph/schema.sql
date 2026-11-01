-- World economy as a graph. Nodes: places, sectors, entities. Edges: flows (place to place),
-- stats (a number about a place), links (entity to entity or place). Every number names its source.
CREATE SCHEMA IF NOT EXISTS kg;
GRANT USAGE ON SCHEMA kg TO topic_index_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA kg GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO topic_index_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA kg GRANT USAGE, SELECT ON SEQUENCES TO topic_index_user;

CREATE TABLE IF NOT EXISTS kg.sources (
    id          smallserial PRIMARY KEY,
    slug        text UNIQUE NOT NULL,
    name        text NOT NULL,
    publisher   text,
    url         text,                     -- page a person reads
    data_url    text,                     -- bulk file or API
    about       text,                     -- what it holds, in one line
    kinds       text[] NOT NULL DEFAULT '{}',  -- flows, stats, entities, links, pages
    coverage    text,                     -- places, years, detail level
    access      text,                     -- open, free-key, registration, paid
    license     text,
    status      text NOT NULL DEFAULT 'listed'
                CHECK (status IN ('listed', 'loading', 'loaded', 'failed', 'skipped')),
    status_note text,                     -- why failed or skipped
    row_count   bigint,
    found_by    text,                     -- survey, ad-hoc, a person
    added_at    timestamptz NOT NULL DEFAULT now(),
    loaded_at   timestamptz
);

CREATE TABLE IF NOT EXISTS kg.places (
    id         serial PRIMARY KEY,
    code       text UNIQUE NOT NULL,      -- PAK, PK.02, US.AZ, US.AZ.013, gn:184745, region:asia
    name       text NOT NULL,
    kind       text NOT NULL CHECK (kind IN ('world', 'region', 'country', 'admin1', 'admin2', 'city', 'other')),
    parent_id  int REFERENCES kg.places(id),
    iso2       text,
    iso3       text,
    m49        int,                       -- UN numeric code, also ISO numeric
    geonameid  int,
    lat        double precision,
    lon        double precision,
    population bigint,
    alt_names  text[]
);
CREATE INDEX IF NOT EXISTS places_name_trgm ON kg.places USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS places_parent ON kg.places (parent_id);
CREATE INDEX IF NOT EXISTS places_kind ON kg.places (kind);
CREATE INDEX IF NOT EXISTS places_m49 ON kg.places (m49);

CREATE TABLE IF NOT EXISTS kg.sectors (
    id        serial PRIMARY KEY,
    scheme    text NOT NULL,              -- each classification keeps its own tree: hs, isic, naics, fao, ...
    code      text NOT NULL,
    name      text NOT NULL,
    parent_id int REFERENCES kg.sectors(id),
    path      text,                       -- hs/11/52/5201/520100, for prefix rollups
    UNIQUE (scheme, code)
);
CREATE INDEX IF NOT EXISTS sectors_name_trgm ON kg.sectors USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS sectors_path ON kg.sectors (path text_pattern_ops);

ALTER TABLE kg.sectors ADD COLUMN IF NOT EXISTS aggregate boolean NOT NULL DEFAULT false;  -- a published sum of other rows in its scheme

CREATE TABLE IF NOT EXISTS kg.measures (
    id     smallserial PRIMARY KEY,
    slug   text UNIQUE NOT NULL,          -- goods_exports_usd, fdi_position_usd, gdp_usd
    name   text NOT NULL,
    unit   text NOT NULL,                 -- USD, USD_2017, tonnes, people, MW
    family text NOT NULL,                 -- goods_trade, services_trade, investment, banking, aid, remittances, arms, migration, freight, output, employment, production, energy, waste, ...
    about  text                           -- what "from" and "to" mean for a flow, and how it was counted
);

ALTER TABLE kg.measures ADD COLUMN IF NOT EXISTS listed boolean NOT NULL DEFAULT true;  -- offered as a filter on the page

CREATE TABLE IF NOT EXISTS kg.flows (
    source_id  smallint NOT NULL REFERENCES kg.sources(id),
    measure_id smallint NOT NULL REFERENCES kg.measures(id),
    year       smallint NOT NULL,
    from_place int NOT NULL REFERENCES kg.places(id),
    to_place   int NOT NULL REFERENCES kg.places(id),
    sector_id  int REFERENCES kg.sectors(id),
    value      double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS flows_from ON kg.flows (from_place, measure_id, year);
CREATE INDEX IF NOT EXISTS flows_to ON kg.flows (to_place, measure_id, year);
CREATE INDEX IF NOT EXISTS flows_sector ON kg.flows (sector_id, year);
CREATE INDEX IF NOT EXISTS flows_source ON kg.flows (source_id);

CREATE TABLE IF NOT EXISTS kg.stats (
    source_id  smallint NOT NULL REFERENCES kg.sources(id),
    measure_id smallint NOT NULL REFERENCES kg.measures(id),
    year       smallint NOT NULL,
    place_id   int NOT NULL REFERENCES kg.places(id),
    sector_id  int REFERENCES kg.sectors(id),
    value      double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS stats_place ON kg.stats (place_id, measure_id, year);
CREATE INDEX IF NOT EXISTS stats_sector ON kg.stats (sector_id, year);
CREATE INDEX IF NOT EXISTS stats_measure ON kg.stats (measure_id, year);
CREATE INDEX IF NOT EXISTS stats_source ON kg.stats (source_id);

-- Organizations and physical sites: companies, agencies, power plants, ports, mines.
CREATE TABLE IF NOT EXISTS kg.entities (
    id        bigserial PRIMARY KEY,
    source_id smallint NOT NULL REFERENCES kg.sources(id),
    ext_id    text NOT NULL,              -- the source's own id: LEI, Q-number, plant id
    name      text NOT NULL,
    kind      text NOT NULL,              -- company, government, ngo, power_plant, port, mine, factory, ...
    place_id  int REFERENCES kg.places(id),
    lat       double precision,
    lon       double precision,
    sector_id int REFERENCES kg.sectors(id),
    url       text,
    attrs     jsonb,
    UNIQUE (source_id, ext_id)
);
CREATE INDEX IF NOT EXISTS entities_name_trgm ON kg.entities USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS entities_place ON kg.entities (place_id, kind);
CREATE INDEX IF NOT EXISTS entities_kind ON kg.entities (kind);
CREATE INDEX IF NOT EXISTS entities_geo ON kg.entities (lat, lon) WHERE lat IS NOT NULL;

-- An entity related to another entity or a place: owns, funds, contracted_in, lobbies, operates_in.
CREATE TABLE IF NOT EXISTS kg.links (
    source_id   smallint NOT NULL REFERENCES kg.sources(id),
    kind        text NOT NULL,
    from_entity bigint NOT NULL REFERENCES kg.entities(id),
    to_entity   bigint REFERENCES kg.entities(id),
    to_place    int REFERENCES kg.places(id),
    sector_id   int REFERENCES kg.sectors(id),
    year        smallint,
    value       double precision,
    unit        text,
    attrs       jsonb,
    CHECK (to_entity IS NOT NULL OR to_place IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS links_from ON kg.links (from_entity, kind);
CREATE INDEX IF NOT EXISTS links_to_entity ON kg.links (to_entity, kind);
CREATE INDEX IF NOT EXISTS links_to_place ON kg.links (to_place, kind);
CREATE INDEX IF NOT EXISTS links_source ON kg.links (source_id);

-- Parts of a source already stored, so a killed load restarts where it stopped.
CREATE TABLE IF NOT EXISTS kg.load_log (
    source_id smallint NOT NULL REFERENCES kg.sources(id),
    part      text NOT NULL,
    row_count bigint,
    done_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, part)
);
