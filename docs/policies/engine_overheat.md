# Engine overheating response

*Sample policy for the fictional company FleetPilot Logistics. Not manufacturer guidance.*

Normal engine temperature for our diesel and hybrid vehicles is about **80 to 105 °C**.

## ENGINE_OVERHEAT warning (severity: high)
1. Stop the vehicle as soon as it is safe and switch off the engine.
2. Do **not** open the radiator cap while the engine is hot.
3. Wait at least **30 minutes**, then check the coolant level.
4. Call the depot. The vehicle must not continue until a mechanic approves it.
5. The fleet manager sets the vehicle status to `repair`.

## Sensor errors
A reading such as **999 °C** is not a real temperature: it is a sensor error code.
Report it as a faulty sensor, not as an overheat. Two or more sensor errors in a week
means the sensor must be replaced.
