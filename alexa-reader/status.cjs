'use strict';
// No discovery, control commands, or web listener. Targets and auth stay private.
const fs=require('node:fs'),path=require('node:path');
const config=process.env.HOME_MONITOR_CONFIG||path.join(require('node:os').homedir(),'.config/home-monitor');
const authPath=path.join(config,'alexa-auth.json'),targetsPath=path.join(config,'alexa-targets.json'),statusPath=path.join(config,'alexa-status.json');
function summarize(response,targets,now=Date.now()/1000){
 const states=new Map((response.deviceStates||[]).map(row=>[row.entity?.entityId,row]));
 return targets.map(target=>{
  const row=states.get(target.id),item={name:target.name,display_source:'Alexa',fetched:now,updated:0};
  if(!row||row.error){item.error='Alexa status unavailable';return item;}
  const capabilities=(row.capabilityStates||[]).flatMap(value=>{try{return [typeof value==='string'?JSON.parse(value):value];}catch{return [];}});
  const health=capabilities.find(c=>c.namespace==='Alexa.EndpointHealth'&&c.name==='connectivity');
  const power=capabilities.find(c=>c.namespace==='Alexa.PowerController'&&c.name==='powerState');
  const stamp=Date.parse(power?.timeOfSample)/1000;
  // Alexa returns cached reports, not a new physical observation on each query.
  // Preserve report time just like SmartThings; reject invalid or week-old data.
  if((health&&health.value?.value!=='OK')||!power||!['ON','OFF'].includes(power.value)||!Number.isFinite(stamp)||stamp>now+300||now-stamp>7*86400){item.error='No recent Alexa power reading';return item;}
  item.switch=power.value.toLowerCase();item.updated=item.switch_at=stamp;item.device_note='Alexa last reported state; sample age shown';return item;
 });
}
function save(file,data){const temporary=file+'.tmp';fs.writeFileSync(temporary,JSON.stringify(data),{mode:0o600});fs.renameSync(temporary,file);}
async function main(){
 process.umask(0o077);
 const Alexa=require('alexa-remote2'),alexa=new Alexa(),saved=JSON.parse(fs.readFileSync(authPath)),targets=JSON.parse(fs.readFileSync(targetsPath));
 if(!Array.isArray(targets)||targets.length>5||!targets.every(t=>typeof t.name==='string'&&typeof t.id==='string'))throw Error('Invalid Alexa targets');
 const registration=saved.formerRegistrationData;
 alexa.on('cookie',()=>{const fresh=alexa.cookieData;if(fresh?.macDms?.adp_token&&fresh?.macDms?.device_private_key&&fresh?.refreshToken&&fresh?.localCookie)save(authPath,{cookie:fresh.localCookie,formerRegistrationData:fresh,amazonPage:fresh.amazonPage||saved.amazonPage,authenticatedAt:saved.authenticatedAt});});
 // Refuse interactive fallback. Login is handled separately on the Mac.
 await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(Error('Alexa initialization timed out')),45000);alexa.init({cookie:registration,formerRegistrationData:registration,macDms:registration?.macDms,amazonPage:saved.amazonPage||'amazon.com',useWsMqtt:false,setupProxy:false,cookieRefreshInterval:4*86400000,logger:()=>{}},err=>{clearTimeout(timeout);err?reject(Error('Alexa authentication unavailable')):resolve();});});
 let stopped=false;process.on('SIGTERM',()=>{stopped=true;alexa.stop();process.exit(0);});
 while(!stopped){
  try{
   const response=await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(Error('Query timed out')),30000);alexa.querySmarthomeDevices(targets.map(t=>t.id),(err,result)=>{clearTimeout(timeout);err?reject(err):resolve(result);});});
   save(statusPath,{state:'live',updated:Date.now()/1000,data:{items:summarize(response,targets)}});
  }catch{save(statusPath,{state:'unavailable',updated:Date.now()/1000,data:{items:targets.map(t=>({name:t.name,error:'Alexa query unavailable'}))}});}
  await new Promise(resolve=>setTimeout(resolve,120000));
 }
}
module.exports={summarize};
if(require.main===module)main().catch(()=>{save(statusPath,{state:'unavailable',updated:Date.now()/1000,data:{items:[]},error:'Alexa sign-in required'});process.exit(1);});
