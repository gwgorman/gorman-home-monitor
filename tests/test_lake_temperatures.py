import json
import unittest
from unittest.mock import patch
from lake_temperatures import parse_temperature, SOURCES
from office_telemetry import TelemetryService

class LakeTemperatureTests(unittest.TestCase):
    def page(self, lake='571', value='63°F', date='2026-11-06T16:42:34Z'):
        item = {'@context': 'https://schema.org', 'additionalProperty': [
            {'propertyID': 'water-temperature', 'value': value, 'dateModified': date,
             'mainEntityOfPage': 'https://lakemonster.com/lake/Texas/Reservoir-' + lake}]}
        return '<script>self.__next_f.push(' + json.dumps([1, '49:T123,' + json.dumps(item)]) + ')</script>'
    def test_published_is_not_observation(self):
        result = parse_temperature(self.page(), SOURCES['richland'], now=1794000000)
        self.assertEqual(result['temperature_f'], 63)
        self.assertIsNone(result['observed_at'])
        self.assertTrue(result['estimated'])
        self.assertEqual(result['published_at'], 1793983354)
    def test_wrong_lake_and_bad_values_rejected(self):
        for page in [self.page(lake='211'), self.page(value='999°F'), '<script>waterTemp:74</script>']:
            with self.assertRaises(ValueError): parse_temperature(page, SOURCES['richland'])
    def test_unknown_date_remains_unknown(self):
        self.assertIsNone(parse_temperature(self.page(date=''), SOURCES['richland'])['published_at'])
    def test_failure_preserves_last_good_and_rate_limits(self):
        service = TelemetryService()
        service._data['water']['temperatures'] = {'richland': {'temperature_f': 63, 'fetched_at': 1}}
        with patch('office_telemetry.fetch_temperature', side_effect=ValueError) as fetch:
            service._refresh_lake_temperatures()
            service._refresh_lake_temperatures()
        self.assertEqual(fetch.call_count, 2)  # one attempt per lake
        reading = service._data['water']['temperatures']['richland']
        self.assertEqual(reading['temperature_f'], 63)
        self.assertEqual(reading['fetched_at'], 1)
        self.assertTrue(reading['error'])
