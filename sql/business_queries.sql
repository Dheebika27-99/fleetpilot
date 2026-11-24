-- FleetPilot: 10 questions a fleet manager asks, answered in SQL.
-- They read from the CLEAN layer (clean_vehicles, clean_sensor_readings).
-- Later these become the "golden set" for testing the text-to-SQL chatbot:
-- the bot's answer must match the answer of these hand-written queries.

-- Q1. How many vehicles does each depot have?
SELECT depot, COUNT(*) AS num_vehicles
FROM clean_vehicles
GROUP BY depot
ORDER BY num_vehicles DESC;

-- Q2. How many vehicles of each fuel type? (clean layer fixes 'Diesel' / 'diesel ')
SELECT fuel_type, COUNT(*) AS num_vehicles
FROM clean_vehicles
GROUP BY fuel_type
ORDER BY num_vehicles DESC;

-- Q3. Which vehicles have never been serviced?
SELECT vehicle_id, license_plate, model, depot
FROM clean_vehicles
WHERE last_service IS NULL
ORDER BY vehicle_id;

-- Q4. Which non-retired vehicles made no trips in the last 60 days? (unused = wasted money)
SELECT v.vehicle_id, v.model, v.depot, v.status
FROM clean_vehicles v
LEFT JOIN trips t ON v.vehicle_id = t.vehicle_id
WHERE t.trip_id IS NULL AND v.status <> 'retired'
ORDER BY v.vehicle_id;

-- Q5. Which trips are still in progress?
SELECT trip_id, vehicle_id, driver_id, started_at
FROM trips
WHERE ended_at IS NULL
ORDER BY started_at DESC;

-- Q6. Total distance and average trip length per vehicle type
SELECT v.vehicle_type,
       COUNT(*)                     AS num_trips,
       ROUND(SUM(t.distance_km), 1) AS total_km,
       ROUND(AVG(t.distance_km), 1) AS avg_trip_km
FROM trips t
JOIN clean_vehicles v ON t.vehicle_id = v.vehicle_id
GROUP BY v.vehicle_type
ORDER BY total_km DESC;

-- Q7. Which open (unresolved) warnings are high severity, and where is the truck?
SELECT w.warning_id, w.occurred_at, w.code, v.vehicle_id, v.model, v.depot
FROM warnings w
JOIN clean_vehicles v ON w.vehicle_id = v.vehicle_id
WHERE w.resolved_at IS NULL AND w.severity = 'high'
ORDER BY w.occurred_at DESC;

-- Q8. Which warning types are most common, and how many are still open?
SELECT code,
       COUNT(*)                                   AS total,
       COUNT(*) FILTER (WHERE resolved_at IS NULL) AS still_open
FROM warnings
GROUP BY code
ORDER BY total DESC;

-- Q9. Top 5 drivers by total distance driven
SELECT d.driver_id, d.name, d.depot,
       COUNT(t.trip_id)              AS num_trips,
       ROUND(SUM(t.distance_km), 1) AS total_km
FROM drivers d
JOIN trips t ON d.driver_id = t.driver_id
GROUP BY d.driver_id, d.name, d.depot
ORDER BY total_km DESC
LIMIT 5;

-- Q10. Average speed and engine temperature per vehicle type (clean readings only)
SELECT v.vehicle_type,
       ROUND(AVG(r.speed_kmh), 1)     AS avg_speed_kmh,
       ROUND(AVG(r.engine_temp_c), 1) AS avg_engine_temp_c
FROM clean_sensor_readings r
JOIN clean_vehicles v ON r.vehicle_id = v.vehicle_id
WHERE r.trip_id IS NOT NULL
GROUP BY v.vehicle_type
ORDER BY v.vehicle_type;
