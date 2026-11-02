"""
main.py: a small API that serves the income regularity feature.

Run it:   make serve
Then open http://localhost:8000/docs for interactive documentation.

It only READS the feature table that dbt built. It never calculates anything,
so the API and the feature always agree.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Path
from psycopg.rows import dict_row
from pydantic import BaseModel

load_dotenv()

app = FastAPI(
    title="Newcomer Credit Data Platform",
    description="Point-in-time affordability features for thin-file applicants.",
    version="0.1.0",
)


class IncomeRegularity(BaseModel):
    """The shape of every response. FastAPI uses it to validate and document."""
    application_id: str
    customer_id: str
    decided_at: datetime
    main_income_source: str | None
    income_payments_6m: int
    median_income_amount: Decimal | None   # sent as a string, so money stays exact
    median_gap_days: float | None
    income_amount_cv: Decimal | None
    is_regular_income: bool
    feature_version: str


QUERY = """
    SELECT application_id, customer_id, decided_at, main_income_source,
           income_payments_6m, median_income_amount, median_gap_days,
           income_amount_cv, is_regular_income, feature_version
    FROM marts.feat_income_regularity
    WHERE application_id = %s
"""


def connect(**kwargs):
    # Every connection runs in UTC, so timestamps in responses never depend on
    # the time zone of the machine the database happens to run on.
    return psycopg.connect(autocommit=True, options="-c TimeZone=UTC", **kwargs)


def fetch_feature(application_id: str) -> dict | None:
    # A new connection per request keeps this simple. A busy service would use a pool.
    with connect(row_factory=dict_row) as conn:
        return conn.execute(QUERY, (application_id,)).fetchone()


@app.get("/health")
def health() -> dict:
    """Is the API up, and can it reach the database?"""
    with connect(connect_timeout=3) as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/features/income-regularity/{application_id}", response_model=IncomeRegularity)
def get_income_regularity(
    application_id: str = Path(pattern=r"^APP-\d{5}$", examples=["APP-00001"]),
) -> dict:
    """Income regularity for one application, as known at its decision time."""
    row = fetch_feature(application_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No application {application_id}")
    return row
