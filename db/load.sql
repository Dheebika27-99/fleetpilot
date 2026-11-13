-- Load the generated CSV files into the FleetPilot tables.
-- Run from the repo folder:  psql -d fleetpilot -f db/schema.sql -f db/load.sql
-- Order matters: parents (vehicles, drivers) before children (trips, readings, warnings),
-- because the foreign keys check that every pointer is valid.

\copy vehicles        FROM 'data/vehicles.csv'        WITH (FORMAT csv, HEADER true)
\copy drivers         FROM 'data/drivers.csv'         WITH (FORMAT csv, HEADER true)
\copy trips           FROM 'data/trips.csv'           WITH (FORMAT csv, HEADER true)
\copy sensor_readings FROM 'data/sensor_readings.csv' WITH (FORMAT csv, HEADER true)
\copy warnings        FROM 'data/warnings.csv'        WITH (FORMAT csv, HEADER true)

-- Quick check: how many rows landed in each table?
SELECT 'vehicles' AS table_name, COUNT(*) AS rows FROM vehicles
UNION ALL SELECT 'drivers', COUNT(*) FROM drivers
UNION ALL SELECT 'trips', COUNT(*) FROM trips
UNION ALL SELECT 'sensor_readings', COUNT(*) FROM sensor_readings
UNION ALL SELECT 'warnings', COUNT(*) FROM warnings;
