"""Read-only Meross garage-door collector; credentials remain outside the checkout."""
import asyncio
import json
import threading
import time

class MerossStatus:
    def __init__(self, credentials):
        self.credentials=credentials
        self.lock=threading.Lock()
        self.state={'state':'unconfigured','data':{'items':[]}}
    def start(self):
        if self.credentials.exists():
            threading.Thread(target=self.run,daemon=True).start()
    def snapshot(self):
        with self.lock:
            result={**self.state,'data':{'items':[dict(x) for x in self.state['data']['items']]}}
        for item in result['data']['items']:
            if time.time()-item.get('fetched',0)>180:
                item.pop('contact',None);item['error']='Meross reading stale'
        return result
    def run(self):
        while True:
            try:asyncio.run(self.collect())
            except Exception as exc:
                with self.lock:self.state={**self.state,'state':'unavailable','error':type(exc).__name__}
            time.sleep(60)
    async def collect(self):
        from meross_iot.http_api import MerossHttpClient
        from meross_iot.model.credentials import MerossCloudCreds
        from meross_iot.manager import MerossManager
        from meross_iot.controller.mixins.garage import GarageOpenerMixin
        client=await MerossHttpClient.async_from_cloud_creds(MerossCloudCreds.from_json(self.credentials.read_text()))
        manager=MerossManager(http_client=client)
        try:
            await manager.async_init();await manager.async_device_discovery()
            devices=manager.find_devices(device_class=GarageOpenerMixin)
            while True:
                items=[]
                for device in devices:
                    name=device.name.strip()
                    if name not in ('Big Garage Door','Small Garage Door'):continue
                    side=0 if name=='Big Garage Door' else 1
                    item={'name':'L garage door' if side==0 else 'R garage door','source':'Meross','display_source':'Meross','garage_door_order':side}
                    try:
                        await asyncio.wait_for(device.async_update(),25)
                        opened=device.get_is_open()
                        if opened is not None:item['contact']='open' if opened else 'closed'
                        else:item['error']='Door state unknown'
                        item['fetched']=item['updated']=time.time()
                    except Exception as exc:item['error']=type(exc).__name__
                    items.append(item)
                with self.lock:self.state={'state':'live','updated':time.time(),'data':{'items':items}}
                await asyncio.sleep(60)
        finally:manager.close()

def apply_device_config(kitchen, config, meross):
    """Annotate live source items, replacing duplicate garage contacts only."""
    normal=lambda text:' '.join(text.strip().lower().replace('’',"'").split())
    result=dict(kitchen);house=dict(result.get('house') or {});data=dict(house.get('data') or {})
    excluded=set(config.get('excluded',[]));groups=config.get('groups',{})
    doors=meross.get('data',{}).get('items',[])
    door_names={normal(d['name']) for d in doors}
    items=[]
    for original in data.get('items',[]):
        key=normal(original.get('name',''))
        if key in excluded or key in door_names:continue
        item=dict(original)
        if key in groups:item['tile_group']=groups[key]
        if key in config.get('notes',{}):item['device_note']=config['notes'][key]
        items.append(item)
    items.extend(doors);data['items']=items;house['data']=data;result['house']=house
    lookup={}
    for item in items:
        key=normal(item.get('name',''))
        if key not in lookup or item.get('component')=='main':lookup[key]=item
    for item in doors:
        lookup['big garage door' if item.get('garage_door_order')==0 else 'small garage door']=item
    for item in (result.get('sensors') or {}).get('items',[]):
        lookup.setdefault(normal(item.get('name','')),item)
    entries=[]
    for group in config.get('group_entries',[]):
        members=[]
        for name in group.get('members',[]):
            if normal(name) in excluded or 'iphone' in normal(name):continue
            reading=lookup.get(normal(name),{})
            members.append({**reading,'name':name,'display_label':config.get('member_labels',{}).get(normal(name),name)})
        entries.append({'name':group['name'],'members':members,'unresolved':group.get('unresolved',0)})
    result['device_groups']=entries
    if result.get('aqualink'):
        feed=dict(result['aqualink']);pool=dict(feed.get('data') or {})
        hidden=set(config.get('pool_hidden_equipment',[]))
        pool['equipment']=[d for d in pool.get('equipment',[]) if d.get('id') not in hidden]
        feed['data']=pool;result['aqualink']=feed
    return result
