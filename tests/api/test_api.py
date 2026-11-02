"""
Tests for the feature API. They call the app directly with FastAPI's TestClient,
so no server needs to be running. They need the database AND the feature table
(built by `make dbt-build`), and skip with a clear reason if either is missing.
"""
import psycopg
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def needs_feature_table():
    load_dotenv()
    try:
        with psycopg.connect(connect_timeout=3, autocommit=True) as conn:
            exists = conn.execute(
                "SELECT to_regclass('marts.feat_income_regularity') IS NOT NULL"
            ).fetchone()[0]
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL not reachable: {exc}")
    if not exists:
        pytest.skip("Feature table missing: run `make dbt-build` first")


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_known_application_returns_its_feature():
    response = client.get("/features/income-regularity/APP-00001")
    assert response.status_code == 200
    body = response.json()
    assert body["application_id"] == "APP-00001"
    assert isinstance(body["is_regular_income"], bool)
    assert body["feature_version"] == "v1"


def test_money_is_sent_as_an_exact_string():
    body = client.get("/features/income-regularity/APP-00001").json()
    assert isinstance(body["median_income_amount"], str)


def test_timestamps_are_returned_in_utc():
    body = client.get("/features/income-regularity/APP-00001").json()
    assert body["decided_at"].endswith(("Z", "+00:00"))


def test_unknown_application_is_404():
    response = client.get("/features/income-regularity/APP-99999")
    assert response.status_code == 404


def test_malformed_id_is_rejected_before_touching_the_database():
    response = client.get("/features/income-regularity/banana")
    assert response.status_code == 422
