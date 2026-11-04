# Gorman Home Monitor

Designed and built by **Greg Gorman with Max (OpenAI Codex)**.

An always-on Raspberry Pi office display: local weather, aircraft with a permanently enabled radar overlay, sky positions, household sensors, cold storage, pool/spa, lake levels and batteries. Twelve pages rotate automatically; a weather-alert band appears for active alerts or unavailable alert updates. Read-only views are available to other devices on the configured home network.

## Features

- Direct local WeatherFlow UDP observations; wind compass and instrument gauges grouped like a weather station, with a locally retained 24-hour pressure history. No weather-station cloud token.
- Independent National Weather Service alerts, 48 hourly forecast periods and five detailed forecast days.
- Local PiAware/SkyAware aircraft tracks and cached Iowa Environmental Mesonet NEXRAD tiles. Radar stays enabled; unavailable or delayed feeds are labeled. The 80 NM scope uses the console square-root range scale to expand nearby airspace. Aircraft, trails, distance rings and weather imagery share that projection; radar tiles are inverse-warped once per image update and cached.
- Skyfield orbital predictions using CelesTrak catalogs, plus planets and bright stars.
- Whole-house SmartThings inventory through the kitchen dashboard's existing credential manager. This avoids competing OAuth refresh tokens. YoLink and iAquaLink readings use the same read-only kitchen API.
- USGS Lewisville and Richland-Chambers lake elevation, seven-day level/rainfall histories, 24-hour/seven-day trends, lake wind and Trinity River flow/stage. USACE dam-release reports retain their own timestamp. Individual gate-position indicators are retired because no current public position feed has been verified.
- Visible report ages, unknown values instead of invented zeroes, and paginated device/battery inventories.
- Compact monitoring interface: grouped house summaries, filled/dark switch symbols, battery indicators and red attention states. Hourly weather shows the next six hours in six chronological rows; the complete five-day outlook remains on one page. Weather station readings, wind compass, pressure history, solar gauges and lightning share one page. Ten detailed aircraft tapes and four overhead satellites and six upcoming passes fit beside their plots. Country flags identify launch origin, matching the original console. House and battery layouts mirror the working console, with 12 house cards per category (Sonos and Thermal & Pool), 24 matching compact cards for On / Off and Security, and 12 segmented battery cards per view. Security emphasizes the primary state and shows temperature as secondary text. Device lists slide every 10 seconds inside each 30-second section, with Previous/Next tile-page arrows for manual navigation, including while paused. Main sections crossfade; tile pages slide across their full width in the direction of navigation, with the pager anchored above the alert/status area, with transitions suppressed for routine refreshes and reduced-motion preferences; radar annotations remain compact. Automatic browser recovery and persistent Wi-Fi power-save fix.

No MQTT dependency, photos, calendars, party controls, GPIO actions or sound. No dependency on the party display application. The kitchen API remains a separate runtime dependency for household devices; weather, aircraft and space collectors run independently.

## Installation

Tested on a Raspberry Pi 4 with 8GB RAM, Raspbian 11 (32-bit armhf userland), Python 3.9, Chromium and a 1920×1080 X11/LXDE display.

```sh
sudo apt-get install python3-venv libopenblas0 curl fonts-noto-color-emoji
python3 -m venv .venv
.venv/bin/python3 -m pip install -r requirements.txt
mkdir -p ~/.config/home-monitor
chmod 700 ~/.config/home-monitor
cp deploy/home-monitor.env.example ~/.config/home-monitor/runtime.env
chmod 600 ~/.config/home-monitor/runtime.env
```

Edit `runtime.env` for your location, trusted LAN subnet, allowed hostnames, aircraft receiver and kitchen API. The example coordinates are neutral placeholders (0, 0); replace them before requesting forecasts. The example LAN permits loopback only; set your trusted subnet explicitly. Personal deployment settings belong outside the repository. Without configuration, HTTP access is restricted to loopback.

Install the checkout as `~/home-monitor`. Then:

```sh
mkdir -p ~/.config/systemd/user
cp deploy/home-monitor.service deploy/home-monitor-kiosk.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now home-monitor.service
```

For a desktop kiosk, back up your existing launcher and have desktop autostart invoke `deploy/start_browser.sh`. It imports the actual X11 session environment, disables screen blanking and starts the supervised Chromium kiosk. The kiosk uses a dedicated profile with extensions disabled, so old tab-rotation/reload extensions cannot alter the new display. Keep a rollback copy of the original launcher. The backend service starts on user login; `sudo loginctl enable-linger "$USER"` also starts it before login.

If Wi-Fi powersave causes interruptions and the adapter is `wlan0`:

```sh
sudo cp deploy/office-wifi-awake.service /etc/systemd/system/
sudo systemctl enable --now office-wifi-awake.service
iw dev wlan0 get power_save
```

