"""
FleetPilot fake-data generator.

Creates a realistic (but 100% made-up) delivery fleet and writes it to CSV files
in the data/ folder, one file per table:

    vehicles.csv, drivers.csv, trips.csv, sensor_readings.csv, warnings.csv

It also PLANTS BUGS on purpose (duplicates, missing values, broken sensor values,
messy text) so we can practise finding them with SQL later.
The answer key is saved to data/_planted_bugs.json (no peeking until W2!).

Uses only Python's standard library: no pip install needed.

Run:  python3 scripts/generate_data.py
"""

import csv
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Settings (change these to make a bigger or smaller fleet)
# ---------------------------------------------------------------------------
SEED = 42                       # same seed = same data every run (reproducible)
NUM_VEHICLES = 200
NUM_DRIVERS = 80
TRIPS_PER_VEHICLE = 10          # on average, for active vehicles
READING_EVERY_MINUTES = 1       # one sensor reading per minute while driving
END_DATE = datetime(2026, 11, 1)  # data covers the 60 days before this date
DAYS = 60

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DEPOTS = ["Tokyo", "Osaka", "Nagoya", "Fukuoka", "Sapporo"]

# make, model, vehicle_type, fuel_type
MODELS = [
    ("Toyota", "Hiace", "van", "diesel"),
    ("Toyota", "Dyna", "truck", "diesel"),
    ("Isuzu", "Elf", "truck", "diesel"),
    ("Hino", "Dutro", "truck", "hybrid"),
    ("Toyota", "Prius", "car", "hybrid"),
    ("Nissan", "Caravan", "van", "gasoline"),
    ("Toyota", "bZ4X", "suv", "electric"),
    ("Fuso", "eCanter", "truck", "electric"),
]

FAMILY_NAMES = ["Sato", "Suzuki", "Takahashi", "Tanaka", "Watanabe", "Ito",
                "Yamamoto", "Nakamura", "Kobayashi", "Kato", "Yoshida", "Yamada"]
GIVEN_NAMES = ["Haruto", "Yuto", "Sota", "Ren", "Yui", "Aoi", "Hina",
               "Sakura", "Kenji", "Mei", "Daiki", "Riko"]

# warning code -> which fuel types can get it
WARNING_CODES = {
    "ENGINE_OVERHEAT": ["diesel", "hybrid", "gasoline"],
    "LOW_TIRE_PRESSURE": ["diesel", "hybrid", "gasoline", "electric"],
    "CHECK_ENGINE": ["diesel", "hybrid", "gasoline"],
    "BATTERY_LOW": ["electric", "hybrid"],
    "BRAKE_WEAR": ["diesel", "hybrid", "gasoline", "electric"],
}
SEVERITY = {
    "ENGINE_OVERHEAT": "high",
    "CHECK_ENGINE": "medium",
    "BRAKE_WEAR": "medium",
    "LOW_TIRE_PRESSURE": "low",
    "BATTERY_LOW": "low",
}


def ts(dt):
    """Format a datetime the way Postgres likes it: 2026-10-05 08:30:00"""
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def write_csv(filename, rows):
    """Write a list of dictionaries to data/<filename> with a header row."""
    path = DATA_DIR / filename
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)      # None is written as empty -> NULL in Postgres
    print(f"  {filename:<22} {len(rows):>7} rows")


# ---------------------------------------------------------------------------
# 1. Vehicles
# ---------------------------------------------------------------------------
def make_vehicles():
    vehicles = []
    for vehicle_id in range(1, NUM_VEHICLES + 1):
        make, model, vehicle_type, fuel_type = random.choice(MODELS)
        year = random.randint(2014, 2025)
        purchased_on = date(year, random.randint(1, 12), random.randint(1, 28))
        status = random.choices(["active", "repair", "retired"], weights=[85, 10, 5])[0]
        depot = random.choice(DEPOTS)
        vehicles.append({
            "vehicle_id": vehicle_id,
            # vehicle_id inside the plate keeps it unique
            "license_plate": f"{depot} {random.randint(100, 999)} {vehicle_id:02d}-{random.randint(10, 99)}",
            "make": make,
            "model": model,
            "vehicle_type": vehicle_type,
            "year": year,
            "fuel_type": fuel_type,
            "depot": depot,
            # mileage before our 60 days of data; trips add to it below
            "mileage_km": (2026 - year) * random.randint(8_000, 25_000),
            "purchased_on": purchased_on.isoformat(),
            # ~10% have no service record yet (an honest NULL)
            "last_service": None if random.random() < 0.10 else
                (END_DATE - timedelta(days=random.randint(10, 400))).date().isoformat(),
            "status": status,
            "created_at": ts(datetime.combine(purchased_on, datetime.min.time())),
            "updated_at": ts(END_DATE - timedelta(hours=random.randint(1, 72))),
        })
    return vehicles


