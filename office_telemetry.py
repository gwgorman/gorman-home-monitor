"""Read-only system, local WeatherFlow UDP, and USGS collectors."""

from __future__ import annotations

import collections, copy, datetime as dt, json, os, socket, subprocess, threading, time, urllib.request

try:
    import psutil
except ImportError:
    psutil = None

WEATHERFLOW_PORT = 50222
USGS_REFRESH_SECONDS = 900

USGS_URLS = {
    "lake": ("LewisvilleLake", "https://waterservices.usgs.gov/nwis/iv/"
             "?format=json&sites=08052800&siteStatus=all"),
    "trinity": ("TrinityRiver", "https://waterservices.usgs.gov/nwis/iv/"
                "?format=json&sites=08053000&parameterCd=00060%2C00065&siteStatus=all"),
}

def _iso_epoch(value):
    if not value:
        return 0.0
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0

def _walk_mapping(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mapping(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mapping(child)

def _water_summary(topic, payload, now):
    """Parse known water shapes conservatively; an error is never rendered as zero."""
    result = {"updated": now, "error": "", "raw_ok": False}
    if isinstance(payload, str):
        preview = payload.lower()
        if "error" in preview or "<!doctype" in preview or "aborted" in preview:
            result["error"] = "DATA LINK FAULT"
            return result
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            try:
                number = float(payload.strip())
            except (TypeError, ValueError):
                result["error"] = "UNRECOGNIZED FEED"
                return result
            if topic == "LewisvilleLake":
                result.update(elevation_ft=number, raw_ok=True)
            else:
                result.update(flow_cfs=number, raw_ok=True)
            return result
    if isinstance(payload, (int, float)):
        result.update(raw_ok=True)
        result["elevation_ft" if topic == "LewisvilleLake" else "flow_cfs"] = float(payload)
        return result
    # Handle USGS JSON time-series and simple named-key collectors without guessing
    # which anonymous number represents lake elevation or discharge.
    for mapping in _walk_mapping(payload):
        lowered = {str(key).lower(): value for key, value in mapping.items()}
        for key in ("elevation_ft", "elevation", "lakelevel", "lake_level", "reservoir_elevation"):
            if key in lowered:
                try:
                    result["elevation_ft"] = float(lowered[key])
                    result["raw_ok"] = True
                except (TypeError, ValueError):
                    pass
        for key in ("flow_cfs", "discharge", "streamflow", "flow"):
            if key in lowered:
                try:
                    result["flow_cfs"] = float(lowered[key])
                    result["raw_ok"] = True
                except (TypeError, ValueError):
                    pass
        for key in ("gage_ft", "gageheight", "gage_height", "height"):
            if key in lowered:
                try:
                    result["gage_ft"] = float(lowered[key])
                    result["raw_ok"] = True
                except (TypeError, ValueError):
                    pass
        variable = mapping.get("variable") if isinstance(mapping, dict) else None
        values = mapping.get("values") if isinstance(mapping, dict) else None
        if isinstance(variable, dict) and isinstance(values, list) and values:
            codes = variable.get("variableCode") or []
            code = str(codes[0].get("value", "")) if codes and isinstance(codes[0], dict) else ""
            try:
                sample = values[0].get("value", [])[-1]
                number = float(sample.get("value"))
                stamp = _iso_epoch(sample.get("dateTime"))
                if code == "00060":
                    result["flow_cfs"] = number
                elif code == "00065":
                    result["gage_ft"] = number
                elif code == "62614":
                    result["elevation_ft"] = number
                else:
                    continue
                result["updated"] = stamp or now
                result["raw_ok"] = True
            except (AttributeError, IndexError, TypeError, ValueError):
                pass
    if not result["raw_ok"]:
        result["error"] = "UNRECOGNIZED FEED"
    return result

class TelemetryService:
    """Collect local observations without broker or account credentials."""

    def __init__(self):
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._last_net = {}
        self._lightning_observations = collections.OrderedDict()
        self._data = {
            "updated": 0.0,
            "system": {},
            "network": {},
            "weather": {},
            "water": {"lake": {}, "trinity": {}},
            "weatherflow": {"connected": False, "updated": 0.0, "error": "WAITING"},
        }
        self._threads = []

    def start(self):
        if self._threads:
            return
        for target, name in ((self._system_loop, "home-system-telemetry"),
                             (self._weather_loop, "home-weatherflow"),
                             (self._usgs_loop, "home-usgs-water")):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self):
        self._stop.set()

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._data)

    def _system_loop(self):
        if psutil:
            psutil.cpu_percent(interval=None)
        while not self._stop.wait(1.0):
            now = time.time()
            try:
                if psutil:
                    cpu = psutil.cpu_percent(interval=None)
                    memory = psutil.virtual_memory().percent
                    uptime = now - psutil.boot_time()
                    counters = psutil.net_io_counters(pernic=True)
                    addresses = psutil.net_if_addrs()
                    stats = psutil.net_if_stats()
                else:
                    cpu = memory = 0.0
                    uptime = float(open("/proc/uptime", encoding="utf-8").read().split()[0])
                    counters, addresses, stats = {}, {}, {}
                thermal_path = "/sys/class/thermal/thermal_zone0/temp"
                temperature = float(open(thermal_path, encoding="utf-8").read()) / 1000.0
                network = {}
                for name in ("wlan0", "eth0"):
                    counter = counters.get(name)
                    previous = self._last_net.get(name)
                    rx = counter.bytes_recv if counter else 0
                    tx = counter.bytes_sent if counter else 0
                    elapsed = max(.001, now - previous[0]) if previous else 1.0
                    rx_rate = max(0.0, (rx - previous[1]) / elapsed) if previous else 0.0
                    tx_rate = max(0.0, (tx - previous[2]) / elapsed) if previous else 0.0
                    self._last_net[name] = (now, rx, tx)
                    ipv4 = "—"
                    for address in addresses.get(name, ()):
                        if getattr(address, "family", None) == socket.AF_INET:
                            ipv4 = address.address
                            break
                    link = stats.get(name)
                    network[name] = {
                        "up": bool(link and link.isup), "speed_mbps": int(link.speed) if link else 0,
                        "ipv4": ipv4, "rx_rate": rx_rate, "tx_rate": tx_rate,
                        "rx_total": rx, "tx_total": tx,
                    }
                wireless = self._wireless_details()
                network.setdefault("wlan0", {}).update(wireless)
                with self._lock:
                    self._data["system"] = {"cpu": cpu, "memory": memory,
                                             "temperature_c": temperature, "uptime": uptime}
                    self._data["network"] = network
                    self._data["updated"] = now
            except Exception as exc:
                with self._lock:
                    self._data["system_error"] = str(exc)

    @staticmethod
    def _wireless_details():
        details = {"signal_dbm": None, "ssid": "—"}
        try:
            for line in open("/proc/net/wireless", encoding="utf-8"):
                if "wlan0:" in line:
                    fields = line.replace(".", "").split()
                    details["signal_dbm"] = float(fields[3])
                    break
        except (OSError, ValueError, IndexError):
            pass
        try:
            result = subprocess.run(["iwgetid", "wlan0", "--raw"], capture_output=True,
                                    text=True, timeout=1, check=False)
            if result.stdout.strip():
                details["ssid"] = result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
        return details

    def _weather_loop(self):
        while not self._stop.is_set():
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("", WEATHERFLOW_PORT))
                sock.settimeout(2)
                with self._lock:
                    self._data["weatherflow"]["error"] = "WAITING"
                while not self._stop.is_set():
                    try:
                        packet = json.loads(sock.recvfrom(65535)[0].decode("utf-8"))
                        self._handle_weather(packet)
                    except socket.timeout:
                        continue
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
            except OSError as exc:
                with self._lock:
                    self._data["weatherflow"].update(connected=False, error=str(exc))
                self._stop.wait(5)
            finally:
                if sock:
                    sock.close()

    def _merge_water(self, source, summary, now=None):
        now = now or time.time()
        with self._lock:
            previous = self._data["water"].get(source, {})
            if not summary.get("raw_ok") and previous.get("raw_ok"):
                previous.update(error=summary.get("error", "DATA LINK FAULT"),
                                link_updated=summary.get("updated", now))
            else:
                summary["link_updated"] = now
                self._data["water"][source] = summary

    def _usgs_loop(self):
        """Poll primary USGS feeds directly."""
        while not self._stop.is_set():
            failed = False
            for source, (topic, url) in USGS_URLS.items():
                try:
                    request = urllib.request.Request(url, headers={"User-Agent": "home-monitor/1.0"})
                    with urllib.request.urlopen(request, timeout=15) as response:
                        payload = json.load(response)
                    summary = _water_summary(topic, payload, time.time())
                    summary["source"] = "USGS DIRECT"
                except Exception:
                    failed = True
                    summary = {"raw_ok": False, "error": "USGS LINK FAULT",
                               "updated": time.time(), "source": "USGS DIRECT"}
                self._merge_water(source, summary)
            self._stop.wait(30 if failed else USGS_REFRESH_SECONDS)

    def _handle_weather(self, packet):
        kind, now = packet.get("type"), time.time()
        values = {}
        if kind == "rapid_wind" and len(packet.get("ob", ())) >= 3:
            ob = packet["ob"]
            values = {"wind_mps": ob[1], "wind_direction": ob[2], "observed": ob[0]}
        elif kind == "obs_st" and packet.get("obs"):
            ob = packet["obs"][0]
            if len(ob) >= 18:
                observed = float(ob[0])
                strike_count = max(0, int(ob[15] or 0))
                strike_distance = float(ob[14]) if strike_count and ob[14] is not None else None
                self._lightning_observations[observed] = (strike_count, strike_distance)
                cutoff = observed - 300
                while self._lightning_observations:
                    timestamp = next(iter(self._lightning_observations))
                    if timestamp >= cutoff:
                        break
                    self._lightning_observations.popitem(last=False)
                lightning_5m = sum(item[0] for item in self._lightning_observations.values())
                recent_distances = [item[1] for item in self._lightning_observations.values()
                                    if item[0] and item[1] is not None]
                values = {
                    "observed": ob[0], "temperature_observed": ob[0], "wind_lull_mps": ob[1], "wind_mps": ob[2],
                    "wind_gust_mps": ob[3], "wind_direction": ob[4], "pressure_mb": ob[6],
                    "temperature_c": ob[7], "humidity": ob[8], "illuminance": ob[9],
                    "uv": ob[10], "solar_wm2": ob[11], "rain_mm": ob[12],
                    "rain_rate_mmh": float(ob[12] or 0) * 60 / max(1, float(ob[17] or 1)),
                    "precip_type": ob[13], "lightning_km": ob[14],
                    "lightning_count": strike_count, "lightning_5m": lightning_5m,
                    "lightning_5m_km": (sum(recent_distances) / len(recent_distances)
                                         if recent_distances else None),
                    "battery_v": ob[16], "station_serial": packet.get("serial_number"),
                    "hub_serial": packet.get("hub_sn"),
                }
                if strike_distance is not None and strike_distance <= 0.804672:
                    values.update(last_close_lightning=observed,
                                  last_close_lightning_km=strike_distance)
                if len(ob) > 18:
                    values["daily_rain_mm"] = ob[18]
        elif kind == "evt_strike" and len(packet.get("evt", ())) >= 2:
            values = {"last_lightning": packet["evt"][0],
                      "last_lightning_km": packet["evt"][1]}
            if float(packet["evt"][1]) <= 0.804672:
                values.update(last_close_lightning=packet["evt"][0],
                              last_close_lightning_km=packet["evt"][1])
        elif kind == "evt_precip":
            values = {"precip_active": True, "last_precip": packet.get("evt", [now])[0]}
        if values:
            with self._lock:
                self._data["weather"].update(values)
                self._data["weatherflow"].update(connected=True, updated=now, error="")
