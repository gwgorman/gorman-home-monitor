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

 def test_group_members_use_current_readings_and_unknown_is_not_off(self):
  source={'house':{'data':{'items':[{'name':'Art','switch':'on','battery':80}]}}}
  config={'excluded':['buffet 2'],'group_entries':[{'name':'Office','members':['Art','Missing','Buffet 2'],'unresolved':1}]}
  result=apply_device_config(source,config,{})['device_groups'][0]
  self.assertEqual([m['name'] for m in result['members']],['Art','Missing'])
  self.assertEqual(result['members'][0]['switch'],'on');self.assertEqual(result['members'][0]['battery'],80)
  self.assertNotIn('switch',result['members'][1]);self.assertEqual(result['unresolved'],1)

 def test_source_name_alias_connects_group_to_same_live_device(self):
  source={'house':{'data':{'items':[{'name':'Small lamp','switch':'off'}]}}}
  config={'device_names':{'small lamp':'Fence 2'},'group_entries':[{'name':'Fence','members':['Fence 2']}]}
  result=apply_device_config(source,config,{})
  self.assertEqual(result['house']['data']['items'][0]['name'],'Fence 2')
  self.assertEqual(result['device_groups'][0]['members'][0]['switch'],'off')
  self.assertEqual(source['house']['data']['items'][0]['name'],'Small lamp')
