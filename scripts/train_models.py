"""Develop on train/validation/calibration only. No test reader exists here."""
from pathlib import Path
import hashlib
import json
import pickle
import platform
import sys
import warnings
import numpy as np
import pandas as pd
import sklearn
from scipy.special import expit, logit
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score, average_precision_score, log_loss
from sklearn.exceptions import ConvergenceWarning

ROOT=Path(__file__).resolve().parents[1]
CATEGORICAL=['origin','hub','destination','carrier']
NUMERIC=['gap_minutes','duration_minutes','hour_sin','hour_cos','week_sin','week_cos','year_sin','year_cos']
FEATURES=CATEGORICAL+NUMERIC


def features(df):
    x=df[CATEGORICAL+['gap_minutes','duration_minutes']].copy()
    for name,col,period in [('hour','departure_hour',24),('week','weekday',7),('year','month',12)]:
        x[name+'_sin']=np.sin(2*np.pi*df[col]/period)
        x[name+'_cos']=np.cos(2*np.pi*df[col]/period)
    assert not any('label' in c or 'status' in c or c.endswith('_id') for c in x.columns)
    return x[FEATURES]


def evaluate(y,p):
    bins=[]
    for low in np.arange(0,1,.1):
        m=(p>=low)&(p<low+.1 if low<.9 else p<=1)
        if m.any():bins.append(dict(lower=round(float(low),1),n=int(m.sum()),predicted=float(p[m].mean()),observed=float(np.asarray(y)[m].mean())))
    return dict(n=len(y),prevalence=float(np.mean(y)),brier=float(brier_score_loss(y,p)),log_loss=float(log_loss(y,p,labels=[0,1])),roc_auc=float(roc_auc_score(y,p)) if len(set(y))>1 else None,average_precision=float(average_precision_score(y,p)),calibration_bins=bins)


