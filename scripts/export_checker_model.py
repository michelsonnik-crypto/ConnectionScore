"""Export the existing calibrated model for exact browser-side inference."""
from pathlib import Path
import csv,json,pickle,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from train_models import CATEGORICAL,NUMERIC
ROOT=Path(__file__).resolve().parents[1]
with (ROOT/'artifacts/model_bundle.pkl').open('rb') as f:bundle=pickle.load(f)
models={}
for t,b in bundle.items():
    prep,lr=b['model'].steps[0][1],b['model'].steps[1][1]
    cat=prep.named_transformers_['cat'];num=prep.named_transformers_['num']
    models[str(t)]=dict(selected=b['selected'],categories=[list(x) for x in cat.categories_],coefficient=lr.coef_[0].tolist(),intercept=float(lr.intercept_[0]),mean=num.mean_.tolist(),scale=num.scale_.tolist(),gap_rates=b['gap_rates'],default=b['default'],calibration_slope=float(b['calibrator'].coef_[0,0]),calibration_intercept=float(b['calibrator'].intercept_[0]))
with (ROOT/'data/raw/airport_timezones.csv').open() as f:
    airports={r['iata']:dict(name=r['name'],timezone=r['tz'],country=r['country']) for r in csv.DictReader(f) if r['iata'] and r['tz'] and r['country']=='US'}
allowed=set(models['45']['categories'][0])|set(models['45']['categories'][2])|{'ATL','ORD','DFW'}
airports={k:v for k,v in airports.items() if k in allowed}
result=dict(version='baseline-calibrated-2025',categorical=CATEGORICAL,numeric=NUMERIC,models=models,airports=airports,hubs=['ATL','ORD','DFW'],validated_start='2025-10-19',validated_end='2025-10-29',model_sha256=json.loads((ROOT/'reports/models.json').read_text())['model_sha256'],live_schedule_connected=False)
(ROOT/'app/checker-model.json').write_text(json.dumps(result,separators=(',',':')))
print('Exported calibrated baseline, airports',len(airports))
