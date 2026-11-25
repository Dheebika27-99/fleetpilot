"""
Create the FleetPilot tables and load the generated CSV files into Postgres.

Same job as `psql -f db/schema.sql -f db/load.sql`, but in Python, so it works
anywhere Python runs (your Mac, Docker, GitHub Actions) without needing psql.

Steps:
  1. run db/schema.sql       (drop + create the 5 tables)
  2. COPY each CSV in data/  (parents first, because of the foreign keys)
  3. run db/clean_views.sql  (the clean layer)
  4. run db/llm_schema.sql   (LLM call log table, created only if missing)

Run:  python scripts/generate_data.py   # makes the CSVs
      python scripts/load_db.py         # loads them
"""

import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))          # so "app" can be imported when run as a script
from app.config import DATABASE_URL    # noqa: E402
DATA_DIR = ROOT / "data"

# Order matters: a trip can only point to a vehicle that already exists.
TABLES = ["vehicles", "drivers", "trips", "sensor_readings", "warnings"]


def run_sql_file(conn, path):
    conn.execute(path.read_text())
    print(f"  ran {path.relative_to(ROOT)}")


def copy_csv(conn, table):
    csv_path = DATA_DIR / f"{table}.csv"
    if not csv_path.exists():
        raise SystemExit(f"Missing {csv_path}. Run: python scripts/generate_data.py")
    with conn.cursor() as cur:
        with cur.copy(f"COPY {table} FROM STDIN WITH (FORMAT csv, HEADER true)") as copy:
            copy.write(csv_path.read_bytes())
        count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  loaded {table:<16} {count:>7} rows")


def main():
    print(f"Connecting to {DATABASE_URL}")
    # One transaction: if anything fails, nothing is half-loaded.
    with psycopg.connect(DATABASE_URL) as conn:
        run_sql_file(conn, ROOT / "db" / "schema.sql")
        for table in TABLES:
            copy_csv(conn, table)
        run_sql_file(conn, ROOT / "db" / "clean_views.sql")
        run_sql_file(conn, ROOT / "db" / "llm_schema.sql")   # LLM call log (kept between reloads)
    print("Done.")


if __name__ == "__main__":
    main()
