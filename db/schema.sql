-- FleetPilot database schema
-- Safe to re-run: drops old tables first (only for development!)
DROP TABLE IF EXISTS warnings, sensor_readings, trips, drivers, vehicles CASCADE;

CREATE TABLE vehicles (
    vehicle_id     INTEGER PRIMARY KEY,
    license_plate  TEXT NOT NULL UNIQUE,
    make           TEXT NOT NULL,
    model          TEXT NOT NULL,
    vehicle_type   TEXT NOT NULL,
    year           INTEGER NOT NULL,
    fuel_type      TEXT NOT NULL,
    depot          TEXT NOT NULL,
    mileage_km     INTEGER NOT NULL,
    purchased_on   DATE NOT NULL,
    last_service   DATE,              
    status         TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    updated_at     TIMESTAMP NOT NULL
);

CREATE TABLE drivers (
    driver_id       INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    license_number  TEXT NOT NULL UNIQUE,
    depot           TEXT NOT NULL,
    hired_on        DATE NOT NULL,
    status          TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);

CREATE TABLE trips (
    trip_id           INTEGER PRIMARY KEY,
    vehicle_id        INTEGER NOT NULL REFERENCES vehicles(vehicle_id),
    driver_id         INTEGER NOT NULL REFERENCES drivers(driver_id),
    started_at        TIMESTAMP NOT NULL,
    ended_at          TIMESTAMP,         
    distance_km       NUMERIC NOT NULL,
    fuel_used_liters  NUMERIC            
);

CREATE TABLE sensor_readings (
    reading_id      BIGINT PRIMARY KEY,
    vehicle_id      INTEGER NOT NULL REFERENCES vehicles(vehicle_id),
    trip_id         INTEGER REFERENCES trips(trip_id), 
    recorded_at     TIMESTAMP NOT NULL,
    speed_kmh       NUMERIC,
    engine_temp_c   NUMERIC,
    fuel_level_pct  NUMERIC,
    battery_pct     NUMERIC,
    mileage_km      INTEGER
);

CREATE TABLE warnings (
    warning_id   INTEGER PRIMARY KEY,
    vehicle_id   INTEGER NOT NULL REFERENCES vehicles(vehicle_id),
    trip_id      INTEGER REFERENCES trips(trip_id),               
    occurred_at  TIMESTAMP NOT NULL,
    code         TEXT NOT NULL,
    severity     TEXT NOT NULL,
    message      TEXT,
    resolved_at  TIMESTAMP                                      
);