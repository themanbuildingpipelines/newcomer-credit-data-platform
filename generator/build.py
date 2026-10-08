"""
build.py: creates the synthetic population in memory.

This file only BUILDS data. It never reads or writes files.
Keeping the logic separate from file handling makes it easy to test:
a test can call build_all() and inspect the tables directly.

Version 1 scope (deliberately small):
  - salaried customers only
  - each customer has a salary, rent and two bills
  - each customer makes one loan application
  - all three timestamps on a transaction are equal (late data comes later)
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta, timezone

import numpy as np
import pandas as pd

GENERATOR_VERSION = "1.0.0"

# The simulated world runs between these dates. They are fixed on purpose:
# if they depended on today's date, the same seed would give different data
# on different days, and tests would stop being repeatable.
SIM_START = date(2024, 1, 1)
SIM_END = date(2025, 12, 31)
LATEST_ARRIVAL = date(2025, 6, 30)
MIN_HISTORY_DAYS = 90  # an application is decided at least this long after arrival

# Fictional names only. No real companies.
EMPLOYERS = [
    "MERIDIAN CARE LTD", "HARBOURVIEW LOGISTICS", "BRIGHTPATH SCHOOLS",
    "NORTHSTAR RETAIL", "KESTREL ENGINEERING", "ALDERWOOD HOSPITALITY",
    "CEDARLINE HEALTH", "SILVERGATE SECURITY",
]
ENERGY_PROVIDERS = ["NORTHGRID ENERGY", "BLUEFLAME POWER", "VOLTWISE HOME"]
MOBILE_PROVIDERS = ["BRIGHTWAVE MOBILE", "SKYLINK TELECOM", "PULSE MOBILE"]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _month_starts(first: date, last: date) -> list[date]:
    """The first day of every month from first's month to last's month."""
    months = []
    current = date(first.year, first.month, 1)
    while current <= last:
        months.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return months


def _day_in_month(month_start: date, day: int) -> date:
    """A day in the given month, clamped so day 31 in February becomes the 28th/29th."""
    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    return month_start.replace(day=min(day, last_day))


def _utc(d: date, hour: int, minute: int) -> datetime:
    """A timezone-aware UTC timestamp. Always store time with a timezone."""
    return datetime.combine(d, time(hour, minute), tzinfo=timezone.utc)


def _round_to(pence: float, step_pence: int) -> int:
    """Round an amount in pence to the nearest step, e.g. nearest £10 = 1000p."""
    return int(round(pence / step_pence)) * step_pence


# ---------------------------------------------------------------------------
# 1. Customers and their hidden truth
# ---------------------------------------------------------------------------

def make_customers(rng: np.random.Generator, n_customers: int):
    """
    Returns two tables:
      customers: what the pipeline is allowed to see
      truth:     the hidden profile, used ONLY to grade the pipeline later
    Also returns a list of profiles the other functions use to build each life.
    """
    window_days = (LATEST_ARRIVAL - SIM_START).days
    customers, truth, profiles = [], [], []

    for i in range(1, n_customers + 1):
        customer_id = f"CUST-{i:05d}"
        arrival = SIM_START + timedelta(days=int(rng.integers(0, window_days + 1)))

        # Monthly salary: most people near £2,300, a few higher or lower.
        salary = float(np.clip(rng.lognormal(mean=np.log(2300), sigma=0.25), 1400, 3500))
        salary_p = _round_to(salary * 100, 1000)                         # nearest £10
        rent_p = _round_to(salary_p * rng.uniform(0.30, 0.50), 500)      # nearest £5
        energy_p = int(rng.integers(60, 141)) * 100                      # £60 to £140 typical
        mobile_p = int(rng.integers(15, 46)) * 100                       # £15 to £45

        # The hidden score: share of income left after fixed costs, plus noise.
        # Noise matters: real life is never perfectly predictable.
        affordability = (salary_p - rent_p - energy_p - mobile_p) / salary_p
        affordability += rng.normal(0, 0.03)

        profile = {
            "customer_id": customer_id,
            "arrival_date": arrival,
            "salary_p": salary_p,
            "rent_p": rent_p,
            "energy_p": energy_p,
            "mobile_p": mobile_p,
            "employer": EMPLOYERS[int(rng.integers(0, len(EMPLOYERS)))],
            "energy": ENERGY_PROVIDERS[int(rng.integers(0, len(ENERGY_PROVIDERS)))],
            "mobile": MOBILE_PROVIDERS[int(rng.integers(0, len(MOBILE_PROVIDERS)))],
            "landlord": f"LANDLORD REF {int(rng.integers(1000, 10000))}",
        }
        profiles.append(profile)

        customers.append({
            "customer_id": customer_id,
            "arrival_date": arrival,
            "income_type": "salaried",
        })
        truth.append({
            "customer_id": customer_id,
            "monthly_income_pence": salary_p,
            "monthly_rent_pence": rent_p,
            "monthly_bills_pence": energy_p + mobile_p,
            "true_affordability": round(float(affordability), 4),
        })

    return pd.DataFrame(customers), pd.DataFrame(truth), profiles


# ---------------------------------------------------------------------------
# 2. Each customer's financial life
# ---------------------------------------------------------------------------

def make_transactions(rng: np.random.Generator, profiles: list[dict]) -> pd.DataFrame:
    """Monthly salary, rent and two bills for every customer, from arrival to SIM_END."""
    rows = []

    def add(p, d, hour, minute, amount_p, counterparty, description):
        # Only record events inside the customer's time in the country.
        if d < p["arrival_date"] or d > SIM_END:
            return
        ts = _utc(d, hour, minute)
        rows.append({
            "customer_id": p["customer_id"],
            "amount_pence": amount_p,          # positive = money in, negative = money out
            "currency": "GBP",
            "counterparty": counterparty,
            "description": description,
            "event_at": ts,                    # when it happened
            "booked_at": ts,                   # v1: the bank books it instantly
            "available_at": ts,                # v1: the lender sees it instantly
        })

    for p in profiles:
        for month in _month_starts(p["arrival_date"], SIM_END):
            # Salary lands between the 25th and 28th; 1 in 10 months it's 1-2 days late.
            pay_day = _day_in_month(month, int(rng.integers(25, 29)))
            if rng.random() < 0.10:
                pay_day += timedelta(days=int(rng.integers(1, 3)))
            add(p, pay_day, 6, int(rng.integers(0, 60)),
                p["salary_p"], p["employer"], f"SALARY {p['employer']}")

            # Rent leaves on the 1st.
            add(p, month, 9, 0, -p["rent_p"], p["landlord"], "RENT STANDING ORDER")

            # Energy varies a little month to month (more in winter in real life).
            energy_day = _day_in_month(month, int(rng.integers(8, 13)))
            energy_amount = _round_to(p["energy_p"] * rng.uniform(0.85, 1.15), 1)
            add(p, energy_day, 7, int(rng.integers(0, 60)),
                -energy_amount, p["energy"], f"{p['energy']} DD")

            # Mobile is a fixed contract around the 15th.
            mobile_day = _day_in_month(month, 15 + int(rng.integers(-1, 2)))
            add(p, mobile_day, 7, int(rng.integers(0, 60)),
                -p["mobile_p"], p["mobile"], f"{p['mobile']} DD")

    df = pd.DataFrame(rows)
    # A stable order means a stable transaction_id, run after run.
    df = df.sort_values(["customer_id", "event_at", "description"]).reset_index(drop=True)
    df.insert(0, "transaction_id", [f"TXN-{i:08d}" for i in range(1, len(df) + 1)])
    return df


# ---------------------------------------------------------------------------
# 3. Loan applications
# ---------------------------------------------------------------------------

def make_applications(rng: np.random.Generator, customers: pd.DataFrame) -> pd.DataFrame:
    """One application per customer, decided at least MIN_HISTORY_DAYS after arrival."""
    rows = []
    for i, row in enumerate(customers.itertuples(index=False), start=1):
        earliest = row.arrival_date + timedelta(days=MIN_HISTORY_DAYS)
        offset = int(rng.integers(0, (SIM_END - earliest).days + 1))
        decided = _utc(earliest + timedelta(days=offset),
                       int(rng.integers(9, 18)), int(rng.integers(0, 60)))
        rows.append({
            "application_id": f"APP-{i:05d}",
            "customer_id": row.customer_id,
            "decided_at": decided,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Everything together
# ---------------------------------------------------------------------------

def build_all(seed: int, n_customers: int) -> dict[str, pd.DataFrame]:
    """
    Build every table from ONE seeded random generator.
    The functions are always called in the same order, so the same seed
    always produces exactly the same data.
    """
    rng = np.random.default_rng(seed)
    customers, truth, profiles = make_customers(rng, n_customers)
    transactions = make_transactions(rng, profiles)
    applications = make_applications(rng, customers)
    return {
        "customers": customers,
        "bank_transactions": transactions,
        "applications": applications,
        "generator_truth": truth,
    }
