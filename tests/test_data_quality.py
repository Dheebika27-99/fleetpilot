"""
Tests for the data-quality checker: does it catch exactly the bugs the
generator planted? (The answer key is data/_planted_bugs.json.)
"""

import json
from pathlib import Path

import psycopg

from app.config import DATABASE_URL
from scripts.check_data_quality import run_checks

ANSWER_KEY = json.loads((Path(__file__).resolve().parent.parent / "data" / "_planted_bugs.json").read_text())


def results_by_name():
    with psycopg.connect(DATABASE_URL) as conn:
        return {r["name"]: r for r in run_checks(conn)}


def test_checker_finds_every_planted_bug():
    r = results_by_name()
    assert r["duplicate_sensor_readings"]["bad_rows"] == ANSWER_KEY["duplicate_readings"]
    assert r["missing_speed_while_driving"]["bad_rows"] == ANSWER_KEY["missing_speed"]
    assert r["negative_or_impossible_speed"]["bad_rows"] == ANSWER_KEY["negative_speed"]
    assert r["engine_temp_out_of_range"]["bad_rows"] == ANSWER_KEY["engine_temp_999"]
    assert r["invalid_fuel_type"]["bad_rows"] == ANSWER_KEY["messy_fuel_type"]


def test_clean_layer_removes_the_bugs():
    with psycopg.connect(DATABASE_URL) as conn:
        dup = conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT vehicle_id, recorded_at FROM clean_sensor_readings
                GROUP BY 1, 2 HAVING COUNT(*) > 1) x
        """).fetchone()[0]
        bad_speed = conn.execute("SELECT COUNT(*) FROM clean_sensor_readings WHERE speed_kmh < 0").fetchone()[0]
        bad_temp = conn.execute("SELECT COUNT(*) FROM clean_sensor_readings WHERE engine_temp_c > 150").fetchone()[0]
        fuel = conn.execute("SELECT COUNT(DISTINCT fuel_type) FROM clean_vehicles").fetchone()[0]
    assert dup == 0
    assert bad_speed == 0
    assert bad_temp == 0
    assert fuel == 4
