-- 00_bootstrap.sql
-- Creates the project's login role and database.
-- Run ONCE as your Mac superuser:
--   psql -d postgres -v app_password="$PGPASSWORD" -f sql/00_bootstrap.sql
-- Safe to re-run: each statement only fires if the thing doesn't exist yet.

SELECT format('CREATE ROLE ncp_dev LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ncp_dev')
\gexec

SELECT 'CREATE DATABASE newcomer_credit OWNER ncp_dev'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'newcomer_credit')
\gexec
