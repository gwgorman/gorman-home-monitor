#!/usr/bin/env python3
"""Independent read-only office monitor. No party controls or account credentials."""
import datetime as dt
import ipaddress
import json
import math
import os
import socket
from pathlib import Path
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from zoneinfo import ZoneInfo
import office_telemetry
from flight_telemetry import FlightTelemetryService
from satellite_telemetry import SatelliteTelemetryService

ROOT=Path(__file__).resolve().parent
CONFIG=Path(os.environ.get('HOME_MONITOR_CONFIG',str(Path.home()/'.config'/'home-monitor')))
CONFIG.mkdir(parents=True,exist_ok=True,mode=0o700)
TZ=ZoneInfo(os.environ.get('HOME_MONITOR_TIMEZONE','UTC'))
SITE_LAT=float(os.environ.get('HOME_MONITOR_LAT','0.0'))
SITE_LON=float(os.environ.get('HOME_MONITOR_LON','0.0'))
LOCATION=os.environ.get('HOME_MONITOR_LOCATION','Configured location')
KITCHEN_URL=os.environ.get('HOME_MONITOR_KITCHEN_URL','http://kitchen.local:8765/api/dashboard')
LAN=ipaddress.ip_network(os.environ.get('HOME_MONITOR_LAN','127.0.0.0/8'))
HOSTS=set(os.environ.get('HOME_MONITOR_HOSTS','localhost:8780,127.0.0.1:8780').lower().split(','))

def read(address):
    with urllib.request.urlopen(urllib.request.Request(address,headers={'User-Agent':'GormanHomeMonitor/1.0 (personal home display)','Accept':'application/geo+json,application/json'}),timeout=12) as response:
        return json.load(response)

class Monitor:
    def __init__(self):
        self.lock=threading.RLock();self.stop=threading.Event();self.sources={}
        self.station=office_telemetry.TelemetryService(history_path=CONFIG/'weather-history.json')
        self.flights=FlightTelemetryService();self.flights.set_weather_enabled(True)
        self.space=SatelliteTelemetryService(cache_dir=str(CONFIG/'space-cache'))
    def start(self):
        self.station.start();self.flights.start();self.space.start()
        for name,interval,job in [('kitchen',30,lambda:read(KITCHEN_URL)),('alerts',60,self.alerts),('forecast',600,self.forecast)]:
            threading.Thread(target=self.worker,args=(name,interval,job),daemon=True).start()
    def worker(self,name,interval,job):
        while not self.stop.is_set():
            delay=interval
            try:
                result=job()
                with self.lock:self.sources[name]={'state':'live','updated':time.time(),'data':result}
            except Exception as exc:
                with self.lock:self.sources[name]={**self.sources.get(name,{}),'state':'unavailable','error':type(exc).__name__}
                delay=min(interval,15)
            self.stop.wait(delay)
    def alerts(self):
        result=[]
        for entry in read(f'https://api.weather.gov/alerts/active?point={SITE_LAT},{SITE_LON}').get('features',[]):
            p=entry['properties'];expires=p.get('ends') or p.get('expires')
            end=dt.datetime.fromisoformat(expires.replace('Z','+00:00')).timestamp() if expires else 0
            if end>time.time():result.append({k:p.get(k,'') for k in ('event','headline','severity','instruction')}|{'expires':end})
        return result
    def forecast(self):
        point=read(f'https://api.weather.gov/points/{SITE_LAT},{SITE_LON}')['properties']
        hourly=read(point['forecastHourly'])['properties']['periods'][:48]
        periods=read(point['forecast'])['properties']['periods']
        days={}
        for p in periods:
            day=p['startTime'][:10]
            row=days.setdefault(day,{'date':day,'high':None,'low':None,'periods':[]})
            row['high' if p['isDaytime'] else 'low']=p['temperature'];row['periods'].append(p)
        return {'hourly':hourly,'days':list(days.values())[:5]}
    def snapshot(self):
        with self.lock:sources=dict(self.sources)
        flights=self.flights.snapshot();weather=flights.get('weather',{})
        tiles=weather.pop('tiles',{})
        weather['tiles']=[{'x':x,'y':y,'url':'/radar/%s/%s.png?v=%s'%(x,y,int(weather.get('updated',0)))} for x,y in tiles]
        alerts=sources.get('alerts',{})
        if alerts.get('data'):alerts={**alerts,'data':[a for a in alerts['data'] if a['expires']>time.time()]}
        return {**sources,'alerts':alerts,'location':LOCATION,'timezone':str(TZ),'station':self.station.snapshot(),'flights':flights,'space':self.space.snapshot(),'now':time.time()}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        peer=ipaddress.ip_address(self.client_address[0])
        if not (peer.is_loopback or peer in LAN):
            return self.reply(b'Household network only',403,'text/plain')
        host=self.headers.get('Host','').lower()
        if host not in HOSTS:
            return self.reply(b'Use the office monitor hostname',403,'text/plain')
        path=self.path.split('?')[0]
        if path=='/api/space':return self.reply(json.dumps(self.server.monitor.space.snapshot(),allow_nan=False).encode(),200,'application/json')
        if path=='/api/status':return self.reply(json.dumps(self.server.monitor.snapshot(),allow_nan=False).encode(),200,'application/json')
        if path.startswith('/radar/'):
            try:
                parts=path.split('/');key=(int(parts[2]),int(parts[3].removesuffix('.png')))
                image=self.server.monitor.flights.snapshot()['weather']['tiles'][key]
                return self.reply(image,200,'image/png')
            except (ValueError,KeyError,IndexError):return self.reply(b'',404,'text/plain')
        static=(ROOT/'static').resolve()
        target=(static/('index.html' if path=='/' else path.lstrip('/'))).resolve()
        if target.parent not in (static,static/'flags',static/'logos'):return self.reply(b'',404,'text/plain')
        try:body=target.read_bytes()
        except OSError:return self.reply(b'',404,'text/plain')
        return self.reply(body,200,{'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png'}.get(target.suffix,'application/octet-stream'))
    def reply(self,body,status,kind):
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)

if __name__=='__main__':
    os.umask(0o077)
    monitor=Monitor();httpd=ThreadingHTTPServer(('0.0.0.0',8780),Handler);httpd.monitor=monitor;monitor.start()
    try:httpd.serve_forever()
    finally:monitor.stop.set();monitor.station.stop();monitor.flights.stop();monitor.space.stop();httpd.server_close()
