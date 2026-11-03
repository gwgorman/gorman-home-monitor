"""Read-only, display-safe whole-house SmartThings inventory."""
import concurrent.futures
import datetime as dt
import math
import time
import urllib.parse

FIELDS=[('temperatureMeasurement','temperature','temperature'),('relativeHumidityMeasurement','humidity','humidity'),('contactSensor','contact','contact'),('waterSensor','water','water'),('switch','switch','switch'),('switchLevel','level','level'),('battery','battery','battery'),('powerMeter','power','power'),('energyMeter','energy','energy'),('motionSensor','motion','motion'),('lock','lock','lock'),('presenceSensor','presence','presence')]

def summarize(device,status):
    result=[]
    for component,capabilities in status.get('components',{}).items():
        row={'name':device.get('label') or device.get('name') or 'Device','component':component,'fetched':time.time(),'updated':0}
        if component not in ('main','cooler'):row['name']+=' · '+component
        for capability,attribute,key in FIELDS:
            item=capabilities.get(capability,{}).get(attribute,{})
            value=item.get('value')
            if value is None or isinstance(value,(dict,list,bool)):continue
            if isinstance(value,float) and not math.isfinite(value):continue
            row[key]=value[:100] if isinstance(value,str) else value
            row[key+'_unit']=item.get('unit','')
            if key=='battery' and (item.get('unit')!='%' or not isinstance(value,(float,int)) or not 0<=value<=100):
                row.pop(key,None);continue
            try:
                stamp=dt.datetime.fromisoformat(item.get('timestamp','').replace('Z','+00:00')).timestamp()
                row[key+'_at']=stamp;row['updated']=max(row['updated'],stamp)
            except (ValueError,TypeError):pass
        if len(row)>5:result.append(row)
    return result

def inventory(smartthings):
    headers={'Authorization':'Bearer '+smartthings.token()}
    devices=[];address='https://api.smartthings.com/v1/devices'
    while address:
        payload=smartthings.fetch(address,headers=headers);devices.extend(payload.get('items',[]))
        address=payload.get('_links',{}).get('next',{}).get('href')
        if address and not address.startswith('https://api.smartthings.com/'):raise ValueError('Unexpected device page')
    def get(device):
        try:
            status=smartthings.fetch('https://api.smartthings.com/v1/devices/'+urllib.parse.quote(device['deviceId'],safe='')+'/status',headers=headers)
            return summarize(device,status),False
        except Exception:
            return [{'name':device.get('label') or device.get('name') or 'Device','error':'Status unavailable','updated':0}],True
    rows=[];failed=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for result,error in pool.map(get,devices):rows.extend(result);failed+=int(error)
    return {'items':rows,'devices':len(devices),'failed':failed,'observed':time.time()}
