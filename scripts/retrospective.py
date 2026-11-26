"""Controlled feature ablation, retrospective development only. No app export."""
from pathlib import Path
import sys,json,subprocess,time,pickle,hashlib
from datetime import datetime,timezone
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src'),str(Path(__file__).resolve().parent)]
import numpy as np
import pandas as pd
from scipy.special import logit
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder,StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier
from connection_score.safety import read_development,assert_features,sha256
from connection_score.history import collect,augment,HISTORY_COLUMNS,POLICY
from train_models import features,CATEGORICAL,NUMERIC,evaluate,policy_report
from model_search import calibrate,calibrated
ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'configs/retrospective.json').read_text())

def dump(path,x):path.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def design(d,name):
 x=features(d)
 if name.endswith('history'):
  x[HISTORY_COLUMNS]=d[HISTORY_COLUMNS];assert_features(x.columns,allow_history=True)
 if name=='xgb_gap':return x[['gap_minutes']]
 return x

def fit(name,d,t):
 y=d[f'label_{t}'];default=float(y.mean())
 if name=='constant':return ('constant',default)
 if name=='gap_cdf':
  # The event is ArrDelay > gap - tau. Pool incoming delays with one
  # observation per incoming flight, avoiding degree-weighted delay CDFs.
  u=d.drop_duplicates('first_id');delay=u.gap_minutes-u.remaining_from_primary
  return ('cdf',np.sort(delay.to_numpy()))
 x=design(d,name);cat=[] if name=='xgb_gap' else CATEGORICAL
 num=[c for c in x if c not in cat]
 prep=ColumnTransformer(([('cat',OneHotEncoder(handle_unknown='ignore'),cat)] if cat else [])+[('num',StandardScaler(),num)])
 est=LogisticRegression(C=.5,max_iter=1800,random_state=42) if name.startswith('logistic') else XGBClassifier(n_estimators=250,max_depth=4,learning_rate=.05,min_child_weight=20,subsample=.8,colsample_bytree=.8,reg_lambda=5,tree_method='hist',n_jobs=2,random_state=42,eval_metric='logloss')
 model=make_pipeline(prep,est);model.fit(x,y);return ('model',model)

def predict(bundle,d,name,t):
 kind,m=bundle
 if kind=='constant':return np.full(len(d),m)
 if kind=='cdf':return (len(m)-np.searchsorted(m,d.gap_minutes.to_numpy()-t,side='right')+1)/(len(m)+2)
 return m.predict_proba(design(d,name))[:,1]

def cap(d,n):return d.sample(n=min(n,len(d)),random_state=42).sort_index()

def difference(d,p,q):
 tmp=pd.DataFrame({'day':d.departure_date.to_numpy(),'delta':(p-d.label_45.to_numpy())**2-(q-d.label_45.to_numpy())**2})
 blocks=tmp.groupby('day').delta.agg(['sum','count']).to_numpy();rng=np.random.default_rng(42)
 totals=blocks[rng.integers(0,len(blocks),size=(CONFIG['bootstrap_repetitions'],len(blocks)))].sum(axis=1)
 values=totals[:,0]/totals[:,1]
 return dict(brier_difference=float(tmp.delta.mean()),interval_95=np.quantile(values,[.025,.975]).tolist(),days=len(blocks),method='paired day-block bootstrap; negative favors first model; exploratory')

