"""LAN-only orbital client; never downloads catalogs or ephemerides itself."""
import copy
import json
import os
from pathlib import Path
import threading
import time
import urllib.request
from urllib.parse import urlparse


def catalog_condition(data, now=None):
    now = time.time() if now is None else now
    stamp = float(data.get('catalog_updated') or 0)
    age = max(0, now - stamp) if stamp else float('inf')
    if not data.get('connected') or not data.get('catalog_count') or age >= 7*86400:
        return 'fault', age
    if data.get('error') or age >= 4*3600:
        return 'stale', age
    return 'nominal', age


class SharedSatelliteTelemetryService:
    def __init__(self, cache_dir=None, url=None):
        self.url = url or os.environ.get('HOME_ORBITS_URL', '')
        parsed = urlparse(self.url)
        if parsed.scheme != 'http' or not parsed.hostname or parsed.path != '/api/space':
            raise ValueError('Configure HOME_ORBITS_URL as http://your-orbit-hub:8780/api/space')
        self.cache_path = Path(cache_dir or Path.home()/'.cache'/'household-orbits')/'last-snapshot.json'
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._data = {'connected': False, 'error': 'ORBIT HUB STARTING', 'updated': 0,
                      'catalog_count': 0, 'overhead': [], 'upcoming': [],
                      'starlink_overhead': [], 'planets': [], 'stars': []}
        try:
            self._accept(json.loads(self.cache_path.read_text()))
        except (OSError, ValueError, TypeError):
            pass
        self._received = 0.0

    def _accept(self, data):
        if not isinstance(data, dict) or data.get('source') != 'household-orbit-hub':
            raise ValueError('Not a household orbit hub snapshot')
        if not isinstance(data.get('updated'), (int, float)):
            raise ValueError('Missing position timestamp')
        with self._lock:
            self._data = data
            self._received = time.time()

    def start(self):
        if self._thread:
            return
        self._thread = threading.Thread(target=self._loop, name='shared-orbits', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def snapshot(self):
        with self._lock:
            data = copy.deepcopy(self._data)
            stale = time.time() - self._received > 30 or time.time() - data.get('updated', 0) > 60
        if stale:
            data.update(error='ORBIT HUB UNAVAILABLE / STALE POSITIONS', connected=False,
                        starlink_error='ORBIT HUB UNAVAILABLE', celestial_error='ORBIT HUB UNAVAILABLE',
                        overhead=[], upcoming=[], starlink_overhead=[], planets=[], stars=[])
        return data

    def _poll(self):
        # Reads the shared snapshot only. No CelesTrak or Skyfield fallback.
        request = urllib.request.Request(self.url, headers={'Accept': 'application/json'})
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.loads(response.read(2_000_000))
        self._accept(data)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.cache_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, allow_nan=False))
        temporary.replace(self.cache_path)

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._poll()
            except (OSError, ValueError, TypeError):
                pass
            self._stop.wait(5)
