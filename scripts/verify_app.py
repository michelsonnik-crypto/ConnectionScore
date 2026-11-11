"""Static/data integration checks. This is not browser QA."""
from pathlib import Path
from html.parser import HTMLParser
import json
import re
root=Path(__file__).resolve().parents[1]
class Parser(HTMLParser):
    def __init__(self):super().__init__();self.ids=set()
    def handle_starttag(self,tag,attrs):
        for k,v in attrs:
            if k=='id':
                assert v not in self.ids, f'Duplicate DOM id: {v}'
                self.ids.add(v)
p=Parser();p.feed((root/'app/index.html').read_text())
js=(root/'app/app.js').read_text()
for ident in re.findall(r"\$\('([^']+)'\)",js):assert ident in p.ids,ident
payload=json.loads((root/'app/research.json').read_text())
assert payload['summary']['split_flight_overlap']==0
assert payload['connections']['test']['status']=='locked_not_downloaded_not_opened'
for r in payload['candidates']:
    assert 0 <= r['risk_30'] <= r['risk_45'] <= r['risk_60'] <= 1
    assert all(re.fullmatch('[A-Z0-9]{2,4}',r[k]) for k in ['origin','hub','destination','carrier'])
    assert '2025-10-19'<=r['departure_date']<'2025-10-30'
assert payload['candidates']
print('DOM references, data coverage, monotone probabilities and test lock verified.')
print('Browser visual/interaction QA not performed: managed browser tool unavailable.')
