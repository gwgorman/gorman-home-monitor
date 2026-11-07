"""Consume sanitized Alexa reports; expire stopped collectors and old fields."""
import json
import time

FIELDS=('switch','level','temperature','humidity','motion','contact','lock','battery','playbackStatus','volume','mute','color','colorTemperature','thermostatMode','targetTemperature','armState','water')

def read_alexa_snapshot(path, now=None):
    now=time.time() if now is None else now
    try:
        snapshot=json.loads(path.read_text())
        if snapshot.get('state')!='live' or not 0<=now-snapshot.get('updated',0)<600:
            return {}
        items=[]
        for original in snapshot.get('data',{}).get('items',[]):
            item=dict(original)
            if not 0<=now-item.get('fetched',snapshot['updated'])<600:
                continue
            for field in FIELDS:
                if field in item and not -300<=now-item.get(field+'_at',0)<=7*86400:
                    item.pop(field,None);item.pop(field+'_at',None);item.pop(field+'_unit',None)
            if not any(field in item for field in FIELDS):item['error']='No usable recent Alexa reading'
            items.append(item)
        return {**snapshot,'data':{'items':items}}
    except (OSError,ValueError,TypeError,AttributeError):
        return {}

def read_alexa_status(path, now=None):
    return read_alexa_snapshot(path,now).get('data',{}).get('items',[])
