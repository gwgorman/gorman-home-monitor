import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('pool_adapter',Path(__file__).resolve().parents[1]/'integrations'/'aqualink.py')
adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
class Switch:
 def __init__(self,label,state):self.label,self.state=label,state
 def turn_on(self):raise AssertionError('No controls permitted')
class Thermostat(Switch):pass
class PoolStatusTests(unittest.TestCase):
 def test_status_mapping_excludes_targets_and_preserves_unknown(self):
  devices={'pump':Switch('Pool pump','1'),'aux':Switch('Spa light','0'),'heater':Switch('Pool heater','2'),'unknown':Switch('Aux 7','99'),'target':Thermostat('Set point','85')}
  rows=adapter.equipment_readings(devices,Switch,Thermostat,123)
  self.assertEqual({r['id']:r['state'] for r in rows},{'pump':'on','aux':'off','heater':'standby','unknown':'unknown'})
  self.assertTrue(all(r['reported_at']==123 for r in rows))
