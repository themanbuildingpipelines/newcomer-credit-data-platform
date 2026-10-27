"""
Tests for generator/build.py.

Each test checks one promise the generator makes. If a promise breaks,
the test name tells you which one.
"""
from datetime import timedelta

import pandas as pd

from generator.build import MIN_HISTORY_DAYS, SIM_END, build_all

SMALL = 50  # small populations keep tests fast


def test_same_seed_gives_identical_data():
    first = build_all(seed=7, n_customers=SMALL)
    second = build_all(seed=7, n_customers=SMALL)
    for name in first:
        pd.testing.assert_frame_equal(first[name], second[name])


def test_different_seed_gives_different_data():
    a = build_all(seed=7, n_customers=SMALL)["bank_transactions"]
    b = build_all(seed=8, n_customers=SMALL)["bank_transactions"]
    assert not a.equals(b)


def test_ids_are_unique():
    tables = build_all(seed=7, n_customers=SMALL)
    assert tables["customers"]["customer_id"].is_unique
    assert tables["bank_transactions"]["transaction_id"].is_unique
    assert tables["applications"]["application_id"].is_unique


def test_every_transaction_belongs_to_a_known_customer():
    tables = build_all(seed=7, n_customers=SMALL)
    known = set(tables["customers"]["customer_id"])
    assert set(tables["bank_transactions"]["customer_id"]) <= known
    assert set(tables["applications"]["customer_id"]) <= known


def test_no_transaction_before_arrival_or_after_sim_end():
    tables = build_all(seed=7, n_customers=SMALL)
    tx = tables["bank_transactions"].merge(tables["customers"], on="customer_id")
    event_dates = tx["event_at"].dt.date
    assert (event_dates >= tx["arrival_date"]).all()
    assert (event_dates <= SIM_END).all()


def test_applications_have_enough_history():
    tables = build_all(seed=7, n_customers=SMALL)
    apps = tables["applications"].merge(tables["customers"], on="customer_id")
    earliest = apps["arrival_date"] + timedelta(days=MIN_HISTORY_DAYS)
    assert (apps["decided_at"].dt.date >= earliest).all()


def test_hidden_truth_never_appears_in_visible_tables():
    tables = build_all(seed=7, n_customers=SMALL)
    hidden = {"true_affordability", "monthly_income_pence", "monthly_rent_pence"}
    for name in ["customers", "bank_transactions", "applications"]:
        assert hidden.isdisjoint(tables[name].columns), f"truth leaked into {name}"


def test_salary_arrives_roughly_monthly():
    tx = build_all(seed=7, n_customers=SMALL)["bank_transactions"]
    salaries = tx[tx["description"].str.startswith("SALARY")]
    gaps = (
        salaries.sort_values("event_at")
        .groupby("customer_id")["event_at"]
        .diff()
        .dropna()
        .dt.days
    )
    # Pay day moves between the 25th and 28th, and is sometimes 1-2 days late.
    assert gaps.between(24, 37).all()


def test_v1_timestamps_are_all_equal():
    # Version 1 assumption: no late-arriving data yet. This test documents it,
    # and will be changed on purpose when late arrivals are added.
    tx = build_all(seed=7, n_customers=SMALL)["bank_transactions"]
    assert (tx["event_at"] == tx["booked_at"]).all()
    assert (tx["booked_at"] == tx["available_at"]).all()
