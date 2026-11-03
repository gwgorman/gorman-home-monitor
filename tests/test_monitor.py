import os,sys,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
scratch=tempfile.TemporaryDirectory()
os.environ['HOME_MONITOR_CONFIG']=scratch.name
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class MonitorTests(unittest.TestCase):
    def test_expired_alerts_removed_and_radar_bytes_not_exposed(self):
        m=server.Monitor.__new__(server.Monitor);m.lock=threading.RLock()
        m.sources={'alerts':{'state':'live','data':[{'expires':time.time()-2},{'expires':time.time()+60}]}}
        m.station=SimpleNamespace(snapshot=lambda:{})
        m.space=SimpleNamespace(snapshot=lambda:{})
        m.flights=SimpleNamespace(snapshot=lambda:{'weather':{'updated':42,'tiles':{(11,12):b'PNG DATA'}}})
        snapshot=m.snapshot()
        self.assertEqual(len(snapshot['alerts']['data']),1)
        self.assertEqual(snapshot['flights']['weather']['tiles'][0]['url'],'/radar/11/12.png?v=42')
        import json
        json.dumps(snapshot)
        self.assertEqual(len(m.sources['alerts']['data']),2)

    def test_private_network_restriction(self):
        from unittest.mock import Mock
        h=server.Handler.__new__(server.Handler);h.client_address=('8.8.8.8',100);h.reply=Mock()
        h.do_GET();self.assertEqual(h.reply.call_args.args[1],403)

    def test_unapproved_host_rejected_even_from_lan(self):
        from unittest.mock import Mock
        import ipaddress
        server.LAN=ipaddress.ip_network('198.51.100.0/24')
        h=server.Handler.__new__(server.Handler);h.client_address=('198.51.100.20',100);h.headers={'Host':'evil.example:8780'};h.reply=Mock()
        h.do_GET();self.assertEqual(h.reply.call_args.args[1],403)

    def test_station_starts_only_local_weather_system_and_water_workers(self):
        from unittest.mock import patch
        import office_telemetry
        collector=office_telemetry.TelemetryService()
        with patch.object(office_telemetry.threading,'Thread') as thread:
            collector.start()
        targets={call.kwargs['target'].__name__ for call in thread.call_args_list}
        self.assertEqual(targets,{'_system_loop','_weather_loop','_usgs_loop'})

    def test_rapid_wind_does_not_refresh_temperature_age(self):
        import office_telemetry
        c=office_telemetry.TelemetryService()
        observation=[100,0,1,2,90,3,1000,20,50,100,1,50,0,0,0,0,2.8,1]
        c._handle_weather({'type':'obs_st','obs':[observation]})
        c._handle_weather({'type':'rapid_wind','ob':[200,5,180]})
        w=c.snapshot()['weather']
        self.assertEqual(w['temperature_observed'],100)
        self.assertEqual(w['wind_mps'],5)

    def test_inventory_keeps_report_ages_and_rejects_invalid_battery(self):
        import importlib.util
        path=Path(__file__).resolve().parents[1]/'integrations'/'house_inventory.py'
        spec=importlib.util.spec_from_file_location('house_inventory',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        payload={'components':{'main':{'battery':{'battery':{'value':0,'unit':'%','timestamp':'2026-01-01T00:00:00Z'}},'temperatureMeasurement':{'temperature':{'value':float('nan'),'unit':'F'}}}}}
        rows=module.summarize({'label':'Test sensor'},payload)
        self.assertEqual(rows[0]['battery'],0)
        self.assertGreater(rows[0]['battery_at'],0)
        self.assertNotIn('temperature',rows[0])
        payload['components']['main']['battery']['battery']['unit']='V'
        self.assertFalse(any('battery' in r for r in module.summarize({'label':'Test'},payload)))
