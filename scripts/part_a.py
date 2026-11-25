"""Auditable, isolated part-A development pipeline. Never exports an app/model.

python scripts/part_a.py --stage data|models --run-id <unique-id>
"""
from pathlib import Path
import argparse, csv, io, json, sys, subprocess, platform, time
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import importlib.metadata
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src'),str(Path(__file__).resolve().parent)]
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from connection_score.safety import raw_archive, read_development, sha256, validate_config, assert_date
from connection_score.pipeline import flight_id, normalize, build
from train_models import features, FEATURES, evaluate, policy_report
ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'configs/part_a.json').read_text())


def dump(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def provenance(out, stage, started):
    paths=[p for folder in ('scripts','src','configs') for p in (ROOT/folder).rglob('*') if p.suffix in ('.py','.json') and '__pycache__' not in str(p)]
    return dict(run_id=out.name,stage=stage,commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        started_at_utc=started,completed_at_utc=datetime.now(timezone.utc).isoformat(),
        command=f'.venv/bin/python scripts/part_a.py --stage {stage} --run-id {out.name}',
        configuration=CONFIG,source_sha256={str(p.relative_to(ROOT)):sha256(p) for p in paths},
        input_manifest_sha256=sha256(ROOT/'data/manifest.json'),
        processed_sha256={s:sha256(ROOT/f'data/processed/connections_{s}.csv.gz') for s in ('train','validation','calibration','demo')},
        versions={'python':platform.python_version(),**{x:importlib.metadata.version(x) for x in ('numpy','pandas','scipy','scikit-learn','matplotlib','xgboost')}},
        test_accessed=False,app_changed=False)


def savefig(out,name,title,ax):
    # Bidi shaping is used when installed; no manual string reversal of mixed text.
    try:
        from bidi.algorithm import get_display
        ax.set_title(get_display(title),fontsize=13)
        for axis in (ax.xaxis,ax.yaxis):
            axis.label.set_text(get_display(axis.label.get_text()))
    except ImportError:
        ax.set_title(title)
    ax.figure.text(.01,.005,f'run={out.name} | commit={subprocess.check_output(["git","rev-parse","--short","HEAD"],cwd=ROOT,text=True).strip()} | development only',fontsize=7)
    ax.figure.tight_layout(rect=(0,.03,1,1))
    path=out/'figures'/f'{name}.png';path.parent.mkdir(exist_ok=True)
    ax.figure.savefig(path,dpi=180);plt.close(ax.figure)


def daily_contrast(frame, a, b, name):
    first=frame.loc[a,['departure_date','label_45']].groupby('departure_date').label_45.agg(['sum','count'])
    second=frame.loc[b,['departure_date','label_45']].groupby('departure_date').label_45.agg(['sum','count'])
    blocks=pd.concat({'a':first,'b':second},axis=1).fillna(0)
    totals=blocks.sum();ra=totals[('a','sum')]/totals[('a','count')];rb=totals[('b','sum')]/totals[('b','count')]
    rng=np.random.default_rng(CONFIG['seed']);values=[]
    data=blocks.to_numpy();cols=list(blocks.columns)
    for _ in range(CONFIG['bootstrap_days']):
        v=data[rng.integers(0,len(data),len(data))].sum(axis=0)
        ca,cb=v[cols.index(('a','count'))],v[cols.index(('b','count'))]
        if ca and cb:values.append(v[cols.index(('b','sum'))]/cb-v[cols.index(('a','sum'))]/ca)
    return dict(name=name,rate_a=float(ra),rate_b=float(rb),difference_b_minus_a=float(rb-ra),interval_95=np.quantile(values,[.025,.975]).tolist(),n_a=int(totals[('a','count')]),n_b=int(totals[('b','count')]),days=len(blocks),bootstrap_valid=len(values),method='paired resampling of complete calendar days; exploratory')


def data_stage(out):
    started=datetime.now(timezone.utc).isoformat();clock=time.perf_counter()
    config=json.loads((ROOT/'configs/research.json').read_text());validate_config(config)
    # Rebuild separately: preserve all existing data, reports, app and model bundles.
    rebuild=ROOT/'artifacts'/out.name/'rebuild'
    rebuilt=build(rebuild)
    original=json.loads((ROOT/'reports/connections.json').read_text())
    matching={s:rebuilt['splits'][s]['sha256']==original['splits'][s]['sha256'] for s in rebuilt['splits']}
    dump(out/'rebuild.json',dict(output=str(rebuild.relative_to(ROOT)),split_hashes_match=matching,report=rebuilt))
    if not all(matching.values()):raise ValueError('Rebuild differs; do not silently use stale processed data')
    frames={s:read_development(ROOT/f'data/processed/connections_{s}.csv.gz',dtype={c:'category' for c in ['origin','hub','destination','carrier','status']}) for s in ('train','validation','calibration','demo')}
    allpairs=pd.concat([d.assign(split=s) for s,d in frames.items()],ignore_index=True)
    allpairs['flight_month']=allpairs.departure_date.str[:7]
    first_ids=set(allpairs.first_id);needed_ids=first_ids|set(allpairs.second_id)
    metadata={};raw_counts=[];raw_missing=Counter();schema=None
    zones=pd.read_csv(ROOT/'data/raw/airport_timezones.csv',usecols=['iata','tz']).dropna().groupby('iata').tz.agg(lambda x: x.iloc[0] if x.nunique()==1 else None).dropna().to_dict()
    raw_n=0;raw_status=Counter();raw_min=None;raw_max=None
    selected=['FlightDate','Reporting_Airline','Flight_Number_Reporting_Airline','Origin','Dest','CRSDepTime','CRSArrTime','CRSElapsedTime','ArrDelay','ArrTime','DepDelay','DepTime','Tail_Number','Cancelled','Diverted']
    for month in range(1,11):
        c=Counter()
        with raw_archive(ROOT/f'data/raw/bts_2025_{month:02d}.zip') as archive:
            member=next(n for n in archive.namelist() if n.lower().endswith('.csv'))
            with archive.open(member) as stream:
                reader=csv.DictReader(io.TextIOWrapper(stream,encoding='utf-8-sig'))
                header=[k for k in reader.fieldnames if k and k.strip()]
                if schema is None:schema=header
                if header!=schema:raise ValueError('Raw schema drift')
                for row in reader:
                    assert_date(row['FlightDate']);c['rows']+=1
                    day=row['FlightDate'];raw_min=day if raw_min is None else min(raw_min,day);raw_max=day if raw_max is None else max(raw_max,day)
                    cancelled=float(row['Cancelled'])==1;diverted=float(row['Diverted'])==1
                    c['cancelled']+=cancelled;c['diverted']+=diverted
                    for col in selected:raw_missing[col]+=not bool(row[col].strip())
                    if not ({row['Origin'],row['Dest']} & set(config['hubs'])):continue
                    c['hub_rows']+=1
                    fid=flight_id(row)
                    if fid not in needed_ids:continue
                    hour=None
                    if fid in first_ids:
                        f=normalize(row,zones)
                        hour=f['arr'].astimezone(ZoneInfo(zones[row['Dest']])).hour
                    value=(float(row['ArrDelay']) if row['ArrDelay'] else None,float(row['DepDelay']) if row['DepDelay'] else None,row['Tail_Number'] or None,hour)
                    if fid in metadata and metadata[fid]!=value:raise ValueError('Conflicting duplicate flight')
                    metadata[fid]=value
        raw_counts.append(dict(month=month,**c));raw_n+=c['rows'];raw_status.update(c)
        print('profile raw',month,c['rows'],flush=True)
    assert needed_ids<=metadata.keys(),'Pair flight missing from raw provenance'
    feasibility=dict(raw_rows=raw_n,raw_columns=len(schema),raw_schema=schema,raw_coverage=[raw_min,raw_max],raw_by_month=raw_counts,
        raw_selected_column_missing={k:dict(missing=int(v),denominator=raw_n,rate=v/raw_n) for k,v in raw_missing.items()},
        raw_cancellation_rate=raw_status['cancelled']/raw_n,raw_diversion_rate=raw_status['diverted']/raw_n,
        feature_count=len(FEATURES),feature_columns=FEATURES,processed_columns=len(frames['train'].columns),pairs=len(allpairs),unique_flights_in_pairs=len(needed_ids),
        pair_date_coverage=[allpairs.departure_date.min(),allpairs.departure_date.max()],splits={},
        by_hub=allpairs.groupby('hub',observed=True).size().to_dict(),by_carrier=allpairs.groupby('carrier',observed=True).size().to_dict(),by_month=allpairs.groupby('flight_month',observed=True).size().to_dict(),
        processed_missing={k:dict(missing=int(v),denominator=len(allpairs),rate=float(v/len(allpairs))) for k,v in allpairs.isna().sum().items()},
        semantics='Raw rows are source flight records, not claimed deduplicated flights; unique flight counts and filtered flights reported separately. Missing raw rates cover selected audit fields, not every raw column.')
    for s,d in frames.items():
        known=d[d.status=='operated'];ids=set(d.first_id)|set(d.second_id)
        feasibility['splits'][s]=dict(pairs=len(d),unique_flights_in_pairs=len(ids),days=d.departure_date.nunique(),coverage=[d.departure_date.min(),d.departure_date.max()],statuses=d.status.value_counts().to_dict(),operated=len(known),failure_rates={str(t):float(known[f'label_{t}'].mean()) for t in (30,45,60)})
    dump(out/'feasibility.json',feasibility)
    # Enrichment is isolated and is ONLY for outcome/diagnostic analysis.
    train=frames['train'].copy()
    train['first_arrival_delay']=train.first_id.map(lambda x:metadata[x][0])
    train['second_departure_delay']=train.second_id.map(lambda x:metadata[x][1])
    train['hub_arrival_hour']=train.first_id.map(lambda x:metadata[x][3])
    train['same_tail']=pd.array([metadata[a][2]==metadata[b][2] if metadata[a][2] and metadata[b][2] else None for a,b in zip(train.first_id,train.second_id)],dtype='boolean')
    train['remaining_actual']=train.gap_minutes+train.second_departure_delay-train.first_arrival_delay
    operated=train[train.status=='operated'].copy()
    if operated.first_arrival_delay.isna().any():raise ValueError('Missing primary outcome input')
    derived=(operated.gap_minutes-operated.first_arrival_delay<45).astype(int)
    if not np.array_equal(derived,operated.label_45.astype(int)):raise ValueError('Primary label reconstruction failed')
    # Every original pair and flight remains in its chronological split.
    ids={s:set(d.first_id)|set(d.second_id) for s,d in frames.items()}
    for i,s in enumerate(ids):
        for other in list(ids)[i+1:]:assert not ids[s]&ids[other]
    # One record per incoming flight prevents high-degree flights dominating rank tests.
    incoming=operated.drop_duplicates('first_id').copy()
    daily=incoming.groupby('departure_date').agg(gap=('gap_minutes','mean'),delay=('first_arrival_delay','mean'))
    rho=stats.spearmanr(daily.gap,daily.delay)
    band=operated[operated.gap_minutes.between(*CONFIG['gap_band_minutes'])].copy()
    tests=[]
    # Test daily failure proportions, rather than treating dependent pairs as independent.
    hub_daily=band.groupby(['departure_date','hub'],observed=True).label_45.mean().unstack()
    arrays=[hub_daily[h].dropna().to_numpy() for h in ['ATL','ORD','DFW']]
    kw=stats.kruskal(*arrays)
    tests.append(dict(name='hub daily failure rates; gap 60–120',test='Kruskal-Wallis',statistic=float(kw.statistic),p=float(kw.pvalue),caveat='Same-day hub series may share system-wide shocks; rank-test p is exploratory. Day-block effect interval is primary.'))
    atl=band[band.hub=='ATL'];morning=atl.hub_arrival_hour.between(6,11);evening=atl.hub_arrival_hour.between(18,23)
    am=atl[morning].groupby('departure_date').label_45.mean();pm=atl[evening].groupby('departure_date').label_45.mean()
    mw=stats.mannwhitneyu(am,pm,alternative='two-sided')
    tests.append(dict(name='ATL morning vs evening daily failure rates',test='Mann-Whitney U',statistic=float(mw.statistic),p=float(mw.pvalue),caveat='Overlapping dates imply pairing; rank test is supplementary, not independent-sample proof.'))
    common=am.index.intersection(pm.index);w=stats.wilcoxon(am.loc[common],pm.loc[common])
    tests.append(dict(name='ATL matched days morning vs evening',test='Wilcoxon signed-rank',statistic=float(w.statistic),p=float(w.pvalue),caveat='Daily differences may be asymmetric and serially dependent; exploratory.'))
    # Holm adjustment for the displayed family, not a claim of preregistration.
    order=np.argsort([t['p'] for t in tests]);running=0
    for rank,i in enumerate(order):
        running=max(running,min(1.,(len(tests)-rank)*tests[i]['p']));tests[i]['holm_p']=running
    comparisons=[daily_contrast(band,band.hub=='ATL',band.hub=='ORD','ORD minus ATL, gap 60–120'),daily_contrast(atl,morning,evening,'ATL evening minus morning by hub scheduled arrival hour, gap 60–120')]
    # Narrower bands expose remaining gap-composition differences; no causal adjustment claim.
    stratified=[]
    for lo,hi in [(60,74),(75,89),(90,104),(105,120)]:
        part=band[band.gap_minutes.between(lo,hi)]
        stratified.append(dict(gap_band=[lo,hi],**daily_contrast(part,part.hub=='ATL',part.hub=='ORD',f'ORD minus ATL {lo}–{hi}')))
    actual=operated.dropna(subset=['remaining_actual'])
    alt={str(t):dict(denominator=len(actual),primary_rate=float(actual[f'label_{t}'].mean()),actual_departure_rate=float((actual.remaining_actual<t).mean()),disagreement_rate=float(((actual.remaining_actual<t).astype(int)!=actual[f'label_{t}']).mean())) for t in (30,45,60)}
    tails={str(v):dict(pairs=len(g),primary_failure_rate=float(g.label_45.mean()),actual_departure_failure_rate=float((g.dropna(subset=['remaining_actual']).remaining_actual<45).mean())) for v,g in operated[operated.same_tail.notna()].groupby('same_tail',observed=True)}
    def group_rates(key):
        return operated.groupby(key,observed=True).label_45.agg(['size','mean']).reset_index().to_dict('records')
    rates={k:group_rates(k) for k in ('hub','carrier','month','weekday','hub_arrival_hour')}
    operated['gap_band']=pd.cut(operated.gap_minutes,[29,59,89,119,149,179,209,240],labels=['30–59','60–89','90–119','120–149','150–179','180–209','210–240'])
    rates['gap_band']=group_rates('gap_band')
    numeric=operated[['gap_minutes','duration_minutes','first_arrival_delay','hub_arrival_hour','label_45']].corr(method='spearman')
    analysis=dict(population='train operated pairs only; exploratory retrospective',training_pairs=len(train),operated_pairs=len(operated),unique_incoming=len(incoming),
        quantiles={c:{str(k):float(v) for k,v in operated[c].quantile([0,.01,.25,.5,.75,.95,.99,1]).items()} for c in ('gap_minutes','first_arrival_delay')},
        rank_tests=tests,daily_spearman=dict(rho=float(rho.statistic),p_naive=float(rho.pvalue),days=len(daily),unit='daily mean of one retained candidate per incoming flight; exploratory; not individual-level relation'),
        comparisons=comparisons,narrow_gap_comparisons=stratified,group_rates=rates,actual_departure_sensitivity=alt,same_tail=tails,same_tail_missing_pairs=int(operated.same_tail.isna().sum()),
        primary_label_reconstruction_matches=True,split_flight_overlap=0,correlations=numeric.to_dict(),
        limitations=['FlightDate is the incoming local departure day; an overnight pair may span calendar days. Daily bootstrap is approximate and does not remove serial or multi-day dependence.',
        'All pairs for a sampled incoming flight are retained: pairs are not independent observations.',
        'Gap bands do not control route, carrier and exact gap composition completely.',
        'Tail identity and actual departure are diagnostics/alternative outcomes only; never model features.',
        'Same-tail pairs are filtered by existing different-flight-number rule and are not all aircraft rotations.',
        'Delay distribution is pair-weighted; rank correlation uses daily aggregated unique incoming flights.',
        'No causal interpretation, no passenger-level missed-connection outcome, no independently held-out TEST.'])
    dump(out/'analysis.json',analysis)
    ax=pd.Series(feasibility['by_month']).plot.bar(figsize=(9,4),color='#147d92');ax.set_ylabel('מספר זוגות');savefig(out,'pairs_by_month','זוגות חיבור לפי חודש — נתוני פיתוח',ax)
    rates_by_t={str(t):float(allpairs.loc[allpairs.status=='operated',f'label_{t}'].mean()) for t in (30,45,60)}
    feasibility['all_development_failure_rates']=rates_by_t;dump(out/'feasibility.json',feasibility)
    ax=pd.Series({k:100*v for k,v in rates_by_t.items()}).plot.bar(figsize=(7,4),color='#147d92',rot=0);ax.set_xlabel('סף מעבר בדקות');ax.set_ylabel('אחוז אי־עמידה');savefig(out,'failure_sensitivity','אי־עמידה לפי סף — רק זוגות עם תווית תקינה',ax)
    hour=operated.groupby(['hub_arrival_hour','hub'],observed=True).label_45.mean().unstack()*100
    ax=hour.plot(figsize=(9,4));ax.set_xlabel('שעת הגעה מתוכננת לשדה המעבר');ax.set_ylabel('אחוז אי־עמידה');savefig(out,'hour_hub','קשר בין שעת הגעה ושדה לסיכון — אימון בלבד',ax)
    fig,ax=plt.subplots(figsize=(8,4));ax.hist(operated.first_arrival_delay,bins=np.arange(-60,301,10),color='#147d92');ax.set_xlabel('איחור הגעה בדקות');ax.set_ylabel('מספר זוגות');savefig(out,'arrival_delay','התפלגות איחור — תצוגה מוגבלת, הזנב נשמר בנתונים',ax)
    fig,ax=plt.subplots(figsize=(6,5));im=ax.imshow(numeric,vmin=-1,vmax=1,cmap='RdBu_r');ax.set_xticks(range(len(numeric)),numeric.columns,rotation=80,fontsize=8);ax.set_yticks(range(len(numeric)),numeric.columns,fontsize=8);fig.colorbar(im,ax=ax);savefig(out,'correlation','מתאמי ספירמן — תיאור בלבד, כולל משתני תוצאה',ax)
    fig,ax=plt.subplots(figsize=(8,5))
    for i,c in enumerate(comparisons):
        a,b=c['interval_95'];d=c['difference_b_minus_a'];ax.errorbar(d*100,i,xerr=[[100*(d-a)],[100*(b-d)]],fmt='o',color='#147d92')
    ax.axvline(0,color='gray',linestyle='--');ax.set_yticks([0,1],['ORD − ATL','ATL evening − morning']);ax.set_xlabel('הפרש בנקודות אחוז ורווח סמך');savefig(out,'daily_effects','הבדלים בתוך מרווח קבוע — דגימת ימים שלמים',ax)
    # Small real examples, not outcome-selected, with no invented flight times.
    train.head(5).to_csv(out/'input_examples.csv',index=False)
    meta=provenance(out,'data',started);meta['runtime_seconds']=time.perf_counter()-clock;meta['rebuild_hashes_match']=matching
    dump(out/'run.json',meta)
    print(json.dumps({'run':out.name,'raw_rows':raw_n,'pairs':len(allpairs),'seconds':meta['runtime_seconds']},ensure_ascii=False),flush=True)


def models_stage(out):
    from model_search import fit_predict,raw_predict,calibrate,calibrated
    from sklearn.calibration import calibration_curve
    import pickle
    started=datetime.now(timezone.utc).isoformat();clock=time.perf_counter()
    frames={s:read_development(ROOT/f'data/processed/connections_{s}.csv.gz',dtype={c:'category' for c in ['origin','hub','destination','carrier','status']}) for s in ('train','validation','calibration','demo')}
    ids={s:set(d.first_id)|set(d.second_id) for s,d in frames.items()}
    for i,s in enumerate(ids):
        for other in list(ids)[i+1:]:assert not ids[s]&ids[other]
    full_demo=frames['demo'].copy()
    frames={s:d[d.status=='operated'].copy() for s,d in frames.items()}
    tr=frames['train'];dates=pd.to_datetime(tr.departure_date)
    report=dict(status='running',population='Retrospective development only; candidate list and windows known from earlier work',screen={},failures=[],validation={},calibration={},demo={},test_accessed=False)
    for name in CONFIG['model_candidates']:
        folds=[]
        for month in CONFIG['screen_months']:
            start=pd.Timestamp(2025,month,1);end=start+pd.offsets.MonthBegin()
            a=tr[dates<start-pd.Timedelta(days=2)];b=tr[(dates>=start+pd.Timedelta(days=2))&(dates<end-pd.Timedelta(days=2))]
            assert not (set(a.first_id)|set(a.second_id))&(set(b.first_id)|set(b.second_id))
            a=a.sample(n=min(len(a),CONFIG['screen_train_cap']),random_state=CONFIG['seed']).sort_index();b=b.sample(n=min(len(b),CONFIG['screen_eval_cap']),random_state=CONFIG['seed']).sort_index()
            try:
                _,p=fit_predict(name,a,b,'label_45');folds.append(dict(month=month,train_n=len(a),eval_n=len(b),**evaluate(b.label_45,p)))
            except Exception as exc:
                report['failures'].append(dict(model=name,month=month,error=repr(exc)))
        report['screen'][name]=dict(folds=folds,mean_brier=float(np.mean([f['brier'] for f in folds])) if len(folds)==len(CONFIG['screen_months']) else None)
        dump(out/'models.json',report);print('screen',name,report['screen'][name]['mean_brier'],flush=True)
    eligible={k:v for k,v in report['screen'].items() if v['mean_brier'] is not None}
    winner=min(eligible,key=lambda k:eligible[k]['mean_brier'])
    names=list(dict.fromkeys(['constant','gap_empirical','logistic_c05',winner]))
    training=tr.sample(n=min(len(tr),CONFIG['final_train_cap']),random_state=CONFIG['seed']).sort_index()
    bundles={};predictions=[]
    for threshold in (30,45,60):
        target=f'label_{threshold}';val=frames['validation'];candidate_models={};metrics={}
        for name in names:
            m,p=fit_predict(name,training,val,target);candidate_models[name]=m;metrics[name]=evaluate(val[target],p)
        selected=min(metrics,key=lambda k:metrics[k]['brier']);model=candidate_models[selected]
        report['validation'][str(threshold)]=dict(metrics=metrics,selected=selected,train_n=len(training),validation_n=len(val))
        cal=frames['calibration'];raw=raw_predict(selected,model,training,cal,target)
        fit=cal.departure_date<'2025-10-08';hold=cal.departure_date>='2025-10-10'
        methods={};scores={}
        for method in ['none','sigmoid','isotonic','prior_offset','temperature']:
            try:
                fitted=calibrate(method,raw[fit],cal.loc[fit,target].to_numpy());pred=calibrated(fitted,raw[hold]);scores[method]=evaluate(cal.loc[hold,target],pred);methods[method]=fitted
            except Exception as exc:report['failures'].append(dict(stage='calibration',threshold=threshold,method=method,error=repr(exc)))
        method=min(scores,key=lambda k:scores[k]['brier']);calibrator=calibrate(method,raw,cal[target].to_numpy())
        report['calibration'][str(threshold)]=dict(selected=method,holdout_metrics=scores,fit_n=int(fit.sum()),eval_n=int(hold.sum()))
        dp=calibrated(calibrator,raw_predict(selected,model,training,full_demo,target));predictions.append(dp)
        bundles[threshold]=dict(name=selected,model=model,calibrator=calibrator,training_prevalence=float(training[target].mean()))
        print('final',threshold,selected,'calibration',method,flush=True)
    matrix=np.maximum.accumulate(np.column_stack(predictions),axis=1)
    report['monotone_projection_changed_rows']=int(np.any(np.abs(matrix-np.column_stack(predictions))>1e-12,axis=1).sum())
    for i,t in enumerate((30,45,60)):
        full_demo[f'risk_{t}']=matrix[:,i];mask=full_demo.status=='operated'
        report['demo'][str(t)]=evaluate(full_demo.loc[mask,f'label_{t}'],matrix[mask,i])
    report['decision_experiment']=policy_report(full_demo)
    report['screen_primary_winner']=winner;report['status']='complete';report['limitations']=['Repeated development data, not independent confirmation','Observed BTS schedules are not booking-time snapshots','Calibration choice uses a short known October development window','Demo already seen; never a final test result','Candidate sets synthetic and sampled; same-carrier is not proof of ticket validity']
    artifact=ROOT/'artifacts'/out.name;artifact.mkdir(parents=True,exist_ok=True)
    with (artifact/'models.pkl').open('wb') as f:pickle.dump(bundles,f)
    report['artifact_sha256']=sha256(artifact/'models.pkl');dump(out/'models.json',report)
    mask=full_demo.status=='operated';p=matrix[mask,1];y=full_demo.loc[mask,'label_45']
    observed,predicted=calibration_curve(y,p,n_bins=10,strategy='quantile')
    fig,ax=plt.subplots(figsize=(6,5));ax.plot([0,1],[0,1],'--',color='gray');ax.plot(predicted,observed,'o-',color='#147d92');ax.set_xlabel('הסתברות חזויה');ax.set_ylabel('שיעור נצפה');savefig(out,'calibration','אבחון כיול — הדגמת פיתוח מוכרת בלבד',ax)
    scores=report['validation']['45']['metrics'];ax=pd.Series({k:v['brier'] for k,v in scores.items()}).plot.barh(figsize=(8,4),color='#147d92');ax.set_xlabel('Brier — נמוך עדיף');savefig(out,'model_comparison','השוואת מודלים — ולידציה בספטמבר',ax)
    meta=provenance(out,'models',started);meta['runtime_seconds']=time.perf_counter()-clock;dump(out/'run.json',meta)
    print('models completed',meta['runtime_seconds'],flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['data','models'],required=True);parser.add_argument('--run-id',required=True);args=parser.parse_args()
    if not args.run_id.replace('-','').replace('_','').isalnum():raise ValueError('Invalid run id')
    out=ROOT/'reports/runs'/args.run_id
    out.mkdir(parents=True,exist_ok=False)
    try:
        (data_stage if args.stage=='data' else models_stage)(out)
    except BaseException as exc:
        dump(out/'failure.json',dict(error=repr(exc),commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),test_accessed=False));raise

if __name__=='__main__':main()
