-- 02_raw_tables.sql
-- The landing tables for generated data, plus an audit log of every load.
-- Run as ncp_dev inside newcomer_credit:  make tables
-- Safe to re-run: IF NOT EXISTS skips tables that already exist.

-- ---------------------------------------------------------------------------
-- The load log. One row per file, per load attempt, whether it worked or not.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.ingestion_runs (
    run_id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name        TEXT        NOT NULL,   -- e.g. 'bank_transactions'
    file_path          TEXT        NOT NULL,
    file_sha256        TEXT        NOT NULL,   -- fingerprint of the exact file loaded
    generator_version  TEXT,                   -- from manifest.json
    generator_seed     INTEGER,                -- from manifest.json
    rows_in_file       INTEGER,
    rows_inserted      INTEGER,
    rows_skipped       INTEGER,                -- already loaded before
    status             TEXT        NOT NULL
                       CHECK (status IN ('running', 'succeeded', 'failed')),
    error_message      TEXT,
    started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at        TIMESTAMPTZ
);

-- ---------------------------------------------------------------------------
-- Landing tables. Columns match the CSV files, plus two lineage columns:
--   _run_id     which load brought this row in
--   _loaded_at  when it arrived
-- No foreign keys here on purpose: real sources arrive in any order.
-- Relationships get tested later, in dbt, instead of enforced at the door.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.customers (
    customer_id   TEXT        PRIMARY KEY,
    arrival_date  DATE        NOT NULL,
    income_type   TEXT        NOT NULL,
    _run_id       BIGINT      NOT NULL,
    _loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.bank_transactions (
    transaction_id  TEXT          PRIMARY KEY,
    customer_id     TEXT          NOT NULL,
    amount          NUMERIC(12,2) NOT NULL,   -- exact money: never FLOAT
    currency        CHAR(3)       NOT NULL,
    counterparty    TEXT          NOT NULL,
    description     TEXT,
    event_at        TIMESTAMPTZ   NOT NULL,   -- when it happened
    booked_at       TIMESTAMPTZ   NOT NULL,   -- when the bank recorded it
    available_at    TIMESTAMPTZ   NOT NULL,   -- when the lender could see it
    _run_id         BIGINT        NOT NULL,
    _loaded_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.applications (
    application_id  TEXT        PRIMARY KEY,
    customer_id     TEXT        NOT NULL,
    decided_at      TIMESTAMPTZ NOT NULL,
    _run_id         BIGINT      NOT NULL,
    _loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Speeds up the most common question later: "this customer's transactions, in time order".
CREATE INDEX IF NOT EXISTS ix_bank_transactions_customer_event
    ON raw.bank_transactions (customer_id, event_at);
