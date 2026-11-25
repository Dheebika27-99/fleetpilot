# Brake inspection policy

*Sample policy for the fictional company FleetPilot Logistics. Not manufacturer guidance.*

## How often
- Trucks and vans: inspect brake pads and discs every **20,000 km** or every **3 months**, whichever comes first.
- Cars (Prius, bZ4X): every **30,000 km** or every **6 months**.
- Vehicles in city delivery with many stops: halve the distance interval (10,000 km for trucks).

## Replace when
- Pad thickness is **3 mm or less**.
- Discs are scored, cracked or below the minimum thickness marked on the disc.
- A BRAKE_WEAR warning is active (see the warning-code playbook).

## After a BRAKE_WEAR warning
1. The driver finishes the current delivery at reduced speed and avoids highways.
2. The vehicle must be inspected within **48 hours**.
3. If the inspection confirms wear, the vehicle status is set to `repair` until the work is done.
