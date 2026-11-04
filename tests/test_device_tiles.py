import json,tempfile,time,unittest
from pathlib import Path
from meross_status import MerossStatus,apply_device_config
class DeviceTilesTests(unittest.TestCase):
 def test_mapping_exclusions_and_meross_override_preserve_batteries(self):
  source={'house':{'data':{'items':[{'name':'Art','switch':'on','battery':50},{'name':'Buffet 2','switch':'off'},{'name':'L garage door','contact':'open'}]}}}
  result=apply_device_config(source,{'excluded':['buffet 2'],'groups':{'art':'GREG’S OFFICE'}},{'data':{'items':[{'name':'L garage door','contact':'closed','source':'Meross'}]}})
  items=result['house']['data']['items'];self.assertEqual(len(items),2)
  self.assertEqual(items[0]['tile_group'],'GREG’S OFFICE');self.assertEqual(items[0]['battery'],50)
  self.assertEqual(items[1]['contact'],'closed');self.assertEqual(source['house']['data']['items'][2]['contact'],'open')
 def test_stale_meross_contact_is_unknown(self):
  m=MerossStatus(Path('/nonexistent'))
  m.state={'state':'unavailable','data':{'items':[{'name':'L garage door','contact':'closed','fetched':time.time()-181}]}}
  self.assertNotIn('contact',m.snapshot()['data']['items'][0])
  self.assertEqual(m.state['data']['items'][0]['contact'],'closed')
