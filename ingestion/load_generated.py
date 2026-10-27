"""
load_generated.py: loads the generator's CSV files into PostgreSQL's raw schema.

Usage (from the project root):
    python -m ingestion.load_generated
    python -m ingestion.load_generated --dir data/generated

For each file, the loader:
  1. checks the file's fingerprint matches manifest.json   (is it the file we expect?)
  2. checks the header matches the expected columns        (has the shape changed?)
  3. records a 'running' row in raw.ingestion_runs          (the attempt is logged first)
  4. copies the file into a temporary table                 (fast bulk load)
  5. inserts into the real table, skipping rows already there  (ON CONFLICT DO NOTHING)
  6. marks the run 'succeeded' with counts, or 'failed' with the error

Running it twice inserts nothing the second time. That's idempotency.
The hidden truth file is never loaded here.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# Load order matters only for readability; there are no foreign keys in raw.
# Each source: (target table, primary key, columns in CSV order, SQL to cast text to types)
SOURCES = {
    "customers": {
        "key": "customer_id",
        "columns": ["customer_id", "arrival_date", "income_type"],
        "casts": ["customer_id", "arrival_date::date", "income_type"],
    },
    "bank_transactions": {
        "key": "transaction_id",
        "columns": [
            "transaction_id", "customer_id", "amount", "currency", "counterparty",
            "description", "event_at", "booked_at", "available_at",
        ],
        "casts": [
            "transaction_id", "customer_id", "amount::numeric(12,2)", "currency",
            "counterparty", "description", "event_at::timestamptz",
            "booked_at::timestamptz", "available_at::timestamptz",
        ],
    },
    "applications": {
        "key": "application_id",
        "columns": ["application_id", "customer_id", "decided_at"],
        "casts": ["application_id", "customer_id", "decided_at::timestamptz"],
    },
}


class LoadError(Exception):
    """A problem with the input file that should stop the load loudly."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as f:
        return next(csv.reader(f))


def start_run(conn, schema, name, path, digest, manifest) -> int:
    """Log the attempt and COMMIT it, so even a failed load leaves a record."""
    with conn.transaction():
        row = conn.execute(
            f"""
            INSERT INTO {schema}.ingestion_runs
                (source_name, file_path, file_sha256, generator_version,
                 generator_seed, rows_in_file, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'running')
            RETURNING run_id
            """,
            (name, str(path), digest, manifest.get("generator_version"),
             manifest.get("seed"), manifest["files"][name]["rows"]),
        ).fetchone()
    return row[0]


def finish_failed(conn, schema, run_id, message) -> None:
    with conn.transaction():
        conn.execute(
            f"""
            UPDATE {schema}.ingestion_runs
            SET status = 'failed', error_message = %s, finished_at = now()
            WHERE run_id = %s
            """,
            (message[:2000], run_id),
        )


def load_file(conn, schema: str, name: str, path: Path, manifest: dict) -> dict:
    """Load one CSV. Returns a summary. Raises on failure (after logging it)."""
    spec = SOURCES[name]
    expected = manifest["files"][name]

    digest = sha256(path)
    run_id = start_run(conn, schema, name, path, digest, manifest)

    try:
        # Check 1: is this exactly the file the manifest describes?
        if digest != expected["sha256"]:
            raise LoadError(
                f"{path.name}: checksum does not match manifest.json. "
                "The file changed after it was generated (was it opened and saved in Excel?)."
            )

        # Check 2: does the header have the columns we expect, in order?
        header = read_header(path)
        if header != spec["columns"]:
            raise LoadError(
                f"{path.name}: unexpected columns.\n  expected {spec['columns']}\n  found    {header}"
            )

        cols = ", ".join(spec["columns"])
        casts = ", ".join(spec["casts"])

        # One transaction: either the rows AND the 'succeeded' status land together, or neither does.
        with conn.transaction():
            # A temporary table of plain text, matching the CSV exactly. Dropped automatically.
            conn.execute(
                f"CREATE TEMP TABLE tmp_load ({', '.join(c + ' TEXT' for c in spec['columns'])}) "
                "ON COMMIT DROP"
            )
            # COPY streams the whole file in one go: much faster than row-by-row inserts.
            with conn.cursor().copy(
                f"COPY tmp_load ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true)"
            ) as copy:
                with path.open("rb") as f:
                    while chunk := f.read(1024 * 1024):
                        copy.write(chunk)

            # Cast text into real types, and skip any row whose key is already loaded.
            inserted = conn.execute(
                f"""
                INSERT INTO {schema}.{name} ({cols}, _run_id)
                SELECT {casts}, %s FROM tmp_load
                ON CONFLICT ({spec['key']}) DO NOTHING
                """,
                (run_id,),
            ).rowcount

            rows_in_file = expected["rows"]
            conn.execute(
                f"""
                UPDATE {schema}.ingestion_runs
                SET status = 'succeeded', rows_inserted = %s, rows_skipped = %s,
                    finished_at = now()
                WHERE run_id = %s
                """,
                (inserted, rows_in_file - inserted, run_id),
            )

        return {"source": name, "run_id": run_id, "rows": rows_in_file, "inserted": inserted}

    except Exception as exc:
        finish_failed(conn, schema, run_id, str(exc))
        raise


def load_all(conn, data_dir: Path, schema: str = "raw") -> list[dict]:
    # Every `with conn.transaction()` block in this file must be a REAL transaction
    # that commits when it ends. Without autocommit, psycopg silently opens an outer
    # transaction on the first query, and our blocks become nested savepoints that
    # never truly commit. So we refuse to run without it.
    if not conn.autocommit:
        raise LoadError("Connect with psycopg.connect(autocommit=True) before loading.")

    manifest_path = data_dir / "manifest.json"
    if not manifest_path.exists():
        raise LoadError(f"No manifest at {manifest_path}. Run `make seed` first.")
    manifest = json.loads(manifest_path.read_text())

    results = []
    for name in SOURCES:  # the truth file is deliberately not in SOURCES
        path = Path(manifest["files"][name]["path"])
        if not path.is_absolute():
            path = data_dir / path.name
        results.append(load_file(conn, schema, name, path, manifest))
    return results


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Load generated CSVs into the raw schema.")
    parser.add_argument("--dir", type=Path, default=Path("data/generated"))
    args = parser.parse_args(argv)

    load_dotenv()  # read PGHOST, PGUSER, PGPASSWORD and friends from .env
    with psycopg.connect(autocommit=True) as conn:
        for r in load_all(conn, args.dir):
            skipped = r["rows"] - r["inserted"]
            print(f"  {r['source']:<18} run {r['run_id']:>3}: "
                  f"{r['inserted']:>7,} inserted, {skipped:>7,} already loaded")


if __name__ == "__main__":
    main()
