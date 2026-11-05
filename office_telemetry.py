"""Read-only system, local WeatherFlow UDP, and USGS collectors."""

from __future__ import annotations

import collections, copy, datetime as dt, json, math, os, socket, subprocess, threading, time, urllib.request

try:
    import psutil
except ImportError:
    psutil = None

from water_history import lake_history, release_report

WEATHERFLOW_PORT = 50222
USGS_REFRESH_SECONDS = 900

USGS_URLS = {
    "richland": ("RichlandChambers", "https://waterservices.usgs.gov/nwis/iv/?format=json&sites=08064550&siteStatus=all&period=P7D"),
    "lake": ("LewisvilleLake", "https://waterservices.usgs.gov/nwis/iv/"
             "?format=json&sites=08052800&siteStatus=all&period=P7D"),
    "trinity": ("TrinityRiver", "https://waterservices.usgs.gov/nwis/iv/"
                "?format=json&sites=08053000&parameterCd=00060%2C00065&siteStatus=all&period=P7D"),
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

    def __init__(self, history_path=None):
        self._history_path = os.fspath(history_path) if history_path else None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._last_net = {}
        self._lightning_observations = collections.OrderedDict()
        self._data = {
            "updated": 0.0,
            "system": {},
            "network": {},
            "weather": {},
            "weather_history": [],
            "water": {"lake": {}, "trinity": {}},
            "weatherflow": {"connected": False, "updated": 0.0, "error": "WAITING"},
        }
        self._threads = []
        if self._history_path:
            try:
                with open(self._history_path, encoding="utf-8") as stream:
                    self._data["weather_history"] = self._clean_history(json.load(stream))
            except (OSError, ValueError, TypeError):
                pass

    @staticmethod
    def _clean_history(rows):
        if not isinstance(rows, list):
            return []
        now = time.time()
        unique = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            stamp, pressure = row.get("time"), row.get("pressure_mb")
            if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in (stamp, pressure)):
                continue
            if now - 86400 <= stamp <= now + 60 and 0 < pressure < 2000:
                unique[stamp] = {"time": stamp, "pressure_mb": pressure}
        return [unique[t] for t in sorted(unique)][-2880:]

    def _record_pressure(self, stamp, pressure):
        with self._lock:
            rows = self._clean_history(self._data["weather_history"] + [{"time": stamp, "pressure_mb": pressure}])
            self._data["weather_history"] = rows
        if not self._history_path:
            return
        temporary = self._history_path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self._history_path), exist_ok=True, mode=0o700)
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(rows, stream, allow_nan=False)
            os.replace(temporary, self._history_path)
        except OSError:
            with self._lock:
                self._data["weather_history_error"] = "History cache unavailable"

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
                    summary = lake_history(payload, {'lake':'08052800','trinity':'08053000','richland':'08064550'}[source])
                    summary["source"] = "USGS DIRECT"
                except Exception:
                    failed = True
                    summary = {"raw_ok": False, "error": "USGS LINK FAULT",
                               "updated": time.time(), "source": "USGS DIRECT"}
                self._merge_water(source, summary)
            try:
                request = urllib.request.Request('https://www.swf-wc.usace.army.mil/reports/fish2.htm',headers={'User-Agent':'home-monitor/1.0'})
                with urllib.request.urlopen(request,timeout=15) as response:releases=release_report(response.read().decode('utf-8',errors='replace'))
                with self._lock:self._data['water']['releases']={'items':releases,'fetched':time.time(),'error':''}
            except Exception:
                with self._lock:
                    current=self._data['water'].setdefault('releases',{'items':{}})
                    current['error']='USACE report unavailable'
            self._stop.wait(30 if failed else USGS_REFRESH_SECONDS)

    @staticmethod
    def _weather_timestamp(value, now):
        try:
            timestamp=float(value)
        except (ValueError,TypeError):
            return None
        if isinstance(value,bool) or not math.isfinite(timestamp) or not 946684800 <= timestamp <= now+300:
            return None
        return timestamp

    def _handle_weather(self, packet):
        kind, now = packet.get("type"), time.time()
        values = {}
        if kind == "rapid_wind" and len(packet.get("ob", ())) >= 3:
            ob = packet["ob"]
            values = {"wind_mps": ob[1], "wind_direction": ob[2], "observed": ob[0]}
        elif kind == "obs_st" and packet.get("obs"):
            ob = packet["obs"][0]
            if len(ob) >= 18:
                observed = self._weather_timestamp(ob[0],now)
                if observed is None:
                    with self._lock:self._data['weatherflow']['invalid_observation_timestamp']={'timestamp':ob[0],'received_at':now}
                    return
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
                if strike_count and self._weather_timestamp(observed,now) is not None:
                    with self._lock:previous=self._data['weather'].get('last_lightning',0)
                    if observed >= previous or self._weather_timestamp(previous,now) is None:
                        values.update(last_lightning=observed,last_lightning_time_source='observation')
                if strike_distance is not None and strike_distance <= 0.804672:
                    values.update(last_close_lightning=observed,
                                  last_close_lightning_km=strike_distance)
                if len(ob) > 18:
                    values["daily_rain_mm"] = ob[18]
        elif kind == "evt_strike" and len(packet.get("evt", ())) >= 2:
            timestamp=self._weather_timestamp(packet['evt'][0],now)
            if timestamp is None:
                with self._lock:self._data['weatherflow']['rejected_lightning_event']={'timestamp':packet['evt'][0],'distance_km':packet['evt'][1],'serial_number':packet.get('serial_number'),'received_at':now}
                return
            values = {"last_lightning": timestamp,
                      "last_lightning_received_at": now,
                      "last_lightning_time_source": 'detected',
                      "last_lightning_km": packet["evt"][1]}
            if float(packet["evt"][1]) <= 0.804672:
                values.update(last_close_lightning=timestamp,
                              last_close_lightning_km=packet["evt"][1])
        elif kind == "evt_precip":
            values = {"precip_active": True, "last_precip": packet.get("evt", [now])[0]}
        if values:
            with self._lock:
                self._data["weather"].update(values)
                self._data["weatherflow"].update(connected=True, updated=now, error="")
            if kind == "obs_st" and "pressure_mb" in values:
                self._record_pressure(values["temperature_observed"], values["pressure_mb"])
