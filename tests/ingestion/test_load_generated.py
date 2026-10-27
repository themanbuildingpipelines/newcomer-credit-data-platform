"""
Tests for ingestion/load_generated.py. These talk to the real PostgreSQL database.

Each test gets its own throwaway schema (e.g. test_raw_3f9c1a), built from the
same sql/02_raw_tables.sql file, and dropped afterwards. Your real `raw` schema
is never touched.

If the database isn't reachable, these tests are skipped with a clear reason
instead of failing, so `make test` still runs the generator tests offline.
"""
import hashlib
import json
import uuid
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from dotenv import load_dotenv

from generator.run import main as generate
from ingestion.load_generated import LoadError, load_all

ROOT = Path(__file__).resolve().parents[2]
DDL = (ROOT / "sql" / "02_raw_tables.sql").read_text()


@pytest.fixture
def conn():
    load_dotenv(ROOT / ".env")
    try:
        connection = psycopg.connect(connect_timeout=3, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL not reachable: {exc}")
    yield connection
    connection.close()


@pytest.fixture
def schema(conn):
    """A fresh, empty copy of the raw tables in a uniquely named schema."""
    name = f"test_raw_{uuid.uuid4().hex[:6]}"
    with conn.transaction():
        conn.execute(f"CREATE SCHEMA {name}")
        conn.execute(DDL.replace("raw.", f"{name}."))
    yield name
    with conn.transaction():
        conn.execute(f"DROP SCHEMA {name} CASCADE")


@pytest.fixture
def data_dir(tmp_path):
    """A small generated town in a temporary folder."""
    generate(["--seed", "5", "--customers", "20", "--out", str(tmp_path)])
    return tmp_path


def count(conn, schema, table):
    return conn.execute(f"SELECT count(*) FROM {schema}.{table}").fetchone()[0]


def manifest(data_dir):
    return json.loads((data_dir / "manifest.json").read_text())


def rewrite_and_fix_checksum(data_dir, name, new_text):
    """Change a file AND update the manifest, to test checks after the checksum."""
    path = data_dir / f"{name}.csv"
    path.write_text(new_text)
    m = manifest(data_dir)
    m["files"][name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (data_dir / "manifest.json").write_text(json.dumps(m))


# ---------------------------------------------------------------------------


def test_refuses_a_connection_without_autocommit(data_dir):
    load_dotenv(ROOT / ".env")
    try:
        plain = psycopg.connect(connect_timeout=3)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL not reachable: {exc}")
    with plain:
        with pytest.raises(LoadError, match="autocommit"):
            load_all(plain, data_dir, "raw")


def test_loads_every_row_the_manifest_promises(conn, schema, data_dir):
    load_all(conn, data_dir, schema)
    files = manifest(data_dir)["files"]
    for table in ["customers", "bank_transactions", "applications"]:
        assert count(conn, schema, table) == files[table]["rows"], table


def test_loading_twice_creates_no_duplicates(conn, schema, data_dir):
    load_all(conn, data_dir, schema)
    before = count(conn, schema, "bank_transactions")
    second = load_all(conn, data_dir, schema)
    assert count(conn, schema, "bank_transactions") == before
    assert all(r["inserted"] == 0 for r in second)


def test_every_load_attempt_is_logged(conn, schema, data_dir):
    load_all(conn, data_dir, schema)
    load_all(conn, data_dir, schema)
    rows = conn.execute(
        f"SELECT source_name, status FROM {schema}.ingestion_runs ORDER BY run_id"
    ).fetchall()
    assert len(rows) == 6
    assert {status for _, status in rows} == {"succeeded"}


def test_every_row_points_to_the_run_that_loaded_it(conn, schema, data_dir):
    load_all(conn, data_dir, schema)
    orphans = conn.execute(
        f"""
        SELECT count(*) FROM {schema}.bank_transactions t
        LEFT JOIN {schema}.ingestion_runs r ON r.run_id = t._run_id
        WHERE r.run_id IS NULL OR r.status <> 'succeeded'
        """
    ).fetchone()[0]
    assert orphans == 0


def test_money_survives_the_load_exactly(conn, schema, data_dir):
    load_all(conn, data_dir, schema)
    lines = (data_dir / "bank_transactions.csv").read_text().splitlines()[1:]
    expected = sum(Decimal(line.split(",")[2]) for line in lines)
    loaded = conn.execute(f"SELECT sum(amount) FROM {schema}.bank_transactions").fetchone()[0]
    assert loaded == expected


def test_timestamps_keep_their_utc_meaning(conn, schema, data_dir):
    load_all(conn, data_dir, schema)
    first_line = (data_dir / "bank_transactions.csv").read_text().splitlines()[1]
    tx_id, csv_ts = first_line.split(",")[0], first_line.split(",")[6]
    db_ts = conn.execute(
        f"SELECT to_char(event_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') "
        f"FROM {schema}.bank_transactions WHERE transaction_id = %s",
        (tx_id,),
    ).fetchone()[0]
    assert db_ts == csv_ts


def test_tampered_file_is_refused_and_logged(conn, schema, data_dir):
    path = data_dir / "customers.csv"
    path.write_text(path.read_text().replace("salaried", "Salaried", 1))
    with pytest.raises(LoadError, match="checksum"):
        load_all(conn, data_dir, schema)
    assert count(conn, schema, "customers") == 0
    status = conn.execute(f"SELECT status FROM {schema}.ingestion_runs").fetchone()[0]
    assert status == "failed"


def test_renamed_column_is_refused(conn, schema, data_dir):
    load_all(conn, data_dir, schema)  # customers and transactions load fine first
    text = (data_dir / "applications.csv").read_text().replace("decided_at", "decision_time", 1)
    rewrite_and_fix_checksum(data_dir, "applications", text)
    with pytest.raises(LoadError, match="unexpected columns"):
        load_all(conn, data_dir, schema)


def test_bad_value_rolls_back_the_whole_file(conn, schema, data_dir):
    lines = (data_dir / "bank_transactions.csv").read_text().splitlines()
    parts = lines[5].split(",")
    parts[2] = "not-a-number"
    lines[5] = ",".join(parts)
    rewrite_and_fix_checksum(data_dir, "bank_transactions", "\n".join(lines) + "\n")

    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        load_all(conn, data_dir, schema)

    # Not a single row from the broken file was kept: all or nothing.
    assert count(conn, schema, "bank_transactions") == 0
    failed = conn.execute(
        f"SELECT count(*) FROM {schema}.ingestion_runs WHERE status = 'failed'"
    ).fetchone()[0]
    assert failed == 1
