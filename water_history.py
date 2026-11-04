"""Primary-source lake histories and reservoir release reports."""
import datetime as dt
from html.parser import HTMLParser
import math
import re

PARAMETERS={'62614':'elevation_ft','00035':'wind_mph','00036':'wind_degrees','00045':'rain_in','00054':'storage_acft','00060':'flow_cfs','00065':'gage_ft'}

def lake_history(payload,site):
    result={'history':{},'source':'USGS DIRECT','raw_ok':False,'error':'','updated':0}
    for series in payload.get('value',{}).get('timeSeries',[]):
        info=series.get('sourceInfo',{})
        if not any(str(x.get('value'))==site for x in info.get('siteCode',[])):continue
        variable=series.get('variable',{});codes=variable.get('variableCode',[])
        field=PARAMETERS.get(str(codes[0].get('value'))) if codes else None
        if not field:continue
        rows={};missing=variable.get('noDataValue',-999999)
        for block in series.get('values',[]):
            for sample in block.get('value',[]):
                try:
                    value=float(sample['value']);stamp=dt.datetime.fromisoformat(sample['dateTime'].replace('Z','+00:00')).timestamp()
                    if not math.isfinite(value) or value==float(missing) or value<=-999:continue
                    rows[stamp]=value
                except (KeyError,TypeError,ValueError):continue
        points=[[t,rows[t]] for t in sorted(rows)]
        if not points:continue
        result['history'][field]=points
        result[field]=points[-1][1];result[field+'_at']=points[-1][0]
    elevation=result['history'].get('elevation_ft',[])
    if elevation:
        latest=elevation[-1];result['updated']=latest[0];result['raw_ok']=True
        for label,span in [('change_24h_ft',86400),('change_7d_ft',7*86400)]:
            target=latest[0]-span
            point=min(elevation,key=lambda x:abs(x[0]-target))
            if abs(point[0]-target)<=3600:result[label]=latest[1]-point[1]
    elif result['history']:
        result['updated']=max(x[-1][0] for x in result['history'].values());result['raw_ok']=True
    if not result['raw_ok']:result['error']='NO VALID USGS OBSERVATIONS'
    return result

class ReportRows(HTMLParser):
    def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None;self.text=[]
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        if tag in ('td','th'):self.cell=[]
    def handle_data(self,data):
        self.text.append(data)
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            if self.row is not None:self.row.append(' '.join(' '.join(self.cell).split()))
            self.cell=None
        if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None

def release_report(html):
    parser=ReportRows();parser.feed(html);text=' '.join(parser.text)
    match=re.search(r'Data as of\s+(\d{2}\s+\w{3}\s+\d{4})\s*@\s*(\d{4})\s*(CST|CDT)',text)
    updated=0
    if match:
        stamp=dt.datetime.strptime(match[1]+' '+match[2],'%d %b %Y %H%M')
        updated=stamp.replace(tzinfo=dt.timezone(dt.timedelta(hours=-6 if match[3]=='CST' else -5))).timestamp()
    result={}
    for row in parser.rows:
        key={'Lewisville Lake':'lake','Richland Chambers':'richland'}.get(row[0] if row else '')
        if key and len(row)>=7:
            item={'updated':updated,'source':'USACE RESERVOIR RELEASE REPORT'}
            for name,index in [('elevation_ft',1),('normal_ft',2),('difference_ft',3),('change_24h_ft',4),('release_cfs',5),('flood_ft',6)]:
                try:
                    value=float(row[index].replace(',',''))
                    if math.isfinite(value):item[name]=value
                except ValueError:pass
            result[key]=item
    if not result:raise ValueError('Reservoir report format not recognized')
    return result
