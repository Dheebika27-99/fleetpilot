"""
API tests. They run against the local fleetpilot database, loaded with the
generated data (seed 42 makes the data the same every time, so exact numbers work).

Run:  pytest
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_list_vehicles_default_limit():
    response = client.get("/vehicles")
    assert response.status_code == 200
    assert len(response.json()) == 50          # default page size


def test_list_vehicles_paging_covers_whole_fleet():
    first = client.get("/vehicles", params={"limit": 500}).json()
    assert len(first) == 200                   # the whole fleet fits in one page


def test_filter_by_depot_only_returns_that_depot():
    vehicles = client.get("/vehicles", params={"depot": "Tokyo", "limit": 500}).json()
    assert len(vehicles) > 0
    assert all(v["depot"] == "Tokyo" for v in vehicles)


def test_fuel_type_is_cleaned():
    """The raw table has 'Diesel' and 'diesel '; the API must only show clean values."""
    vehicles = client.get("/vehicles", params={"limit": 500}).json()
    fuel_types = {v["fuel_type"] for v in vehicles}
    assert fuel_types <= {"diesel", "hybrid", "electric", "gasoline"}


def test_fuel_type_filter_ignores_case_and_spaces():
    a = client.get("/vehicles", params={"fuel_type": "diesel", "limit": 500}).json()
    b = client.get("/vehicles", params={"fuel_type": " DIESEL ", "limit": 500}).json()
    assert len(a) == len(b) == 90              # 82 + 4 'Diesel' + 4 'diesel '


def test_get_one_vehicle():
    response = client.get("/vehicles/1")
    assert response.status_code == 200
    assert response.json()["vehicle_id"] == 1


def test_unknown_vehicle_returns_404():
    response = client.get("/vehicles/99999")
    assert response.status_code == 404


def test_limit_too_big_is_rejected():
    response = client.get("/vehicles", params={"limit": 10000})
    assert response.status_code == 422        # validation error


def test_sql_injection_attempt_is_harmless():
    """A malicious 'depot' value is treated as plain text, not as SQL."""
    response = client.get("/vehicles", params={"depot": "Tokyo'; DROP TABLE vehicles; --"})
    assert response.status_code == 200
    assert response.json() == []
    assert client.get("/vehicles/1").status_code == 200   # table still exists


def test_open_warnings_are_really_open():
    # find a vehicle that has at least one open warning
    for vehicle_id in range(1, 201):
        warnings = client.get(f"/vehicles/{vehicle_id}/warnings", params={"open_only": True}).json()
        if warnings:
            assert all(w["resolved_at"] is None for w in warnings)
            return
    raise AssertionError("expected at least one vehicle with open warnings")
