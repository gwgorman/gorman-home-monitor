import datetime as dt
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from water_history import lake_history,release_report

class WaterHistoryTests(unittest.TestCase):
    def series(self,code,values,site='08052800'):
        return {'sourceInfo':{'siteCode':[{'value':site}]},'variable':{'variableCode':[{'value':code}],'noDataValue':-999999},'values':[{'value':[{'value':str(value),'dateTime':stamp} for stamp,value in values]}]}
    def test_history_filters_missing_values_and_keeps_station_and_parameter_separate(self):
        p={'value':{'timeSeries':[self.series('62614',[('2026-11-01T00:00:00-06:00',518),('2026-11-02T00:00:00-06:00',518.2),('2026-11-02T00:15:00-06:00',-999999)]),self.series('00035',[('2026-11-02T00:00:00-06:00',10)]),self.series('62614',[('2026-11-02T00:00:00-06:00',312)],'08064550')]}}
        s=lake_history(p,'08052800')
        self.assertEqual(s['elevation_ft'],518.2);self.assertEqual(s['wind_mph'],10)
        self.assertAlmostEqual(s['change_24h_ft'],.2)
        self.assertEqual(len(s['history']['elevation_ft']),2)
        self.assertNotIn('change_7d_ft',s);self.assertNotIn('gates',s)
    def test_missing_history_never_becomes_zero(self):
        s=lake_history({'value':{'timeSeries':[]}},'08052800')
        self.assertFalse(s['raw_ok']);self.assertNotIn('elevation_ft',s)
    def test_release_report_retains_report_time_not_fetch_time(self):
        h='<p>Data as of 03 Nov 2026 @ 1100 CST</p><table><tr><td>Lewisville Lake</td><td>517.98</td><td>522.0</td><td>-4.02</td><td>0.23</td><td>221</td><td>532.0</td></tr></table>'
        s=release_report(h)['lake'];self.assertEqual(s['release_cfs'],221)
        self.assertEqual(dt.datetime.fromtimestamp(s['updated'],dt.timezone.utc).hour,17)
        self.assertNotIn('gate_a',s)
    def test_unrecognized_corps_report_is_an_error(self):
        with self.assertRaises(ValueError):release_report('<html>Unavailable</html>')
