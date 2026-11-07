const {test}=require('node:test'),assert=require('node:assert/strict'),{summarize,selectTargets,resolveGroups}=require('./status.cjs');
const targets=[{name:'front',id:'channel1'},{name:'back',id:'channel2'}],now=1794015000;
function state(id,power,stamp=now){return {entity:{entityId:id},capabilityStates:[JSON.stringify({namespace:'Alexa.PowerController',name:'powerState',value:power,timeOfSample:new Date(stamp*1000).toISOString()})]};}
test('channels map by endpoint, never response position',()=>{const rows=summarize({deviceStates:[state('channel2','ON'),state('channel1','OFF')]},targets,now);assert.deepEqual(rows.map(x=>x.switch),['off','on']);assert.ok(rows.every(x=>x.display_source==='Alexa'));});
test('missing, failed, old and unreachable channels remain unknown',()=>{for(const response of [{},{deviceStates:[state('channel1','ON',now-7*86400-1)]},{deviceStates:[{...state('channel1','ON'),error:'FAULT'}]},{deviceStates:[{...state('channel1','ON'),capabilityStates:[...state('channel1','ON').capabilityStates,{namespace:'Alexa.EndpointHealth',name:'connectivity',value:{value:'UNREACHABLE'}}]}]}]){assert.ok(summarize(response,targets,now).every(x=>x.switch===undefined));}});

test('a cached report retains its sample time, never query time',()=>{const row=summarize({deviceStates:[state('channel1','ON',now-7200)]},targets,now)[0];assert.equal(row.switch,'on');assert.equal(row.updated,now-7200);assert.equal(row.fetched,now);});

const device=(name,id,extra={})=>({friendlyName:name,enablement:'ENABLED',legacyAppliance:{applianceId:id,applianceTypes:['SMARTPLUG'],capabilities:[{interfaceName:'Alexa.PowerController',properties:{retrievable:true}}],...extra}});
test('discovery excludes disabled, Echo, iPhone, scenes and curated exclusions',()=>{
 const devices=[device('Live','1'),{...device('Disabled','2'),enablement:'DISABLED_BY_CUSTOMER'},device('Echo','3',{applianceTypes:['ALEXA_VOICE_ENABLED']}),device('Greg iPhone','4'),device('Retired','5'),device('Scene','6',{capabilities:[]})];
 assert.deepEqual(selectTargets(devices,{excluded:['retired']}).map(t=>t.name),['Live']);
});
test('multiple capabilities preserve units and timestamps; no arbitrary sensitive properties',()=>{
 const target={name:'Sensor',id:'1',capabilities:[{interfaceName:'Alexa.InventoryLevelSensor',instance:'Battery',configuration:{measurement:{'@type':'Percentage'}}}]};
 const cap=(namespace,name,value,instance)=>({namespace,name,value,instance,timeOfSample:new Date((now-2)*1000).toISOString()});
 const response={deviceStates:[{entity:{entityId:'1'},capabilityStates:[cap('Alexa.TemperatureSensor','temperature',{value:21,scale:'CELSIUS'}),cap('Alexa.ContactSensor','detectionState','DETECTED'),cap('Alexa.MotionSensor','detectionState','NOT_DETECTED'),cap('Alexa.InventoryLevelSensor','level',{value:55},'Battery'),cap('Alexa.InteractionLockController','unlockCode','SECRET')]}]};
 const row=summarize(response,[target],now)[0];assert.equal(row.temperature,21);assert.equal(row.temperature_unit,'C');assert.equal(row.contact,'open');assert.equal(row.motion,'inactive');assert.equal(row.battery,55);assert.equal(row.battery_unit,'%');assert.ok(!JSON.stringify(row).includes('SECRET'));
});
test('nested groups resolve and cycles cannot recurse forever',()=>{
 const groups={applianceGroups:[{name:'Parent',groupId:'p',applianceIds:['1'],childIds:['c']},{name:'Child',groupId:'c',applianceIds:['2'],childIds:['p']}]};
 assert.deepEqual(resolveGroups(groups,[device('One','1'),device('Two','2')])[0].members,['One','Two']);
});
