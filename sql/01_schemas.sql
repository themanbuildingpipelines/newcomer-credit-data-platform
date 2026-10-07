-- 01_schemas.sql
-- The four layers of the warehouse. Run as ncp_dev inside newcomer_credit.
-- IF NOT EXISTS makes this safe to run any number of times.

CREATE SCHEMA IF NOT EXISTS raw;           -- data exactly as received, never edited
CREATE SCHEMA IF NOT EXISTS staging;       -- cleaned and typed
CREATE SCHEMA IF NOT EXISTS intermediate;  -- business logic building blocks
CREATE SCHEMA IF NOT EXISTS marts;         -- final outputs: features, reports
