"""
FleetPilot API.

Run:   uvicorn app.main:app --reload
Docs:  http://localhost:8000/docs   (interactive test page, made by FastAPI)
"""

from typing import List, Optional

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from app.config import DATABASE_URL
from app.db import get_conn
from app.llm.router import router as llm_router
from app.prediction import router as prediction_router
from app.schemas import Health, Vehicle, Warning

app = FastAPI(
    title="FleetPilot API",
    description="Fleet telemetry API: vehicles, warnings, failure-risk predictions and an LLM gateway.",
    version="0.3.0",
)
app.include_router(prediction_router)
app.include_router(llm_router)

# The API reads from the CLEAN layer (views), never from raw sensor tables.
VEHICLE_COLUMNS = """
    vehicle_id, license_plate, make, model, vehicle_type, year, fuel_type,
    depot, mileage_km, last_service, status
"""


@app.get("/health", response_model=Health)
def health():
    """Is the API up, and can it reach the database?"""
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return Health(status="ok", database="ok")
    except psycopg.OperationalError:
        # 503 = "service unavailable": the API runs, but a dependency is down
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unreachable"})


@app.get("/vehicles", response_model=List[Vehicle])
def list_vehicles(
    depot: Optional[str] = None,
    status: Optional[str] = None,
    fuel_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn=Depends(get_conn),
):
    """List vehicles, optionally filtered by depot, status or fuel type."""
    where, params = [], []
    if depot:
        where.append("depot = %s")
        params.append(depot)
    if status:
        where.append("status = %s")
        params.append(status)
    if fuel_type:
        where.append("fuel_type = %s")
        params.append(fuel_type.lower().strip())

    sql = f"SELECT {VEHICLE_COLUMNS} FROM clean_vehicles"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY vehicle_id LIMIT %s OFFSET %s"
    params += [limit, offset]

    # %s placeholders: the driver sends values separately from the SQL,
    # so user input can never change the query (prevents SQL injection).
    return conn.execute(sql, params).fetchall()


@app.get("/vehicles/{vehicle_id}", response_model=Vehicle)
def get_vehicle(vehicle_id: int, conn=Depends(get_conn)):
    """One vehicle by ID. 404 if it doesn't exist."""
    row = conn.execute(
        f"SELECT {VEHICLE_COLUMNS} FROM clean_vehicles WHERE vehicle_id = %s",
        [vehicle_id],
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Vehicle {vehicle_id} not found")
    return row


@app.get("/vehicles/{vehicle_id}/warnings", response_model=List[Warning])
def vehicle_warnings(vehicle_id: int, open_only: bool = False, conn=Depends(get_conn)):
    """Warnings for one vehicle, newest first. open_only=true -> only unresolved ones."""
    exists = conn.execute("SELECT 1 FROM vehicles WHERE vehicle_id = %s", [vehicle_id]).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail=f"Vehicle {vehicle_id} not found")

    sql = "SELECT * FROM warnings WHERE vehicle_id = %s"
    if open_only:
        sql += " AND resolved_at IS NULL"
    sql += " ORDER BY occurred_at DESC"
    return conn.execute(sql, [vehicle_id]).fetchall()
