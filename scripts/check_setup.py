"""
check_setup.py: confirms your machine is ready to build the project.

Run it with:  make check   (or: python scripts/check_setup.py)
Every line should show OK. Anything marked FAIL tells you what to fix.
"""
import importlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
results = []


def check(name, passed, fix=""):
    results.append(passed)
    status = "OK  " if passed else "FAIL"
    print(f"[{status}] {name}")
    if not passed and fix:
        print(f"       fix: {fix}")


# 1. Python version
check(
    f"Python {sys.version_info.major}.{sys.version_info.minor}",
    sys.version_info >= (3, 11),
    "install Python 3.12 with: brew install python@3.12",
)

# 2. Running inside the project's virtual environment
in_venv = sys.prefix != sys.base_prefix
check("Virtual environment active", in_venv, "run: source .venv/bin/activate")

# 3. Required libraries installed
for pkg in ["numpy", "pandas", "psycopg", "dotenv", "pytest"]:
    try:
        importlib.import_module(pkg)
        check(f"Library '{pkg}' installed", True)
    except ImportError:
        check(f"Library '{pkg}' installed", False, "run: pip install -r requirements.txt")

# 4. .env exists and holds the settings we need
from dotenv import load_dotenv  # noqa: E402

env_file = ROOT / ".env"
check(".env file exists", env_file.exists(), "run: cp .env.example .env  then fill it in")
load_dotenv(env_file)
for var in ["PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"]:
    check(f"Setting {var} present", bool(os.getenv(var)), f"add {var}=... to .env")

# 5. .env is protected by .gitignore
ignored = subprocess.run(
    ["git", "check-ignore", "-q", ".env"], cwd=ROOT, capture_output=True
).returncode == 0
check(".env is ignored by Git", ignored, "add a line '.env' to .gitignore")

# 6. Database connection and the four schemas
try:
    import psycopg

    # With no arguments, psycopg reads the PG* settings loaded from .env
    with psycopg.connect(connect_timeout=5) as conn:
        version = conn.execute("SHOW server_version").fetchone()[0]
        check(f"Connected to PostgreSQL {version}", True)
        found = {
            row[0]
            for row in conn.execute(
                "SELECT schema_name FROM information_schema.schemata"
            )
        }
        for schema in ["raw", "staging", "intermediate", "marts"]:
            check(f"Schema '{schema}' exists", schema in found, "run: make schemas")
except Exception as exc:  # show the real error, it's the best clue
    check("Connected to PostgreSQL", False, f"{type(exc).__name__}: {exc}".strip())

print()
if all(results):
    print("All checks passed. Your machine is ready.")
else:
    print(f"{results.count(False)} check(s) failed. Fix the first one, then run again.")
    sys.exit(1)
