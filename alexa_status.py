"""Consume the private read-only Alexa sidecar snapshot, expiring stale readings."""
import json
import time

def read_alexa_status(path, now=None):
    now=time.time() if now is None else now
    try:
        snapshot=json.loads(path.read_text())
        if snapshot.get('state')!='live' or not 0<=now-snapshot.get('updated',0)<300:
            return []
        items=[]
        for original in snapshot.get('data',{}).get('items',[]):
            item=dict(original)
            if item.get('switch') not in ('on','off') or not 0<=now-item.get('switch_at',0)<=7*86400:
                item.pop('switch',None)
                item['error']='No recent Alexa power reading'
            items.append(item)
        return items
    except (OSError,ValueError,TypeError,AttributeError):
        return []
