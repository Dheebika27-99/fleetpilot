-- FleetPilot "clean layer"
-- The raw tables keep every row exactly as the sensors sent it (nothing is lost).
-- These views give the API, dashboards and (later) the chatbot a cleaned version.
--
--   raw tables  ──►  clean views  ──►  API / chatbot
--   (everything)     (trusted)

-- Vehicles: normalise messy text ('Diesel', 'diesel ' -> 'diesel')
CREATE OR REPLACE VIEW clean_vehicles AS
SELECT
    vehicle_id, license_plate, make, model, vehicle_type, year,
    LOWER(TRIM(fuel_type)) AS fuel_type,
    depot, mileage_km, purchased_on, last_service, status,
    created_at, updated_at
FROM vehicles;

-- Sensor readings:
--   1. remove duplicates: keep ONE reading per (vehicle_id, recorded_at),
--      the one with the smallest reading_id (the original)
--   2. impossible values become NULL (unknown) instead of poisoning AVG()
CREATE OR REPLACE VIEW clean_sensor_readings AS
SELECT
    reading_id, vehicle_id, trip_id, recorded_at,
    CASE WHEN speed_kmh < 0 OR speed_kmh > 200 THEN NULL ELSE speed_kmh END            AS speed_kmh,
    CASE WHEN engine_temp_c < -40 OR engine_temp_c > 150 THEN NULL ELSE engine_temp_c END AS engine_temp_c,
    fuel_level_pct, battery_pct, mileage_km
FROM (
    SELECT DISTINCT ON (vehicle_id, recorded_at) *
    FROM sensor_readings
    ORDER BY vehicle_id, recorded_at, reading_id
) AS one_per_minute;