def gap_fit(df,target):
    tmp=df.assign(bin=(df.gap_minutes//15).astype(int))
    rate=tmp.groupby('bin')[target].agg(['sum','count'])
    return {int(k):float((r['sum']+1)/(r['count']+2)) for k,r in rate.iterrows()}


def gap_predict(df,rates,default):
    return np.array([rates.get(int(x//15),default) for x in df.gap_minutes])


def clustered_difference(df):
    """Exploratory weekly block bootstrap: association, not a causal effect."""
    d=df[(df.hub.isin(['ATL','ORD'])) & df.gap_minutes.between(60,120)].copy()
    d['week']=(pd.to_datetime(d.departure_date)-pd.Timestamp('2025-01-01')).dt.days//7
    sums=d.groupby(['week','hub'],observed=True).label_45.agg(['sum','count']).unstack('hub').fillna(0)
    rng=np.random.default_rng(42)
    values=[]
    for _ in range(1000):
        sample=sums.iloc[rng.integers(0,len(sums),len(sums))].sum()
        values.append(float(sample[('sum','ORD')]/sample[('count','ORD')]-sample[('sum','ATL')]/sample[('count','ATL')]))
    rates=d.groupby('hub',observed=True).label_45.mean()
    return dict(description='ORD minus ATL, scheduled gap 60–120 minutes; training data only; exploratory association',rows=len(d),weeks=len(sums),difference=float(rates['ORD']-rates['ATL']),interval_95=[float(x) for x in np.quantile(values,[.025,.975])],method='1000 weekly block bootstrap resamples, seed 42',limitations='Not causal; route/carrier mixes differ; weekly blocks approximate flight dependence; no multiple-testing claim.')


def policy_report(demo):
    results={k:[] for k in ['shortest','longest_gap','lowest_risk']}
    groupcols=['departure_date','origin','destination']
    groups=0
    for _,g in demo.groupby(groupcols,sort=True,observed=True):
        if len(g)<2:continue
        candidates=g[g.duration_minutes <= g.duration_minutes.min()+60]
        if len(candidates)<2:continue
        groups+=1
        ordered=candidates.sort_values(['duration_minutes','first_id','second_id'])
        choices={'shortest':ordered.iloc[0],'longest_gap':ordered.sort_values('gap_minutes',ascending=False,kind='stable').iloc[0],'lowest_risk':ordered.sort_values('risk_45',kind='stable').iloc[0]}
        for name,row in choices.items():results[name].append(row)
    output={}
    for name,rows in results.items():
        if not rows:continue
        chosen=pd.DataFrame(rows)
        known=chosen[chosen.status=='operated']
        output[name]=dict(choices=len(chosen),known_margin_outcomes=len(known),margin_failure_rate=float(known.label_45.mean()) if len(known) else None,mean_duration_minutes=float(chosen.duration_minutes.mean()),statuses=chosen.status.value_counts().to_dict())
    left=pd.DataFrame(results['lowest_risk']).reset_index(drop=True)
    right=pd.DataFrame(results['longest_gap']).reset_index(drop=True)
    mask=(left.status=='operated')&(right.status=='operated')
    paired=pd.DataFrame({'day':left.loc[mask,'departure_date'],'difference':left.loc[mask,'label_45']-right.loc[mask,'label_45']})
    blocks=paired.groupby('day').difference.agg(['sum','count'])
    rng=np.random.default_rng(42)
    differences=[]
    for _ in range(1000):
        totals=blocks.iloc[rng.integers(0,len(blocks),len(blocks))].sum()
        differences.append(float(totals['sum']/totals['count']))
    paired_result=dict(common_known_groups=len(paired),difference_lowest_risk_minus_longest_gap=float(paired.difference.mean()),interval_95=[float(x) for x in np.quantile(differences,[.025,.975])],method='Exploratory paired calendar-day block bootstrap; few demo days and cross-day dependence limit precision.')
    return dict(groups=groups,max_extra_duration_minutes=60,policies=output,paired=paired_result,scope='Exploratory demo period only, restricted to sampled synthetic candidate sets; not a test result or a commercial itinerary experiment.')


def main():
    warnings.simplefilter('error',ConvergenceWarning)
    frames={s:pd.read_csv(ROOT/f'data/processed/connections_{s}.csv.gz',dtype={c:'category' for c in CATEGORICAL+['status']}) for s in ('train','validation','calibration','demo')}
    ids={s:set(df.first_id)|set(df.second_id) for s,df in frames.items()}
    for i,a in enumerate(ids):
        for b in list(ids)[i+1:]:assert not ids[a]&ids[b],f'Flight overlap: {a}/{b}'
    operated={s:d[d.status=='operated'].copy() for s,d in frames.items()}
    # Outcome-independent cap keeps a complete rebuild practical on a laptop.
    full_training_count=len(operated['train'])
    if full_training_count>300000:
        operated['train']=operated['train'].sample(n=300000,random_state=42).sort_index()
    xs={s:features(d) for s,d in operated.items()}
    demo_x=features(frames['demo'])
    report={'test_status':'LOCKED — not downloaded, parsed, scored or used for decisions','validation':{},'demo':{},'selected':{},'features':FEATURES,'training_operated_pairs':full_training_count,'training_fit_sample':len(operated['train']),'versions':dict(python=platform.python_version(),sklearn=sklearn.__version__,numpy=np.__version__,pandas=pd.__version__),'split_flight_overlap':0}
    bundles={}
    projections=[]
    for t in (30,45,60):
        label=f'label_{t}'
        train=operated['train'];val=operated['validation'];cal=operated['calibration']
        model=make_pipeline(ColumnTransformer([('cat',OneHotEncoder(handle_unknown='ignore'),CATEGORICAL),('num',StandardScaler(),NUMERIC)]),LogisticRegression(max_iter=1000,C=.5,solver='lbfgs',random_state=42))
        model.fit(xs['train'],train[label])
        default=float(train[label].mean())
        rates=gap_fit(train,label)
        p=model.predict_proba(xs['validation'])[:,1]
        gp=gap_predict(val,rates,default)
        metrics={'constant_train_rate':evaluate(val[label],np.full(len(val),default)),'gap_empirical':evaluate(val[label],gp),'logistic':evaluate(val[label],p)}
        selected=min(metrics,key=lambda k:metrics[k]['brier'])
        report['validation'][str(t)]=metrics
        report['selected'][str(t)]=selected
        def raw_predict(df,x):
            if selected=='logistic':return model.predict_proba(x)[:,1]
            if selected=='gap_empirical':return gap_predict(df,rates,default)
            return np.full(len(df),default)
        calraw=raw_predict(cal,xs['calibration'])
        calibrator=LogisticRegression(C=1e6,solver='lbfgs',max_iter=1000)
        calibrator.fit(logit(np.clip(calraw,1e-6,1-1e-6)).reshape(-1,1),cal[label])
        # Positive slope preserves risk ordering. A failure is reported, not hidden.
        assert calibrator.coef_[0,0] > 0,'Calibration reversed risk ordering'
        raw=raw_predict(frames['demo'],demo_x)
        calibrated=calibrator.predict_proba(logit(np.clip(raw,1e-6,1-1e-6)).reshape(-1,1))[:,1]
        projections.append(calibrated)
        bundles[t]=dict(model=model,gap_rates=rates,default=default,selected=selected,calibrator=calibrator)
        print('threshold',t,'selected',selected,'validation_brier',metrics[selected]['brier'],flush=True)
    # The events are nested. Fixed monotone projection prevents contradictory risks.
    predictions=np.maximum.accumulate(np.column_stack(projections),axis=1)
    report['monotone_projection_changed_rows']=int((np.abs(predictions-np.column_stack(projections))>1e-12).any(axis=1).sum())
    for i,t in enumerate((30,45,60)):
        frames['demo'][f'risk_{t}']=predictions[:,i]
        mask=frames['demo'].status=='operated'
        report['demo'][str(t)]=evaluate(frames['demo'].loc[mask,f'label_{t}'],predictions[mask,i])
    demo_mask=frames['demo'].status=='operated'
    report['calibration_diagnostic_45']=dict(predicted_mean=float(predictions[demo_mask,1].mean()),observed_mean=float(frames['demo'].loc[demo_mask,'label_45'].mean()),status='Underestimation on development demo; operational calibration not established. Do not recalibrate using demo or test.')
    report['inference']=clustered_difference(operated['train'])
    report['decision_experiment']=policy_report(frames['demo'])
    (ROOT/'artifacts').mkdir(exist_ok=True)
    with (ROOT/'artifacts/model_bundle.pkl').open('wb') as f:pickle.dump(bundles,f)
    report['model_sha256']=hashlib.file_digest((ROOT/'artifacts/model_bundle.pkl').open('rb'),'sha256').hexdigest()
    (ROOT/'reports/models.json').write_text(json.dumps(report,indent=2)+'\n')
    # Publish all demo candidates so UI filters never fabricate alternatives.
    records=[]
    group_keys=['departure_date','origin','destination']
    # Keep complete candidate groups; choose only by candidate count, never outcome.
    chosen_groups=frames['demo'].groupby(group_keys,observed=True).size().sort_values(ascending=False,kind='stable').head(120).index
    app_mask=pd.MultiIndex.from_frame(frames['demo'][group_keys]).isin(chosen_groups)
    app_frame=frames['demo'].loc[app_mask]
    report['app_coverage']=dict(groups=len(chosen_groups),candidates=len(app_frame),selection='120 candidate groups with most sampled alternatives; selected without outcomes')
    (ROOT/'reports/models.json').write_text(json.dumps(report,indent=2)+'\n')
    for r in app_frame.to_dict('records'):
        for t in (30,45,60):
            r[f'label_{t}']=None if pd.isna(r[f'label_{t}']) else int(r[f'label_{t}'])
            r[f'risk_{t}']=round(float(r[f'risk_{t}']),6)
        records.append(r)
    public=dict(summary=report,connections=json.loads((ROOT/'reports/connections.json').read_text()),candidates=records)
    (ROOT/'app/research.json').write_text(json.dumps(public,separators=(',',':'),allow_nan=False))
    lines=['# מודל בסיס ומצב המחקר','', '**TEST נשאר סגור: נובמבר–דצמבר 2025 לא הורדו ולא נקראו.**','', '## חלוקת זמן','', '- אימון: ינואר–אוגוסט 2025.','- ולידציה ובחירת מודל: ספטמבר.','- כיול: תחילת אוקטובר.','- הדגמה ובדיקה התפתחותית: סוף אוקטובר.','- מרווח הפרדה של יומיים מכל צד של גבול; אין טיסות משותפות.','', '## תוצאות ולידציה לפני כיול','', '| סף דקות | קבוע | מרווח בלבד | לוגיסטית | נבחר לפי Brier |','|---|---:|---:|---:|---|']
    for t in (30,45,60):
        m=report['validation'][str(t)]
        lines.append(f"| {t} | {m['constant_train_rate']['brier']:.5f} | {m['gap_empirical']['brier']:.5f} | {m['logistic']['brier']:.5f} | {report['selected'][str(t)]} |")
    lines+=['','Brier נמוך עדיף. מילוי/קידוד וסקיילינג נלמדים באימון בלבד; אין שימוש בתוצאת טיסה, סטטוס או מזהה כתכונת מודל.','', 'תוצאות demo ותרשימי כיול מלאים זמינים ב־models.json ובממשק. ההסתברויות הן למרווח בקרב טיסות תקינות; אינן הסתברות לביטול או לפספוס נוסע.','', '## גבולות התוצאה','', '- דגימה דטרמיניסטית של 1/20 מהטיסות הנכנסות, לפי מזהה לוח זמנים בלבד; מספר זוגות אינו מספר תצפיות עצמאיות.','- חברה מדווחת זהה, החלפת מספר טיסה, ללא חזרה למוצא, ומרווח מתוכנן של 30–240 דקות.','- הסטות, ביטולים וחוסרים נשמרים בנפרד ואינם תוויות אפס.','- ניתוח הקשר ORD/ATL מבוסס bootstrap של בלוקים שבועיים באימון בלבד; אינו מסקנה סיבתית.','- ניסוי בחירה בסוף אוקטובר מוגבל לקבוצות חלופות שנדגמו; אינו הוכחת תועלת על TEST.','- אין צילום היסטורי של לוח שהיה ידוע במועד ההזמנה, אין מחיר חי ואין אימות שהזוג נמכר.','- בהדגמה נמצאה הערכת חסר של הסיכון למרות כיול קודם. ההסתברויות עדיין אינן מתאימות לשימוש תפעולי; אין לתקן אותן לפי TEST.', '- טרם בוצעה סקירת ספרות מלאה או התקבל אישור מנחה להגדרות הפתוחות.','']
    diagnostic=report['calibration_diagnostic_45']
    paired=report['decision_experiment']['paired']
    lines += ['## אבחון כיול וניסוי החלטה','',
              f"בתרחיש 45 דקות בהדגמה: סיכון חזוי ממוצע {100*diagnostic['predicted_mean']:.2f}%, לעומת אי־עמידה נצפית {100*diagnostic['observed_mean']:.2f}%. נמצאה הערכת חסר; המודל אינו מוכן לשימוש תפעולי.", '',
              f"בהשוואה מזווגת מול כלל המרווח הארוך, הפרש שיעור אי־העמידה: {100*paired['difference_lowest_risk_minus_longest_gap']:.2f} נקודות אחוז; רווח 95%: {100*paired['interval_95'][0]:.2f} עד {100*paired['interval_95'][1]:.2f} נקודות אחוז. רווח אי־הוודאות כולל אפס בגרסה הנוכחית; אין ראיה מספקת ליתרון. זהו ניתוח התפתחותי, לא TEST.", '']
    (ROOT/'reports/model_report.md').write_text('\n'.join(lines))

if __name__=='__main__':main()
