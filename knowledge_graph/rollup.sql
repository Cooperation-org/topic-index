-- Summaries the page reads. Rerun with rollup.py after a load. A source may give a total row
-- (sector NULL) and sector rows; the total wins so nothing counts twice.
CREATE SCHEMA IF NOT EXISTS kg_app;
GRANT USAGE ON SCHEMA kg_app TO topic_index_user;
CREATE TABLE IF NOT EXISTS kg_app.asks (
    id         bigserial PRIMARY KEY,
    asked_by   text,
    question   text NOT NULL,
    answer     text,
    tool_calls jsonb,
    tokens_in  int,
    tokens_out int,
    asked_at   timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE ON kg_app.asks TO topic_index_user;
GRANT USAGE, SELECT ON SEQUENCE kg_app.asks_id_seq TO topic_index_user;
CREATE SCHEMA IF NOT EXISTS kg_raw;   -- tables pulled ad hoc, one per source, all columns text
GRANT USAGE ON SCHEMA kg_raw TO topic_index_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA kg_raw GRANT SELECT ON TABLES TO topic_index_user;

-- A published total is a row with no sector, so it never adds to its own parts.
UPDATE kg.stats SET sector_id = NULL WHERE sector_id IN (SELECT id FROM kg.sectors WHERE upper(code) = 'TOTAL');
UPDATE kg.flows SET sector_id = NULL WHERE sector_id IN (SELECT id FROM kg.sectors WHERE upper(code) = 'TOTAL' OR (scheme = 'ebops' AND code = 'S'));
-- FAOSTAT item codes from 1700 are its own groupings of other items.
UPDATE kg.sectors SET aggregate = true WHERE scheme = 'fao' AND code ~ '^[0-9]+$' AND code::int >= 1700 AND NOT aggregate;
-- USDA publishes hundreds of measures; the page offers the ones that say how big a crop is.
UPDATE kg.measures SET listed = false WHERE slug LIKE 'nass\_%' AND listed
   AND slug NOT IN ('nass_production_usd', 'nass_sales_usd', 'nass_area_harvested_acres', 'nass_production_480_lb_bales');

CREATE MATERIALIZED VIEW IF NOT EXISTS kg.flow_pairs AS
SELECT source_id, measure_id, year, from_place, to_place,
       COALESCE(sum(value) FILTER (WHERE sector_id IS NULL), sum(value)) AS value
FROM kg.flows WHERE sector_id IS NULL OR sector_id NOT IN (SELECT id FROM kg.sectors WHERE aggregate)
GROUP BY 1, 2, 3, 4, 5 WITH NO DATA;
CREATE UNIQUE INDEX IF NOT EXISTS flow_pairs_key ON kg.flow_pairs (source_id, measure_id, year, from_place, to_place);
CREATE INDEX IF NOT EXISTS flow_pairs_to ON kg.flow_pairs (source_id, measure_id, year, to_place);

CREATE MATERIALIZED VIEW IF NOT EXISTS kg.flow_sectors AS
SELECT source_id, measure_id, year, sector_id, sum(value) AS value
FROM kg.flows WHERE sector_id IS NOT NULL AND sector_id NOT IN (SELECT id FROM kg.sectors WHERE aggregate)
GROUP BY 1, 2, 3, 4 WITH NO DATA;
CREATE UNIQUE INDEX IF NOT EXISTS flow_sectors_key ON kg.flow_sectors (source_id, measure_id, year, sector_id);

CREATE MATERIALIZED VIEW IF NOT EXISTS kg.datasets AS
SELECT source_id, measure_id, kind, min(year) AS min_year, max(year) AS max_year,
       bool_or(has_sector) AS has_sector, array_agg(DISTINCT year ORDER BY year) AS years
FROM (SELECT DISTINCT source_id, measure_id, 'flow' AS kind, year, false AS has_sector FROM kg.flow_pairs
      UNION SELECT DISTINCT source_id, measure_id, 'flow', year, true FROM kg.flow_sectors
      UNION SELECT DISTINCT source_id, measure_id, 'stat', year, sector_id IS NOT NULL FROM kg.stats) d
GROUP BY 1, 2, 3 WITH NO DATA;
CREATE UNIQUE INDEX IF NOT EXISTS datasets_key ON kg.datasets (source_id, measure_id, kind);

CREATE MATERIALIZED VIEW IF NOT EXISTS kg.place_datasets AS
SELECT DISTINCT from_place AS place_id, source_id, measure_id, 'flow' AS kind FROM kg.flow_pairs
UNION SELECT DISTINCT to_place, source_id, measure_id, 'flow' FROM kg.flow_pairs
UNION SELECT DISTINCT place_id, source_id, measure_id, 'stat' FROM kg.stats WITH NO DATA;
CREATE UNIQUE INDEX IF NOT EXISTS place_datasets_key ON kg.place_datasets (place_id, source_id, measure_id, kind);

CREATE MATERIALIZED VIEW IF NOT EXISTS kg.place_country AS
WITH RECURSIVE up AS (SELECT id AS place_id, id AS at, parent_id, kind FROM kg.places
                      UNION ALL SELECT u.place_id, p.id, p.parent_id, p.kind FROM up u JOIN kg.places p ON p.id = u.parent_id
                      WHERE u.kind <> 'country')
SELECT place_id, at AS country_id FROM up WHERE kind = 'country' WITH NO DATA;
CREATE UNIQUE INDEX IF NOT EXISTS place_country_key ON kg.place_country (place_id);
CREATE INDEX IF NOT EXISTS place_country_country ON kg.place_country (country_id);
