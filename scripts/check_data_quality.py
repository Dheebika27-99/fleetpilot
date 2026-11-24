"""
FleetPilot data-quality checks.

Runs a list of SQL checks against the RAW tables and prints a report.
Each check counts "bad" rows; a check FAILS when the count is above its limit.

Exit code: 0 if every check passes, 1 if any check fails, so this script can
later block a pipeline in GitHub Actions ("don't train / deploy on bad data").

Run:  python scripts/check_data_quality.py
"""

import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.config import DATABASE_URL  # noqa: E402

VALID_FUEL_TYPES = ("diesel", "hybrid", "electric", "gasoline")

# (name, kind of problem, SQL that returns ONE number = how many bad rows, max allowed)
CHECKS = [
    (
        "duplicate_sensor_readings",
        "duplicates",
        """
        SELECT COUNT(*) FROM (
            SELECT vehicle_id, recorded_at
            FROM sensor_readings
            GROUP BY vehicle_id, recorded_at
            HAVING COUNT(*) > 1
        ) AS dup_pairs
        """,
        0,
    ),
    (
        "missing_speed_while_driving",
        "missing values",
        "SELECT COUNT(*) FROM sensor_readings WHERE speed_kmh IS NULL AND trip_id IS NOT NULL",
        0,
    ),
    (
        "negative_or_impossible_speed",
        "impossible values",
        "SELECT COUNT(*) FROM sensor_readings WHERE speed_kmh < 0 OR speed_kmh > 200",
        0,
    ),
    (
        "engine_temp_out_of_range",
        "impossible values",
        "SELECT COUNT(*) FROM sensor_readings WHERE engine_temp_c < -40 OR engine_temp_c > 150",
        0,
    ),
    (
        "invalid_fuel_type",
        "messy text",
        f"SELECT COUNT(*) FROM vehicles WHERE fuel_type NOT IN {VALID_FUEL_TYPES}",
        0,
    ),
    (
        "trips_ending_before_start",
        "impossible values",
        "SELECT COUNT(*) FROM trips WHERE ended_at < started_at",
        0,
    ),
    (
        "orphan_trips_without_vehicle",
        "broken pointers",
        """
        SELECT COUNT(*) FROM trips t
        LEFT JOIN vehicles v ON t.vehicle_id = v.vehicle_id
        WHERE v.vehicle_id IS NULL
        """,
        0,
    ),
]


def run_checks(conn):
    """Run every check and return a list of result dictionaries."""
    results = []
    for name, kind, sql, max_allowed in CHECKS:
        bad_rows = conn.execute(sql).fetchone()[0]
        results.append({
            "name": name,
            "kind": kind,
            "bad_rows": bad_rows,
            "max_allowed": max_allowed,
            "passed": bad_rows <= max_allowed,
        })
    return results


def print_report(results):
    print(f"\n{'check':<32} {'kind':<18} {'bad rows':>9}  result")
    print("-" * 70)
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"{r['name']:<32} {r['kind']:<18} {r['bad_rows']:>9}  {mark}")
    failed = sum(not r["passed"] for r in results)
    print("-" * 70)
    print(f"{len(results) - failed} passed, {failed} failed\n")
    return failed


def main():
    with psycopg.connect(DATABASE_URL) as conn:
        results = run_checks(conn)
    failed = print_report(results)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