The weather station must broadcast UDP port 50222 to the Pi's network. Do not enable a second UDP listener on the same Pi unless broadcast delivery has been tested. Catalog/ephemeris downloads and radar tiles are cached; application data and any credentials stay outside this repository.

## Household integration

`integrations/house_inventory.py` is the read-only inventory adapter added to the kitchen dashboard. It uses that server's existing `SmartThings` instance (`token()` and `fetch()`) and returns display-safe capabilities, component names and source timestamps. Run `inventory(existing_smartthings)` as the kitchen server's `house` worker every five minutes. The office monitor expects the kitchen `/api/dashboard` JSON envelope with `house`, `smartthings`, `sensors` and `aqualink`; no account tokens are copied to the office Pi.

The API is intended for a trusted LAN. It has source-subnet and Host checks, but no login or TLS. Do not forward this port to the internet. Source values may be old even when an API call succeeds; report ages are shown. This display supplements official emergency notifications and cannot guarantee alert delivery during outages.

## Validation and scope

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
```

See [feature inventory](INVENTORY.md) for coverage and remaining integrations. ERCOT, irrigation history and water-meter usage are not yet implemented; retiring the old screen does not retire those upstream systems or the old MQTT broker.

## Authors

Greg Gorman — project owner, requirements and installation.

Max (OpenAI Codex) — AI engineering collaborator, implementation and validation.

MIT licensed. Collectors were adapted from Greg and Max's Raspberry Pi console work; the office application is independently deployed.

## Display data and graphics

Battery icons use source-reported percentages (green full at 60% or higher, green half from 20%, red below 20%). [YoLink THSensor battery levels](https://doc.yosmart.com/docs/yolinkapi/THSensor/) use their native 0–4 scale, never a claimed percentage. WeatherFlow voltage remains a voltage reading with a neutral battery outline. Sensor alarms, wet leak sensors, offline/error states and low batteries receive red emphasis; recent lightning strikes highlight the lightning panel. No generic temperature alarms are inferred from unlike devices.

Satellite flags show launch country/location, independently of the [CelesTrak owner code](https://celestrak.org/satcat/sources.php); hover details retain both. Local flag artwork is from [Twemoji](https://github.com/jdecked/twemoji), licensed CC BY 4.0 (see static/flags/LICENSE-GRAPHICS). Noto Color Emoji also supports other symbols on the Pi.

Airline/operator banners are stored locally for common ICAO callsign prefixes, sourced from [Jxck-S/airline-logos](https://github.com/Jxck-S/airline-logos/tree/main/fr24_banners). Unrecognized or private callsigns keep their plain identifier. Airline marks remain the property of their owners and are outside the code MIT license; see static/logos/NOTICE.md.

### Shared household orbital hub

The office monitor is the sole orbital producer. Its LAN-only `/api/space` endpoint
serves the same satellite positions, Starlink positions, upcoming passes, planets
and bright stars used by its own display. HTTP reads never trigger provider
requests. DE421 stays in the hub's persistent `space-cache`; clients need neither
Skyfield nor their own ephemeris downloads. All clients use the hub's configured
observer location, so this feed is intended for displays at the same house.

To convert a compatible Star Trek display, back up its `satellite_telemetry.py`,
install `shared_orbits.py` beside it and install
`integrations/startrek_satellite_client.py` as `satellite_telemetry.py`. Set
`HOME_ORBITS_URL=http://office-monitor.local:8780/api/space` in its systemd user
service environment, substituting your hub hostname. Reload systemd and restart
the display. The existing start/stop/snapshot interface remains unchanged.
Add the hub hostname to `HOME_MONITOR_HOSTS` and configure its trusted LAN subnet.
There are no account credentials in this public-data feed.

Only the hub contacts CelesTrak. Each catalog refresh attempt reserves at least a
two-hour cooldown on disk **before** network access, including failed attempts;
longer HTTP Retry-After values extend it. A restart preserves that deadline.
Clients poll the LAN every five seconds and never fall back to CelesTrak. They
retain the last snapshot on disk with its original timestamps, and mark the feed
unavailable and hide frozen sky positions after a brief outage. The hub retains
catalogs for propagation while provider downloads recover. Starlink positions
are calculated in batches, so their timestamp can trail the main sky snapshot.

When migrating an existing installation, copy its public TLE cache with preserved
mtime before starting the hub. Seed `download-schedule.json` in `space-cache` with
`catalog` and `starlink` Unix deadlines at least two hours beyond the last known
upstream attempt (or cutover time if unknown). Retire the old collectors first.
Do not remove the schedule to force a download. See the
[CelesTrak usage policy](https://celestrak.org/usage-policy.php).
