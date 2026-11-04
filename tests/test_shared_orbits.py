import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from satellite_telemetry import SatelliteTelemetryService, REFRESH_SECONDS
from shared_orbits import SharedSatelliteTelemetryService, catalog_condition

class SharedOrbitTests(unittest.TestCase):
    def test_cooldown_survives_restart_and_retry_after_extends_it(self):
        with tempfile.TemporaryDirectory() as directory:
            first = SatelliteTelemetryService(directory)
            deadline = first._defer_download('starlink', 10000)
            second = SatelliteTelemetryService(directory)
            self.assertEqual(second._deadline('starlink'), deadline)
            error = HTTPError('https://example.invalid',429,'limit',{'Retry-After':'18000'},None)
            self.assertEqual(second._retry_deadline('starlink',error,1000),19000)
            self.assertEqual(first._deadline('starlink'),19000)
            forbidden = HTTPError('https://example.invalid',403,'limit',{},None)
            self.assertEqual(first._retry_deadline('catalog', forbidden,1000),1000+REFRESH_SECONDS)

    def test_client_keeps_producer_timestamps_and_cannot_fetch_catalogs(self):
        with tempfile.TemporaryDirectory() as directory:
            client = SharedSatelliteTelemetryService(directory,'http://hub.local:8780/api/space')
            stamp = time.time()-10
            payload = {'source':'household-orbit-hub','updated':stamp,'catalog_updated':stamp-100,
                       'catalog_count':2,'connected':True,'overhead':[{'name':'ISS'}]}
            class Response:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def read(self,*args):return json.dumps(payload).encode()
            with patch('urllib.request.urlopen',return_value=Response()) as fetch:
                client._poll()
                for _ in range(5):self.assertEqual(client.snapshot()['updated'],stamp)
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(fetch.call_args.args[0].full_url,client.url)
            restarted = SharedSatelliteTelemetryService(directory,client.url)
            self.assertFalse(restarted.snapshot()['connected'])
            self.assertEqual(restarted.snapshot()['overhead'],[])
            self.assertEqual(restarted.snapshot()['updated'],stamp)

    def test_frozen_producer_positions_are_not_presented_as_live(self):
        with tempfile.TemporaryDirectory() as directory:
            client = SharedSatelliteTelemetryService(directory,'http://hub.local:8780/api/space')
            client._accept({'source':'household-orbit-hub','updated':time.time()-120,
                            'connected':True,'catalog_count':2,'overhead':[{'name':'ISS'}]})
            self.assertEqual(catalog_condition(client.snapshot())[0],'fault')
            self.assertEqual(client.snapshot()['overhead'],[])

    def test_lan_endpoint_reads_snapshot_without_triggering_collector(self):
        import server
        from unittest.mock import Mock
        handler = server.Handler.__new__(server.Handler)
        handler.client_address = ('127.0.0.1',123)
        handler.headers = {'Host':next(iter(server.HOSTS))}
        handler.path = '/api/space'
        handler.reply = Mock()
        handler.server = Mock()
        handler.server.monitor.space.snapshot.return_value = {'source':'household-orbit-hub'}
        handler.do_GET()
        self.assertEqual(handler.reply.call_args.args[1],200)
        self.assertEqual(handler.server.monitor.space.method_calls,[unittest.mock.call.snapshot()])
