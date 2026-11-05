"""Read-only iAquaLink temperature and equipment adapter. No equipment control methods are exposed."""
import asyncio
import math
import threading
import time


def temperature(value, unit):
    if isinstance(value, bool) or str(unit).upper() not in ('F', 'C', '°F', '°C'):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    # Zero/negative and nonnumeric values are inactive/unknown water readings.
    if not math.isfinite(number) or number <= 0:
        return None
    return number * 9 / 5 + 32 if str(unit).upper() in ('C', '°C') else number


def equipment_readings(devices, switch_type, thermostat_type, observed):
    result=[]
    for key, device in devices.items():
        if not isinstance(device, switch_type) or isinstance(device, thermostat_type):
            continue
        raw=str(device.state).lower()
        state={'0':'off','1':'on','2':'standby','3':'enabled','true':'on','false':'off'}.get(raw,'unknown')
        result.append({'id':key,'name':device.label,'state':state,'reported_at':observed,'source':'iAquaLink'})
    return sorted(result,key=lambda d:d['name'].lower())


class AquaLink:
    def __init__(self, directory, load, save):
        self.path = directory / 'aqualink.json'
        self.load, self.save = load, save
        self.lock = threading.RLock()
        self.loop = None
        self.client = None
        self.identity = None
        self.stage = "starting"

    def configured(self):
        config = self.load(self.path, {})
        return bool(config.get('username') and config.get('password'))

    async def read(self, config, remember=False):
        from iaqualink.client import AqualinkClient
        identity = (config.get('username'), config.get('password'))
        if self.client is None or identity != self.identity or not self.client.logged:
            if self.client is not None:
                await self.client.close()
            self.client = AqualinkClient(*identity)
            self.identity = identity
            self.stage = "login"
            await self.client.login()
        if remember:
            self.save(self.path, config)
        self.stage = "system discovery"
        systems = await self.client.get_systems()
        if config.get('serial'):
            systems = {k: v for k, v in systems.items() if k == config['serial']}
        self.save(self.path.parent / 'aqualink-systems.json', {'supported': [{'name': s.name, 'type': s.data.get('device_type', '')} for s in systems.values()]})
        if not config.get('serial') and len(systems) != 1:
            named = {key: system for key, system in systems.items() if system.name.strip().casefold() == 'pool'}
            if len(named) == 1:
                systems = named
        if not systems:
            raw = (await self.client._send_systems_request()).json()
            self.save(self.path.parent / 'aqualink-systems.json', {'supported': [], 'discovered': [{'name': row.get('name', ''), 'type': row.get('device_type', '')} for row in raw if isinstance(row, dict)]})
            raise LookupError('No supported pool controller discovered')
        if len(systems) != 1:
            raise ValueError('More than one supported system; select its serial')
        system = next(iter(systems.values()))
        self.stage = "controller status"
        await system.update()
        devices = await system.get_devices()
        if getattr(system, 'online', None) is False:
            raise ConnectionError('Pool controller is offline')
        unit = getattr(system, 'temp_unit', '')
        now = time.time()
        result = {'observed': now, 'items': [], 'equipment': []}
        from iaqualink.device import AqualinkSwitch, AqualinkThermostat
        result['equipment'] = equipment_readings(devices, AqualinkSwitch, AqualinkThermostat, now)
        for key, name in [('pool_temp', 'Pool'), ('spa_temp', 'Spa')]:
            device = devices.get(key)
            value = temperature(device.state if device else None, unit)
            result['items'].append({'name': name, 'temperature_f': value,
                'reported_at': now if value is not None else 0, 'source': 'iAquaLink',
                'status': 'Current controller reading' if value is not None else 'Not currently reporting'})
        return result

    def reading(self):
        with self.lock:
            if not self.configured():
                return {'configured': False, 'items': []}
            if self.loop is None:
                self.loop = asyncio.new_event_loop()
            return self.loop.run_until_complete(asyncio.wait_for(self.read(self.load(self.path, {})), 45))

    def connect(self, config):
        with self.lock:
            if self.loop is None:
                self.loop = asyncio.new_event_loop()
            result = self.loop.run_until_complete(asyncio.wait_for(self.read(config, remember=True), 45))
            self.save(self.path, config)
            return result
