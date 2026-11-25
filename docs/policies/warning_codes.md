# Warning-code playbook

*Sample policy for the fictional company FleetPilot Logistics. Not manufacturer guidance.*

What to do for each warning code that appears in the FleetPilot `warnings` table.

| Code | Severity | First action | Deadline |
|---|---|---|---|
| ENGINE_OVERHEAT | high | stop safely, switch off engine, call depot | before driving again |
| CHECK_ENGINE | medium | finish current delivery, avoid heavy loads | inspection within 3 days |
| BRAKE_WEAR | medium | reduce speed, avoid highways | inspection within 48 hours |
| LOW_TIRE_PRESSURE | low | check and inflate at next safe stop | same day |
| BATTERY_LOW | low | charge (electric) or report if repeated (hybrid) | same day |

## Open warnings
A warning is **open** while `resolved_at` is empty. Fleet managers review all open
high-severity warnings every morning. A medium warning open for more than 7 days is escalated.