# ---------------------------------------------------------------------------
# 2. Drivers
# ---------------------------------------------------------------------------
def make_drivers():
    drivers = []
    for driver_id in range(1, NUM_DRIVERS + 1):
        hired_on = date(random.randint(2012, 2025), random.randint(1, 12), random.randint(1, 28))
        drivers.append({
            "driver_id": driver_id,
            "name": f"{random.choice(GIVEN_NAMES)} {random.choice(FAMILY_NAMES)}",
            "license_number": f"DL-{driver_id:06d}",
            "depot": random.choice(DEPOTS),
            "hired_on": hired_on.isoformat(),
            "status": random.choices(["active", "inactive"], weights=[92, 8])[0],
            "created_at": ts(datetime.combine(hired_on, datetime.min.time())),
            "updated_at": ts(END_DATE - timedelta(days=random.randint(1, 30))),
        })
    return drivers


# ---------------------------------------------------------------------------
# 3. Trips + 4. Sensor readings (made together: readings happen during trips)
# ---------------------------------------------------------------------------
def make_trips_and_readings(vehicles, drivers):
    trips, readings = [], []
    trip_id, reading_id = 1, 1
    start_day = END_DATE - timedelta(days=DAYS)
    active_drivers = [d for d in drivers if d["status"] == "active"]

    for v in vehicles:
        if v["status"] == "retired":
            continue                         # retired trucks make no trips
        n_trips = TRIPS_PER_VEHICLE if v["status"] == "active" else 2
        n_trips = max(1, n_trips + random.randint(-3, 3))
        days = sorted(random.sample(range(DAYS), n_trips))   # one trip per chosen day
        mileage = v["mileage_km"]
        fuel_level = random.uniform(60, 100)
        battery = random.uniform(60, 100)
        is_last_vehicle_trip_open = random.random() < 0.03   # a few trips still running

        # drivers from the same depot, if any
        depot_drivers = [d for d in active_drivers if d["depot"] == v["depot"]] or active_drivers

        for i, day in enumerate(days):
            started_at = start_day + timedelta(days=day, hours=random.randint(6, 17),
                                               minutes=random.randint(0, 59))
            duration_min = random.randint(20, 90)
            in_progress = is_last_vehicle_trip_open and i == len(days) - 1
            if in_progress:
                duration_min = random.randint(5, 20)          # only driven a bit so far

            # ---- sensor readings, one per minute -------------------------
            distance = 0.0
            for minute in range(0, duration_min, READING_EVERY_MINUTES):
                speed = max(0.0, random.gauss(45, 15))
                distance += speed / 60
                mileage_now = mileage + int(distance)
                engine_temp = random.gauss(92, 4)
                if v["fuel_type"] != "electric":
                    fuel_level = max(5.0, fuel_level - random.uniform(0.05, 0.2))
                if v["fuel_type"] in ("electric", "hybrid"):
                    battery = max(3.0, battery - random.uniform(0.05, 0.3))
                readings.append({
                    "reading_id": reading_id,
                    "vehicle_id": v["vehicle_id"],
                    "trip_id": trip_id,
                    "recorded_at": ts(started_at + timedelta(minutes=minute)),
                    "speed_kmh": round(speed, 1),
                    # electric trucks have no engine and no fuel tank -> honest NULLs
                    "engine_temp_c": None if v["fuel_type"] == "electric" else round(engine_temp, 1),
                    "fuel_level_pct": None if v["fuel_type"] == "electric" else round(fuel_level, 1),
                    "battery_pct": round(battery, 1) if v["fuel_type"] in ("electric", "hybrid") else None,
                    "mileage_km": mileage_now,
                })
                reading_id += 1

            mileage += int(distance)
            if v["fuel_type"] == "electric":
                battery = random.uniform(70, 100)        # recharged overnight
            elif fuel_level < 30:
                fuel_level = random.uniform(80, 100)     # refuelled

            driver = random.choice(depot_drivers)
            trips.append({
                "trip_id": trip_id,
                "vehicle_id": v["vehicle_id"],
                "driver_id": driver["driver_id"],
                "started_at": ts(started_at),
                "ended_at": None if in_progress else ts(started_at + timedelta(minutes=duration_min)),
                "distance_km": round(distance, 1),
                # electric = no fuel; in-progress = not known yet
                "fuel_used_liters": None if (v["fuel_type"] == "electric" or in_progress)
                                    else round(distance * random.uniform(0.08, 0.14), 2),
            })
            trip_id += 1

        # a parked "heartbeat" reading at the end of the period (no trip -> trip_id NULL)
        readings.append({
            "reading_id": reading_id,
            "vehicle_id": v["vehicle_id"],
            "trip_id": None,
            "recorded_at": ts(END_DATE - timedelta(minutes=random.randint(1, 600))),
            "speed_kmh": 0.0,
            "engine_temp_c": None,
            "fuel_level_pct": None if v["fuel_type"] == "electric" else round(fuel_level, 1),
            "battery_pct": round(battery, 1) if v["fuel_type"] in ("electric", "hybrid") else None,
            "mileage_km": mileage,
        })
        reading_id += 1
        v["mileage_km"] = mileage            # latest snapshot in the vehicles table

    return trips, readings


