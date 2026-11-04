# Feature inventory

| Page | Source | Status |
|---|---|---|
| Overview | Direct kitchen device inventory and local weather | Implemented, source ages visible |
| Weather station | WeatherFlow UDP 50222 | Implemented, locally retained pressure history (up to 24 hours) |
| Hourly forecast | National Weather Service | 48 hours, eight periods per rotation |
| Five-day forecast | National Weather Service | Day/night narratives |
| Air traffic | Local PiAware plus IEM NEXRAD | Implemented, radar always enabled |
| Space | CelesTrak and Skyfield | Predicted positions and passes |
| House devices | SmartThings via kitchen credential manager | Paginated read-only capabilities |
| Cold storage and pool | Kitchen YoLink, SmartThings, iAquaLink | Pool/spa may report only in the active mode |
| Lake and river | USGS | Lewisville and Trinity implemented |
| Batteries | SmartThings via kitchen API | Reported percentages and ages |

Permanent NWS alert band across all pages. Local network access only by default. No MQTT, party controls, photos or calendar pages.

Remaining integrations: Richland Chambers, lake gates/history, ERCOT power-grid data, irrigation history and water-meter usage. Environmental sensors require a working source before any values are displayed. These gaps are explicit; old default/zero readings are not used as evidence that devices are healthy.

Operational checks for each deployment: confirm source timestamps, weather radar tile delivery, full display layout, page rotation, browser recovery and reboot startup. Do not stop a legacy broker or data source until its remaining consumers are identified.
