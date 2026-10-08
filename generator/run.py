"""
run.py: the command line entry point. This file handles files; build.py handles logic.

Usage (from the project root):
    python -m generator.run --seed 42 --customers 1000

Writes:
    data/generated/customers.csv
    data/generated/bank_transactions.csv
    data/generated/applications.csv
    data/generated/truth/generator_truth.csv   <- hidden scores, kept apart on purpose
    data/generated/manifest.json               <- what was generated, how, and checksums
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from generator.build import GENERATOR_VERSION, build_all

# Explicit column order for every output file. Downstream code depends on it,
# so it never changes by accident.
COLUMNS = {
    "customers": ["customer_id", "arrival_date", "income_type"],
    "bank_transactions": [
        "transaction_id", "customer_id", "amount", "currency", "counterparty",
        "description", "event_at", "booked_at", "available_at",
    ],
    "applications": ["application_id", "customer_id", "decided_at"],
    "generator_truth": [
        "customer_id", "monthly_income", "monthly_rent", "monthly_bills",
        "true_affordability",
    ],
}


def pence_to_str(pence: int) -> str:
    """Exact money formatting from whole pence. No floats involved: -125050 -> '-1250.50'."""
    sign = "-" if pence < 0 else ""
    pence = abs(int(pence))
    return f"{sign}{pence // 100}.{pence % 100:02d}"


def iso_utc(ts: pd.Timestamp) -> str:
    """Timestamps as ISO 8601 in UTC with a trailing Z, e.g. 2024-02-28T06:13:00Z."""
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def prepare(name: str, df: pd.DataFrame) -> pd.DataFrame:
    """Turn in-memory types into clean, unambiguous text for the CSV."""
    df = df.copy()
    if name == "bank_transactions":
        df["amount"] = df["amount_pence"].map(pence_to_str)
        for col in ["event_at", "booked_at", "available_at"]:
            df[col] = df[col].map(iso_utc)
    if name == "applications":
        df["decided_at"] = df["decided_at"].map(iso_utc)
    if name == "customers":
        df["arrival_date"] = df["arrival_date"].map(lambda d: d.isoformat())
    if name == "generator_truth":
        df["monthly_income"] = df["monthly_income_pence"].map(pence_to_str)
        df["monthly_rent"] = df["monthly_rent_pence"].map(pence_to_str)
        df["monthly_bills"] = df["monthly_bills_pence"].map(pence_to_str)
    return df[COLUMNS[name]]


def write_csv(df: pd.DataFrame, path: Path) -> None:
    """
    Write to a temporary file first, then rename it into place.
    If the program crashes halfway, you never get a half-written CSV
    sitting where a complete one should be.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8", lineterminator="\n")
    os.replace(tmp, path)


def sha256(path: Path) -> str:
    """A fingerprint of the file. Same contents, same fingerprint."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic population.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--customers", type=int, default=1000)
    parser.add_argument("--out", type=Path, default=Path("data/generated"))
    args = parser.parse_args(argv)

    tables = build_all(seed=args.seed, n_customers=args.customers)

    paths = {
        "customers": args.out / "customers.csv",
        "bank_transactions": args.out / "bank_transactions.csv",
        "applications": args.out / "applications.csv",
        "generator_truth": args.out / "truth" / "generator_truth.csv",
    }

    files = {}
    for name, df in tables.items():
        write_csv(prepare(name, df), paths[name])
        files[name] = {
            "path": str(paths[name]),
            "rows": int(len(df)),
            "sha256": sha256(paths[name]),
        }

    manifest = {
        "generator_version": GENERATOR_VERSION,
        "seed": args.seed,
        "customers_requested": args.customers,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": files,
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"Generated with seed {args.seed} (generator v{GENERATOR_VERSION})")
    for name, info in files.items():
        print(f"  {name:<18} {info['rows']:>8,} rows  ->  {info['path']}")
    print(f"  manifest           ->  {args.out / 'manifest.json'}")


if __name__ == "__main__":
    main()
