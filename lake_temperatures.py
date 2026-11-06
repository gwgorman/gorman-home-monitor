"""Read public LakeMonster surface estimates; never treat publication as sensor time."""
import datetime as dt
import json
import math
import re
import time
import urllib.request
from html.parser import HTMLParser

SOURCES = {
    'lake': 'https://lakemonster.com/lake/Texas/Lewisville-Lake-%28Little-Elm-Reservoir%29-211',
    'richland': 'https://lakemonster.com/lake/Texas/Richland-Chambers-Reservoir-571',
}

class Scripts(HTMLParser):
    def __init__(self):
        super().__init__(); self.active = False; self.parts = []
    def handle_starttag(self, tag, attrs):
        self.active = tag == 'script'
    def handle_endtag(self, tag):
        if tag == 'script': self.active = False
    def handle_data(self, data):
        if self.active: self.parts.append(data)

def parse_temperature(page, url, now=None):
    """Use only the requested lake's explicit water-temperature property."""
    now = time.time() if now is None else now
    parser = Scripts(); parser.feed(page)
    texts = list(parser.parts)
    for script in parser.parts:
        match = re.fullmatch(r'self\.__next_f\.push\((.*)\)', script, re.S)
        if match:
            try:
                row = json.loads(match[1])
                if len(row) > 1 and isinstance(row[1], str): texts.append(row[1])
            except (ValueError, TypeError): pass
    decoder = json.JSONDecoder()
    for text in texts:
        for match in re.finditer(r'\{"@context"\s*:', text):
            try: item, _ = decoder.raw_decode(text[match.start():])
            except ValueError: continue
            for prop in item.get('additionalProperty', []):
                if prop.get('propertyID') != 'water-temperature': continue
                if prop.get('mainEntityOfPage', '').rsplit('-', 1)[-1] != url.rsplit('-', 1)[-1]: continue
                value = re.fullmatch(r'(-?\d+(?:\.\d+)?)\s*°F', str(prop.get('value', '')))
                if not value: continue
                temperature = float(value[1])
                if not math.isfinite(temperature) or not 32 <= temperature <= 110: continue
                published = None
                try:
                    date = dt.datetime.fromisoformat(prop.get('dateModified', '').replace('Z', '+00:00'))
                    if date.tzinfo is not None and 946684800 <= date.timestamp() <= now + 300:
                        published = date.timestamp()
                except (ValueError, TypeError): pass
                return {'temperature_f': temperature, 'published_at': published,
                        'observed_at': None, 'estimated': True, 'source': 'LakeMonster',
                        'url': url, 'fetched_at': now, 'error': ''}
    raise ValueError('No lake-specific published temperature')

def fetch_temperature(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'GormanHomeMonitor/1.0'})
    with urllib.request.urlopen(request, timeout=20) as response:
        page = response.read(2_000_000).decode('utf-8', errors='replace')
    return parse_temperature(page, url)
