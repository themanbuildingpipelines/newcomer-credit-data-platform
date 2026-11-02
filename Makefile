# Short names for the commands you'll run every day.
# IMPORTANT: every indented line below must start with a TAB, not spaces.

# Load settings from .env and pass them to every command
ifneq (,$(wildcard .env))
include .env
export
endif

# Your Mac username is the database superuser Homebrew created
SUPERUSER ?= $(USER)

PYTHON := .venv/bin/python
PIP    := .venv/bin/pip

.PHONY: setup db schemas tables check dbt-debug seed load dbt-build pipeline serve psql reset-raw test clean

setup:            ## create the virtual environment and install libraries
	python3.12 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

db:               ## create the project role and database (run once)
	@echo "Creating role and database as $(SUPERUSER)..."
	@PGUSER=$(SUPERUSER) PGDATABASE=postgres psql -v ON_ERROR_STOP=1 -v app_password="$(PGPASSWORD)" -f sql/00_bootstrap.sql

schemas:          ## create the four warehouse layers
	psql -v ON_ERROR_STOP=1 -f sql/01_schemas.sql

tables:           ## create the raw landing tables and the load log
	psql -v ON_ERROR_STOP=1 -f sql/02_raw_tables.sql

check:            ## confirm everything is ready
	$(PYTHON) scripts/check_setup.py

dbt-debug:        ## confirm dbt can reach the database
	cd dbt && ../.venv/bin/dbt debug

seed:             ## generate the synthetic population (same seed, same data)
	$(PYTHON) -m generator.run --seed 42 --customers 1000

load:             ## load the generated CSVs into the raw schema
	$(PYTHON) -m ingestion.load_generated

dbt-build:        ## build and test every dbt model (staging, intermediate, marts)
	cd dbt && ../.venv/bin/dbt build

pipeline:         ## everything, in order: generate, load, transform and test
	$(MAKE) seed
	$(MAKE) load
	$(MAKE) dbt-build

serve:            ## run the feature API on http://localhost:8000 (Ctrl+C to stop)
	$(PYTHON) -m uvicorn api.main:app --reload --port 8000

psql:             ## open psql as the project user, in the project database
	psql

reset-raw:        ## DEV ONLY: empty the raw tables and the load log
	psql -v ON_ERROR_STOP=1 -c "TRUNCATE raw.customers, raw.bank_transactions, raw.applications, raw.ingestion_runs RESTART IDENTITY"

test:             ## run the Python tests
	$(PYTHON) -m pytest -q

clean:            ## remove build output
	rm -rf dbt/target dbt/logs logs