# ---------------------------------------------------------------------------
# 5. Warnings
# ---------------------------------------------------------------------------
def make_warnings(vehicles, trips):
    by_id = {v["vehicle_id"]: v for v in vehicles}
    warnings = []
    warning_id = 1

    def add_warning(vehicle, trip_id, occurred_at):
        nonlocal warning_id
        possible = [c for c, fuels in WARNING_CODES.items() if vehicle["fuel_type"] in fuels]
        code = random.choice(possible)
        # 70% fixed within a few days, 30% still open (honest NULL)
        resolved = None
        if random.random() < 0.70:
            resolved = occurred_at + timedelta(hours=random.randint(2, 120))
            if resolved > END_DATE:
                resolved = None
        warnings.append({
            "warning_id": warning_id,
            "vehicle_id": vehicle["vehicle_id"],
            "trip_id": trip_id,
            "occurred_at": ts(occurred_at),
            "code": code,
            "severity": SEVERITY[code],
            "message": None if random.random() < 0.15 else code.replace("_", " ").lower() + " detected",
            "resolved_at": ts(resolved),
        })
        warning_id += 1

    # warnings during trips (~20% of trips)
    for t in trips:
        if random.random() < 0.20:
            start = datetime.strptime(t["started_at"], "%Y-%m-%d %H:%M:%S")
            add_warning(by_id[t["vehicle_id"]], t["trip_id"], start + timedelta(minutes=random.randint(1, 15)))

    # warnings while parked (no trip)
    for _ in range(80):
        v = random.choice(vehicles)
        add_warning(v, None, END_DATE - timedelta(days=random.randint(0, DAYS - 1), hours=random.randint(0, 23)))

    return warnings


# ---------------------------------------------------------------------------
# 6. Plant bugs on purpose 🐛
# ---------------------------------------------------------------------------
def plant_bugs(vehicles, readings):
    key = {}

    # Shuffle the driving readings once, then take SEPARATE slices for each bug,
    # so no reading gets two bugs and the answer key stays exact.
    pool = [r for r in readings if r["trip_id"] is not None]
    random.shuffle(pool)
    n_dup, n_drop, n_bad = len(readings) // 200, len(readings) // 100, 40
    to_copy = pool[:n_dup]
    dropouts = pool[n_dup:n_dup + n_drop]
    broken_speed = pool[n_dup + n_drop:n_dup + n_drop + n_bad]
    rest = [r for r in pool[n_dup + n_drop + n_bad:] if r["engine_temp_c"] is not None]
    broken_temp = rest[:n_bad]

    # 🐛 sensor dropouts: speed missing on readings that SHOULD have it
    for r in dropouts:
        r["speed_kmh"] = None
    key["missing_speed"] = len(dropouts)

    # 🐛 broken sensors: impossible values
    for r in broken_speed:
        r["speed_kmh"] = -50.0
    for r in broken_temp:
        r["engine_temp_c"] = 999.0
    key["negative_speed"] = len(broken_speed)
    key["engine_temp_999"] = len(broken_temp)

    # 🐛 duplicate sensor readings: same vehicle + same time + same values, new reading_id
    next_id = max(r["reading_id"] for r in readings) + 1
    for r in to_copy:
        copy = dict(r)
        copy["reading_id"] = next_id
        next_id += 1
        readings.append(copy)
    key["duplicate_readings"] = len(to_copy)

    # 🐛 messy text: 'Diesel' / 'diesel ' instead of 'diesel'
    diesels = [v for v in vehicles if v["fuel_type"] == "diesel"]
    messy = random.sample(diesels, k=min(8, len(diesels)))
    for i, v in enumerate(messy):
        v["fuel_type"] = "Diesel" if i % 2 == 0 else "diesel "
    key["messy_fuel_type"] = len(messy)

    # keep readings in time order per vehicle (duplicates now sit next to originals)
    readings.sort(key=lambda r: (r["vehicle_id"], r["recorded_at"], r["reading_id"]))
    return key


def main():
    random.seed(SEED)
    DATA_DIR.mkdir(exist_ok=True)

    vehicles = make_vehicles()
    drivers = make_drivers()
    trips, readings = make_trips_and_readings(vehicles, drivers)
    warnings = make_warnings(vehicles, trips)
    bug_key = plant_bugs(vehicles, readings)

    print("Writing CSV files to", DATA_DIR)
    write_csv("vehicles.csv", vehicles)
    write_csv("drivers.csv", drivers)
    write_csv("trips.csv", trips)
    write_csv("sensor_readings.csv", readings)
    write_csv("warnings.csv", warnings)

    with open(DATA_DIR / "_planted_bugs.json", "w") as f:
        json.dump(bug_key, f, indent=2)
    print("Done. Answer key saved to data/_planted_bugs.json (don't peek yet!)")


if __name__ == "__main__":
    main()