def matched_stats(train):
 d=train[(train.hub=='ATL')&(train.carrier=='DL')&train.gap_minutes.between(60,120)].copy()
 d['period']=np.where(d.departure_hour.between(6,11),'morning',np.where(d.departure_hour.between(18,23),'evening','other'))
 d=d[d.period!='other'];d['gap_bin']=(d.gap_minutes//15).astype(int)
 keys=['departure_date','origin','destination','gap_bin']
 tab=d.groupby(keys+['period'],observed=True).label_45.agg(['sum','count']).unstack('period').dropna()
 weight=tab[('count','morning')]+tab[('count','evening')]
 delta=tab[('sum','evening')]/tab[('count','evening')]-tab[('sum','morning')]/tab[('count','morning')]
 daily=pd.DataFrame({'numerator':weight*delta,'denominator':weight}).groupby(level='departure_date').sum().to_numpy()
 rng=np.random.default_rng(42);v=daily[rng.integers(0,len(daily),size=(2000,len(daily)))].sum(axis=1)
 return dict(population='ATL, DL, gap 60-120; first-flight local DEPARTURE hour, not hub arrival hour',control='Matched same day, origin, destination, carrier and 15-minute gap bin; only cells containing both periods',candidate_pairs=len(d),retained_pairs=int(weight.sum()),matched_cells=len(tab),days=len(daily),standardized_evening_minus_morning=float((weight*delta).sum()/weight.sum()),interval_95=np.quantile(v[:,0]/v[:,1],[.025,.975]).tolist(),limitations='Restricted overlap population; residual exact-gap imbalance and between-day serial dependence; association not causation')

def main():
 run=sys.argv[1];out=ROOT/'reports/runs'/run;out.mkdir(parents=True,exist_ok=False);start=time.perf_counter()
 report=dict(run_id=run,commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),started_at_utc=datetime.now(timezone.utc).isoformat(),configuration=CONFIG,status='running',test_accessed=False,app_changed=False)
 dump(out/'results.json',report)
 try:
  snapshot=collect(ROOT)
  # Reconstruct incoming arrival delays from an isolated source audit export.
  # Read raw only via history.collect plus the guarded archive helper below.
  from connection_score.safety import raw_archive
  from connection_score.pipeline import flight_id
  import csv,io
  frames={s:read_development(ROOT/f'data/processed/connections_{s}.csv.gz',dtype={k:'category' for k in CATEGORICAL+['status']}) for s in ['train','validation','calibration','demo']}
  ids={s:set(d.first_id)|set(d.second_id) for s,d in frames.items()}
  for i,s in enumerate(ids):
   for other in list(ids)[i+1:]:assert not ids[s]&ids[other]
  full_demo=frames['demo'];frames={s:augment(d[d.status=='operated'].copy(),snapshot) for s,d in frames.items()}
  train=frames['train'];needed=set(train.first_id);delays={}
  for month in range(1,9):
   with raw_archive(ROOT/f'data/raw/bts_2025_{month:02d}.zip') as z:
    member=next(n for n in z.namelist() if n.endswith('.csv'))
    with z.open(member) as stream:
     for row in csv.DictReader(io.TextIOWrapper(stream,encoding='utf-8-sig')):
      if row['Dest'] not in ['ATL','ORD','DFW']:continue
      fid=flight_id(row)
      if fid in needed:delays[fid]=float(row['ArrDelay'])
  assert needed<=delays.keys()
  train['remaining_from_primary']=train.gap_minutes-train.first_id.map(delays)
  report['matched_inference']=matched_stats(train)
  report['history_policy']=POLICY;report['history_coverage']={s:float((d.history_missing==0).mean()) for s,d in frames.items()}
  report['screen']={};method_scores={m:[] for m in ['none','sigmoid','isotonic']}
  for name in CONFIG['variants']:
   folds=[]
   for month in CONFIG['screen_months']:
    es=pd.Timestamp(2025,month,1);cs=es-pd.offsets.MonthBegin();ee=es+pd.offsets.MonthBegin();dates=pd.to_datetime(train.departure_date)
    a=cap(train[dates<cs-pd.Timedelta(days=2)],60000)
    b=cap(train[(dates>=cs+pd.Timedelta(days=2))&(dates<es-pd.Timedelta(days=2))],20000)
    c=cap(train[(dates>=es+pd.Timedelta(days=2))&(dates<ee-pd.Timedelta(days=2))],20000)
    sets=[set(v.first_id)|set(v.second_id) for v in [a,b,c]]
    assert all(not sets[i]&sets[j] for i in range(3) for j in range(i+1,3))
    model=fit(name,a,45);bp=predict(model,b,name,45);cp=predict(model,c,name,45)
    scores={}
    for method in method_scores:
     calibration=calibrate(method,bp,b.label_45.to_numpy());p=calibrated(calibration,cp)
     scores[method]=evaluate(c.label_45,p)['brier']
    folds.append(dict(month=month,train_n=len(a),cal_n=len(b),eval_n=len(c),calibration_brier=scores))
   report['screen'][name]=folds;dump(out/'results.json',report);print('rolling',name,flush=True)
  fitted={};val_predictions={};tr=cap(train,CONFIG['final_train_cap'])
  report['validation']={};report['calibration_methods']={};demo_probs=[]
  for t in [30,45,60]:
   predictions={};metrics={};models={}
   for name in CONFIG['variants']:
    model=fit(name,tr,t);p=predict(model,frames['validation'],name,t);models[name]=model;predictions[name]=p;metrics[name]=evaluate(frames['validation'][f'label_{t}'],p)
   winner=min(metrics,key=lambda n:metrics[n]['brier']);fitted[t]=models[winner]
   report['validation'][str(t)]=dict(selected=winner,metrics=metrics)
   # Primary-threshold rolling calibration method is fixed for all thresholds.
   scores={method:float(np.mean([v['calibration_brier'][method] for v in report['screen'][winner]])) for method in method_scores}
   method=min(scores,key=scores.get);cal=frames['calibration'];raw=predict(models[winner],cal,winner,t)
   calibrator=calibrate(method,raw,cal[f'label_{t}'].to_numpy())
   dp=calibrated(calibrator,predict(models[winner],frames['demo'],winner,t));demo_probs.append(dp)
   report['calibration_methods'][str(t)]=dict(selected=method,selection_primary_threshold=45,rolling_brier=scores)
   fitted[t]=dict(name=winner,model=models[winner],calibrator=calibrator)
   if t==45:val_predictions=predictions
   print('final',t,winner,method,flush=True)
  report['validation_differences']={f'{a}_minus_{b}':difference(frames['validation'],val_predictions[a],val_predictions[b]) for a,b in [('xgb_schedule','xgb_gap'),('xgb_history','xgb_schedule'),('logistic_history','logistic_schedule')]}
  matrix=np.maximum.accumulate(np.column_stack(demo_probs),axis=1)
  report['demo']={str(t):dict(**evaluate(frames['demo'][f'label_{t}'],matrix[:,i]),prediction_mean=float(matrix[:,i].mean())) for i,t in enumerate([30,45,60])}
  report['notes']=['Retrospective event-time experiment; publication and schedule snapshot availability not established','Rolling calibration selection uses primary threshold; sensitivity thresholds use same method choice rule','All development windows previously inspected; not independent confirmation','CDF baseline uses one incoming flight per sampled training frame; verify sampling sensitivity before final freeze','No airport causal effect claimed; matched inference limited to overlap cells']
  artifact=ROOT/'artifacts'/run;artifact.mkdir(parents=True,exist_ok=False)
  with (artifact/'models.pkl').open('wb') as stream:pickle.dump(fitted,stream)
  report['artifact_sha256']=sha256(artifact/'models.pkl');report['input_sha256']={s:sha256(ROOT/f'data/processed/connections_{s}.csv.gz') for s in frames}
  report['runtime_seconds']=time.perf_counter()-start;report['status']='complete';dump(out/'results.json',report)
 except BaseException as e:
  report['status']='failed';report['error']=repr(e);dump(out/'results.json',report);raise

if __name__=='__main__':main()
