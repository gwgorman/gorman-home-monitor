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
   self.assertEqual(read_alexa_status(path,1301),[])
 def test_group_uses_supplemental_channel_but_direct_data_wins(self):
  source={'house':{'data':{'items':[{'name':'Direct','switch':'off'}]}}}
  config={'group_entries':[{'name':'Yard','members':['back landscape lights ','Direct']}]}
  rows=[{'name':'Back landscape lights','switch':'on'},{'name':'Direct','switch':'on'}]
  result=apply_device_config(source,config,{},rows)
  self.assertEqual([x['switch'] for x in result['device_groups'][0]['members']],['on','off'])
