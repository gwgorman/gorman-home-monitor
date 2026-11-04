/* Native SVG weather instruments: local observations, no third-party widgets. */
const WeatherInstruments=(()=>{
 const NS='http://www.w3.org/2000/svg';
 function svgNode(tag,attrs={},text){const n=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n;}
 function instrument(label){const root=el('div',undefined,'instrument');root.append(el('div',label,'instrument-label'));return root;}
 function gauge(label,value,unit,min,max,digits=0,color='var(--accent)'){
  const root=instrument(label),valid=typeof value==='number'&&Number.isFinite(value),display=valid?num(value,digits):'—',svg=svgNode('svg',{viewBox:'0 0 240 190',role:'img','aria-label':`${label}: ${display} ${unit}`});
  const path='M 32 107 A 88 88 0 0 1 208 107';
  svg.append(svgNode('path',{d:path,fill:'none',stroke:'var(--line)','stroke-width':19}));
  if(valid){const ratio=Math.max(0,Math.min(1,(value-min)/(max-min))),angle=Math.PI*(1-ratio);svg.append(svgNode('path',{d:path,fill:'none',stroke:color,'stroke-width':19,pathLength:100,'stroke-dasharray':`${ratio*100} 100`}));svg.append(svgNode('line',{x1:120,y1:107,x2:120+Math.cos(angle)*76,y2:107-Math.sin(angle)*76,stroke:'var(--text)','stroke-width':3}),svgNode('circle',{cx:120,cy:107,r:4,fill:'var(--text)'}));}
  svg.append(svgNode('text',{x:120,y:153,'text-anchor':'middle',class:'dial-value'},display),svgNode('text',{x:120,y:184,'text-anchor':'middle',class:'dial-unit'},unit),svgNode('text',{x:25,y:130,'text-anchor':'middle',class:'dial-limit'},min),svgNode('text',{x:215,y:130,'text-anchor':'middle',class:'dial-limit'},max));root.append(svg);return root;
 }
 function compass(degrees){
  const root=instrument('Wind direction');root.classList.add('compass-instrument');const valid=typeof degrees==='number'&&Number.isFinite(degrees),svg=svgNode('svg',{viewBox:'0 0 240 235',role:'img','aria-label':valid?`Wind from ${num(degrees)} degrees`:'Wind direction unavailable'});
  svg.append(svgNode('circle',{cx:120,cy:112,r:78,fill:'none',stroke:'var(--line)','stroke-width':12}));
  for(let d=0;d<360;d+=30){const a=d*Math.PI/180;svg.append(svgNode('line',{x1:120+Math.sin(a)*66,y1:112-Math.cos(a)*66,x2:120+Math.sin(a)*73,y2:112-Math.cos(a)*73,stroke:'var(--muted)','stroke-width':1}));}
  for(const [text,x,y]of [['N',120,17],['E',221,118],['S',120,220],['W',19,118]])svg.append(svgNode('text',{x,y,'text-anchor':'middle',class:'compass-point'},text));
  if(valid)svg.append(svgNode('path',{d:'M 120 26 L 110 48 L 130 48 Z',fill:'var(--accent)',transform:`rotate(${degrees} 120 112)`}));
  svg.append(svgNode('text',{x:120,y:113,'text-anchor':'middle',class:'compass-value'},valid?num(degrees)+'°':'—'),svgNode('text',{x:120,y:139,'text-anchor':'middle',class:'compass-bearing'},valid?['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'][Math.round(degrees/22.5)%16]:'No report'));root.append(svg);return root;
 }
 function pressureChart(points){
  const root=el('div',undefined,'pressure-history'),clean=points.filter(x=>Number.isFinite(x.pressure_mb)&&Number.isFinite(x.time)).slice(-2880);root.append(el('div','Barometric pressure · available history, up to 24 hours','instrument-label'));
  if(clean.length<2){root.append(el('p','Pressure history builds from local station reports.','note'));return root;}
  const svg=svgNode('svg',{viewBox:'0 0 720 155',role:'img','aria-label':'Barometric pressure history in inches of mercury'}),values=clean.map(x=>x.pressure_mb*.029529983),low=Math.floor((Math.min(...values)-.005)*100)/100,high=Math.ceil((Math.max(...values)+.005)*100)/100,span=Math.max(.02,high-low),start=clean[0].time,end=clean[clean.length-1].time;
  for(let i=0;i<3;i++){const y=18+i*48;svg.append(svgNode('line',{x1:55,y1:y,x2:705,y2:y,stroke:'var(--line)','stroke-width':1}),svgNode('text',{x:45,y:y+4,'text-anchor':'end',class:'chart-axis'},(high-i*span/2).toFixed(2)));}
  let path='';clean.forEach((p,i)=>{const x=55+(p.time-start)/Math.max(1,end-start)*650,y=18+(high-values[i])/span*96;path+=(i&&p.time-clean[i-1].time<900?' L ':' M ')+x+' '+y;});svg.append(svgNode('path',{d:path,fill:'none',stroke:'var(--blue)','stroke-width':2.5}));
  for(const [time,x,anchor]of [[start,55,'start'],[end,705,'end']])svg.append(svgNode('text',{x,y:145,'text-anchor':anchor,class:'chart-axis'},fmt(new Date(time*1000),{hour:'numeric',minute:'2-digit'})));root.append(svg);return root;
 }
 function lightningDisplay(w){
  const root=el('section',undefined,'lightning-display'),current=fresh(w.temperature_observed,300),count=current&&Number.isFinite(w.lightning_5m)?w.lightning_5m:null,distance=count>0&&Number.isFinite(w.lightning_5m_km)?w.lightning_5m_km*.621371:null;
  root.append(el('h3','Lightning'));
  const metrics=el('div',undefined,'lightning-metrics');
  for(const [label,value,detail]of [['Reported strikes · 5 min',count==null?'—':String(count),count==null?'Waiting for station':'Local station reports'],['Average distance',distance==null?'—':num(distance,1)+' mi',distance==null?'No recent strike distance':'Past 5 minutes'],['Last detected event',w.last_lightning?fmt(new Date(w.last_lightning*1000),{hour:'numeric',minute:'2-digit'}):'None received',w.last_lightning?age(w.last_lightning):'Since monitor started']]){const metric=el('div',undefined,'lightning-metric');metric.append(el('div',label,'lightning-label'),el('strong',value),el('div',detail,'lightning-note'));metrics.append(metric);}root.append(metrics);return root;
 }
 function panel(title,cls=''){const p=el('section',undefined,'station-panel '+cls);p.append(el('h2',title));return p;}
 function render(){
  const {w,current}=station(),windCurrent=fresh(w.observed,180),v=k=>current&&typeof w[k]==='number'?w[k]:null,wind=k=>windCurrent&&typeof w[k]==='number'?w[k]:null,toF=x=>x==null?null:x*9/5+32,mph=x=>x==null?null:x*2.23694,root=el('div',undefined,'station-dashboard');
  const windPanel=panel('Wind','wind-panel'),windDials=el('div',undefined,'wind-dials');windDials.append(gauge('Speed',mph(wind('wind_mps')),'mph',0,30,1),gauge('Gust',mph(v('wind_gust_mps')),'mph',0,60,1));windPanel.append(compass(wind('wind_direction')),windDials);
  const air=panel('Air','air-panel'),airDials=el('div',undefined,'air-dials');airDials.append(gauge('Temperature',toF(v('temperature_c')),'°F',30,115,1),gauge('Humidity',v('humidity'),'%',0,100,0,'var(--blue)'),gauge('Barometric pressure',v('pressure_mb')==null?null:w.pressure_mb*.029529983,'inHg',28.6,30.8,2,'var(--blue)'));air.append(airDials,pressureChart(state.station?.weather_history||[]),lightningDisplay(w));
  const solar=panel('Solar','solar-panel');solar.append(gauge('Solar radiation',v('solar_wm2'),'W/m²',0,1000),gauge('UV index',v('uv'),'index',0,11,1),gauge('Illuminance',v('illuminance'),'lux',0,100000));
  const extras=el('div',undefined,'station-extras'),rain=panel('Precipitation');rain.append(gauge('Rain rate',v('rain_rate_mmh')==null?null:w.rain_rate_mmh/25.4,'in/hr',0,2,2));rain.append(el('div','Type: '+(current?({0:'None',1:'Rain',2:'Hail',3:'Rain and hail'}[w.precip_type]??'Unknown'):'No report'),'instrument-note'));
  const lightning=panel('Lightning'),lightningCurrent=fresh(w.temperature_observed,300),distance=lightningCurrent&&w.lightning_5m>0&&Number.isFinite(w.lightning_5m_km)?w.lightning_5m_km*.621371:null;lightning.append(gauge('Average distance · last 5 min',distance,'miles',0,50,1),el('div',lightningCurrent?`${w.lightning_5m??'—'} strikes in the last 5 minutes`:'Strike count unavailable','instrument-note'));
  const status=panel('Station status');status.append(gauge('Battery',v('battery_v'),'V',0,3,3),el('div',(current?'Local UDP · ':'Waiting for station · ')+age(w.temperature_observed),'instrument-note'));
  extras.append(rain,lightning,status);if(pageSlice()===0){root.classList.add('station-primary');root.append(windPanel,air);}else{root.classList.add('station-secondary');root.append(solar,extras);}return root;
 }
 return {render};
})();
