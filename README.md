# Gorman Home Monitor

Designed and built by **Greg Gorman with Max (OpenAI Codex)**.

An always-on Raspberry Pi office display: local weather, aircraft with a permanently enabled radar overlay, sky positions, household sensors, cold storage, pool/spa, lake levels and batteries. Ten pages rotate automatically; a weather-alert band stays visible throughout. Read-only views are available to other devices on the configured home network.

## Features

- Direct local WeatherFlow UDP observations; wind compass and instrument gauges grouped like a weather station, with a locally retained 24-hour pressure history. No weather-station cloud token.
- Independent National Weather Service alerts, 48 hourly forecast periods and five detailed forecast days.
- Local PiAware/SkyAware aircraft tracks and cached Iowa Environmental Mesonet NEXRAD tiles. Radar stays enabled; unavailable or delayed feeds are labeled.
- Skyfield orbital predictions using CelesTrak catalogs, plus planets and bright stars.
- Whole-house SmartThings inventory through the kitchen dashboard's existing credential manager. This avoids competing OAuth refresh tokens. YoLink and iAquaLink readings use the same read-only kitchen API.
- USGS Lewisville Lake elevation and Trinity River flow/stage.
- Visible report ages, unknown values instead of invented zeroes, and paginated device/battery inventories.
- Compact monitoring interface: grouped house summaries, filled/dark switch symbols, battery indicators and red attention states. Hourly weather shows the next six hours in six chronological rows; the complete five-day outlook remains on one page. Weather station readings, wind compass, pressure history, solar gauges and lightning share one page. Ten detailed aircraft tapes and four overhead satellites and six upcoming passes fit beside their plots. Country flags identify launch origin, matching the original console. House and battery layouts mirror the working console, with 12 grouped house cards (plus additional ungrouped devices) and 12 segmented battery cards per view. Device lists page every 15 seconds inside each 30-second page; radar annotations remain compact. Automatic browser recovery and persistent Wi-Fi power-save fix.

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

See [feature inventory](INVENTORY.md) for coverage and remaining integrations. ERCOT, Richland Chambers, irrigation history and water-meter usage are not yet implemented; retiring the old screen does not retire those upstream systems or the old MQTT broker.

## Authors

Greg Gorman — project owner, requirements and installation.

Max (OpenAI Codex) — AI engineering collaborator, implementation and validation.

MIT licensed. Collectors were adapted from Greg and Max's Raspberry Pi console work; the office application is independently deployed.

## Display data and graphics

Battery icons use source-reported percentages (green full at 60% or higher, green half from 20%, red below 20%). [YoLink THSensor battery levels](https://doc.yosmart.com/docs/yolinkapi/THSensor/) use their native 0–4 scale, never a claimed percentage. WeatherFlow voltage remains a voltage reading with a neutral battery outline. Sensor alarms, wet leak sensors, offline/error states and low batteries receive red emphasis; recent lightning strikes highlight the lightning panel. No generic temperature alarms are inferred from unlike devices.

Satellite flags show launch country/location, independently of the [CelesTrak owner code](https://celestrak.org/satcat/sources.php); hover details retain both. Local flag artwork is from [Twemoji](https://github.com/jdecked/twemoji), licensed CC BY 4.0 (see static/flags/LICENSE-GRAPHICS). Noto Color Emoji also supports other symbols on the Pi.

Airline/operator banners are stored locally for common ICAO callsign prefixes, sourced from [Jxck-S/airline-logos](https://github.com/Jxck-S/airline-logos/tree/main/fr24_banners). Unrecognized or private callsigns keep their plain identifier. Airline marks remain the property of their owners and are outside the code MIT license; see static/logos/NOTICE.md.
