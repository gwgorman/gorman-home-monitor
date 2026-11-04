"""Install as satellite_telemetry.py beside shared_orbits.py on client displays.

Set HOME_ORBITS_URL in the display's service environment. The original
SatelliteTelemetryService/snapshot interface is preserved without upstream I/O.
"""
from shared_orbits import SharedSatelliteTelemetryService as SatelliteTelemetryService
from shared_orbits import catalog_condition
