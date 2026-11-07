import json,tempfile,unittest
from pathlib import Path
from alexa_status import read_alexa_status
from meross_status import apply_device_config
class AlexaStatusTests(unittest.TestCase):
 def test_stale_file_never_keeps_on(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'status.json'
   payload={'state':'live','updated':1000,'data':{'items':[{'name':'Back landscape lights','switch':'on','switch_at':1000}]}}
   path.write_text(json.dumps(payload))
   self.assertEqual(read_alexa_status(path,1001)[0]['switch'],'on')
   self.assertEqual(read_alexa_status(path,1601),[])
 def test_group_uses_supplemental_channel_but_direct_data_wins(self):
  source={'house':{'data':{'items':[{'name':'Direct','switch':'off'}]}}}
  config={'group_entries':[{'name':'Yard','members':['back landscape lights ','Direct']}]}
  rows=[{'name':'Back landscape lights','switch':'on'},{'name':'Direct','switch':'on'}]
  result=apply_device_config(source,config,{},rows)
  self.assertEqual([x['switch'] for x in result['device_groups'][0]['members']],['on','off'])

 def test_individual_field_ages_and_failed_cycle_do_not_look_current(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'status.json'
   payload={'state':'live','updated':1000000,'data':{'items':[{'name':'Sensor','fetched':1000000,'temperature':22,'temperature_at':999999,'switch':'on','switch_at':1}]}}
   path.write_text(json.dumps(payload))
   row=read_alexa_status(path,1000001)[0]
   self.assertEqual(row['temperature'],22);self.assertNotIn('switch',row)
   payload['state']='unavailable';path.write_text(json.dumps(payload));self.assertEqual(read_alexa_status(path,1000001),[])
 def test_yolink_and_meross_sources_are_not_duplicated(self):
  source={'sensors':{'items':[{'name':'Freezer','temperature_f':2}]},'house':{'data':{'items':[]}}}
  config={'excluded':['retired'],'device_names':{'small lamp':'Fence 2'}}
  alexa=[{'name':'Freezer','temperature':2},{'name':'L garage door','contact':'open'},{'name':'Small lamp','switch':'on'},{'name':'Retired','switch':'on'},{'name':'Fault','error':'unreachable'}]
  result=apply_device_config(source,config,{'data':{'items':[{'name':'L garage door','contact':'closed'}]}},alexa)
  self.assertEqual([x['name'] for x in result['house']['data']['items']],['Fence 2','L garage door'])
