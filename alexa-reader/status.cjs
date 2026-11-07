'use strict';
// Read-only discovery and status queries. No device commands or web listener.
const fs=require('node:fs'),path=require('node:path');
const config=process.env.HOME_MONITOR_CONFIG||path.join(require('node:os').homedir(),'.config/home-monitor');
const authPath=path.join(config,'alexa-auth.json'),statusPath=path.join(config,'alexa-status.json');
const MAX_SAMPLE_AGE=7*86400;
const normal=name=>String(name||'').trim().toLowerCase().replace(/’/g,"'").replace(/\s+/g,' ');
const FIELD_NAMES=['switch','level','temperature','humidity','motion','contact','lock','battery','playbackStatus','volume','mute','color','colorTemperature','thermostatMode','targetTemperature','armState','water'];
function selectTargets(devices,settings={}){
 const excluded=new Set((settings.excluded||[]).map(normal));
 return devices.flatMap(device=>{
  const legacy=device.legacyAppliance||{},name=(device.friendlyName||legacy.friendlyName||'').trim(),types=legacy.applianceTypes||[];
  if(!name||!legacy.applianceId||legacy.isEnabled===false||(device.enablement&&device.enablement!=='ENABLED')||types.includes('ALEXA_VOICE_ENABLED')||/iphone/i.test(name)||excluded.has(normal(name)))return [];
  const capabilities=legacy.capabilities||[];
  if(!capabilities.some(cap=>cap.properties?.retrievable===true))return [];
  return [{name,id:legacy.applianceId,types,capabilities}];
 });
}
function summarize(response,targets,now=Date.now()/1000){
 const states=new Map((response.deviceStates||[]).map(row=>[row.entity?.entityId,row]));
 return targets.map(target=>{
  const row=states.get(target.id),item={name:target.name,display_source:'Alexa',fetched:now,updated:0};
  if(!row||row.error){item.error='Alexa status unavailable';return item;}
  const caps=(row.capabilityStates||[]).flatMap(value=>{try{return [typeof value==='string'?JSON.parse(value):value];}catch{return [];}}).filter(c=>c&&typeof c==='object');
  const health=caps.find(c=>c.namespace==='Alexa.EndpointHealth'&&c.name==='connectivity');
  if(health&&health.value?.value!=='OK'){item.error='Alexa endpoint unreachable';return item;}
  const put=(key,value,stamp,unit)=>{if(value===undefined||value===null)return;item[key]=value;item[key+'_at']=stamp;if(unit)item[key+'_unit']=unit;item.updated=Math.max(item.updated,stamp);};
  const percent=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=100?value:undefined;
  for(const cap of caps){
   const stamp=Date.parse(cap.timeOfSample)/1000;
   if(!Number.isFinite(stamp)||stamp>now+300||now-stamp>MAX_SAMPLE_AGE)continue;
   const value=cap.value,key=cap.namespace+'.'+cap.name;
   if(key==='Alexa.PowerController.powerState')put('switch',({ON:'on',OFF:'off'})[value],stamp);
   else if(key==='Alexa.BrightnessController.brightness')put('level',percent(value),stamp,'%');
   else if(key==='Alexa.TemperatureSensor.temperature'||key==='Alexa.ThermostatController.targetSetpoint'){
    const units={CELSIUS:'C',FAHRENHEIT:'F'},unit=units[value?.scale];
    if(unit&&typeof value.value==='number'&&Number.isFinite(value.value)&&value.value>=-100&&value.value<=200)put(key.includes('targetSetpoint')?'targetTemperature':'temperature',value.value,stamp,unit);
   }
   else if(key==='Alexa.HumiditySensor.relativeHumidity')put('humidity',percent(typeof value==='object'?value?.value:value),stamp,'%');
   else if(key==='Alexa.MotionSensor.detectionState')put('motion',({DETECTED:'active',NOT_DETECTED:'inactive'})[value],stamp);
   else if(key==='Alexa.ContactSensor.detectionState')put('contact',({DETECTED:'open',NOT_DETECTED:'closed'})[value],stamp);
   else if(key==='Alexa.LockController.lockState')put('lock',({LOCKED:'locked',UNLOCKED:'unlocked',JAMMED:'jammed'})[value],stamp);
   else if(key==='Alexa.InventoryLevelSensor.level'&&/battery/i.test(cap.instance||'')){
    const definition=(target.capabilities||[]).find(c=>c.interfaceName===cap.namespace&&c.instance===cap.instance);
    if(definition?.configuration?.measurement?.['@type']==='Percentage')put('battery',percent(typeof value==='object'?value?.value:value),stamp,'%');
   }
   else if(key==='Alexa.RangeController.rangeValue'&&/humidity/i.test(cap.instance||''))put('humidity',percent(value),stamp,'%');
   else if(key==='Alexa.PlaybackStateReporter.playbackState')put('playbackStatus',({PLAYING:'playing',PAUSED:'paused',STOPPED:'stopped'})[typeof value==='object'?value?.state:value],stamp);
   else if(key==='Alexa.Speaker.volume')put('volume',percent(value),stamp,'%');
   else if(key==='Alexa.Speaker.muted'&&typeof value==='boolean')put('mute',value?'muted':'unmuted',stamp);
   else if(key==='Alexa.ColorTemperatureController.colorTemperatureInKelvin'&&Number.isFinite(value)&&value>=1000&&value<=15000)put('colorTemperature',value,stamp,'K');
   else if(key==='Alexa.ColorController.color'&&value&&Number.isFinite(value.hue)&&value.hue>=0&&value.hue<=360&&value.saturation>=0&&value.saturation<=1&&value.brightness>=0&&value.brightness<=1)put('color',{hue:value.hue,saturation:value.saturation,brightness:value.brightness},stamp);
   else if(key==='Alexa.ThermostatController.thermostatMode'&&['AUTO','COOL','HEAT','OFF','ECO','CUSTOM'].includes(value))put('thermostatMode',value.toLowerCase(),stamp);
   else if(key==='Alexa.SecurityPanelController.armState'&&['ARMED_AWAY','ARMED_STAY','ARMED_NIGHT','DISARMED'].includes(value))put('armState',value.toLowerCase(),stamp);
  }
  if(!FIELD_NAMES.some(field=>item[field]!==undefined))item.error='No usable recent Alexa reading';
  else item.device_note='Alexa last reported state; sample age shown';
  return item;
 });
}
function resolveGroups(groups,devices,settings={}){
 const excluded=new Set((settings.excluded||[]).map(normal)),lookup=new Map(),ignored=new Set(),all=groups.applianceGroups||[];
 for(const device of devices){
  const legacy=device.legacyAppliance||{},name=(device.friendlyName||'').trim();
  const ids=[legacy.applianceId,legacy.entityId,device.id,device.endpointId,...(legacy.mergedApplianceIds||[])].filter(id=>typeof id==='string');
  if(!name||legacy.isEnabled===false||(device.enablement&&device.enablement!=='ENABLED')||(legacy.applianceTypes||[]).includes('ALEXA_VOICE_ENABLED')||/iphone/i.test(name)||excluded.has(normal(name))){ids.forEach(id=>ignored.add(id));continue;}
  for(const id of ids)lookup.set(id,name);
 }
 const byId=new Map(all.map(g=>[g.groupId,g]));
 function members(group,seen=new Set()){
  if(seen.has(group.groupId))return {names:[],unresolved:0};seen=new Set(seen).add(group.groupId);
  const names=[],unknown=new Set();
  for(const id of group.applianceIds||[]){if(lookup.has(id))names.push(lookup.get(id));else if(!ignored.has(id))unknown.add(id);}
  for(const id of group.childIds||[]){const child=byId.get(id);if(child){const result=members(child,seen);names.push(...result.names);}else unknown.add(id);}
  return {names:[...new Set(names)].sort((a,b)=>a.localeCompare(b)),unresolved:unknown.size};
 }
 return all.map(group=>{const result=members(group);return {name:group.name,members:result.names,unresolved:result.unresolved};});
}
function save(file,data){const temporary=file+'.tmp';fs.writeFileSync(temporary,JSON.stringify(data),{mode:0o600});fs.renameSync(temporary,file);}
async function main(){
 process.umask(0o077);
 const Alexa=require('alexa-remote2'),alexa=new Alexa(),saved=JSON.parse(fs.readFileSync(authPath)),registration=saved.formerRegistrationData;
 alexa.on('cookie',()=>{const fresh=alexa.cookieData;if(fresh?.macDms?.adp_token&&fresh?.macDms?.device_private_key&&fresh?.refreshToken&&fresh?.localCookie)save(authPath,{cookie:fresh.localCookie,formerRegistrationData:fresh,amazonPage:fresh.amazonPage||saved.amazonPage,authenticatedAt:saved.authenticatedAt});});
 const call=(method,args=[],timeout=45000)=>new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Alexa request timed out')),timeout);alexa[method](...args,(err,result)=>{clearTimeout(timer);err?reject(err):resolve(result);});});
 await call('init',[{cookie:registration,formerRegistrationData:registration,macDms:registration?.macDms,amazonPage:saved.amazonPage||'amazon.com',useWsMqtt:false,setupProxy:false,cookieRefreshInterval:4*86400000,logger:()=>{}}]);
 process.on('SIGTERM',()=>{alexa.stop();process.exit(0);});
 let targets=[],entries=[],discoveryAt=0,inventoryCount=0,cycleQueried=0;const readings=new Map();
 const publish=()=>{
  const items=targets.map(t=>readings.get(t.id)||{name:t.name,error:'Awaiting Alexa query',updated:0});
  save(statusPath,{state:'live',updated:Date.now()/1000,discovery_at:discoveryAt,group_entries:entries,
   coverage:{inventory:inventoryCount,eligible:targets.length,queried:cycleQueried,readings:items.filter(i=>!i.error).length,unavailable:items.filter(i=>i.error).length},data:{items}});
 };
 while(true){
  const cycleStarted=Date.now();let limited=false;cycleQueried=0;
  if(Date.now()/1000-discoveryAt>=21600){
   try{
    let settings={};try{settings=JSON.parse(fs.readFileSync(path.join(config,'device-tiles.json')));}catch{}
    const devices=await call('getSmarthomeDevicesV2'),groups=await call('getSmarthomeGroups');
    if(!Array.isArray(devices)||!Array.isArray(groups.applianceGroups))throw Error('Invalid discovery');
    targets=selectTargets(devices,settings);
    const priority=new Map((settings.alexa_priority||[]).map((name,index)=>[normal(name),index]));
    targets.sort((a,b)=>(priority.get(normal(a.name))??10000)-(priority.get(normal(b.name))??10000));
    entries=resolveGroups(groups,devices,settings);inventoryCount=devices.length;discoveryAt=Date.now()/1000;
   }catch{if(!targets.length)throw Error('Alexa discovery unavailable');}
  }
  for(let i=0;i<targets.length;i+=16){
   const batch=targets.slice(i,i+16);
   try{
    const response=await call('querySmarthomeDevices',[batch.map(t=>t.id)]);
    const errors=response.errors||[];
    limited=errors.some(e=>/throttl|rate|too.many/i.test(e.code||e.message||''));
    summarize(response,batch).forEach((row,index)=>readings.set(batch[index].id,row));
   }catch(error){limited=/429|throttl|rate|too.many/i.test(error.message||'');for(const t of batch)readings.set(t.id,{name:t.name,error:'Alexa query unavailable',updated:0,fetched:Date.now()/1000});}
   cycleQueried+=batch.length;publish();if(limited)break;
   if(i+16<targets.length)await new Promise(resolve=>setTimeout(resolve,12000));
  }
  // Each endpoint is queried at most once per five-minute cycle; back off on throttling.
  await new Promise(resolve=>setTimeout(resolve,Math.max(30000,(limited?900000:300000)-(Date.now()-cycleStarted))));
 }
}
module.exports={summarize,selectTargets,resolveGroups,FIELD_NAMES};
if(require.main===module)main().catch(()=>{save(statusPath,{state:'unavailable',updated:Date.now()/1000,data:{items:[]},error:'Alexa sign-in or discovery unavailable'});process.exit(1);});
