"""
Response shapes (Pydantic models).
FastAPI uses them to validate what we send back and to build the /docs page.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class Health(BaseModel):
    status: str
    database: str


class Vehicle(BaseModel):
    vehicle_id: int
    license_plate: str
    make: str
    model: str
    vehicle_type: str
    year: int
    fuel_type: str
    depot: str
    mileage_km: int
    last_service: Optional[date]      # NULL = never serviced yet
    status: str


class Warning(BaseModel):
    warning_id: int
    vehicle_id: int
    trip_id: Optional[int]            # NULL = happened while parked
    occurred_at: datetime
    code: str
    severity: str
    message: Optional[str]
    resolved_at: Optional[datetime]   # NULL = not fixed yet
