"""Follow-up: choose calibration across seasons rather than one short October window."""
from pathlib import Path
import sys,json,pickle,hashlib
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
from model_search import make_model,calibrate,calibrated,raw_predict
from train_models import CATEGORICAL,features,evaluate
ROOT=Path(__file__).resolve().parents[1]

def main():
    config=json.loads((ROOT/'configs/temporal_calibration.json').read_text())
    previous=json.loads((ROOT/'reports/model_search.json').read_text())
    with (ROOT/'artifacts/model_search.pkl').open('rb') as f:bundle=pickle.load(f)
    selected=bundle['selected']
    train=pd.read_csv(ROOT/'data/processed/connections_train.csv.gz',dtype={k:'category' for k in CATEGORICAL+['status']})
    train=train[train.status=='operated'].copy();dates=pd.to_datetime(train.departure_date)
    report={'status':'running','configuration':config,'model_selection_source':'Previous September validation; this is development follow-up, not independent validation','folds':{},'selected_methods':{},'demo':{},'test_status':'not_downloaded_not_opened','previous_demo_already_seen':True}
    for t in [30,45,60]:
        folds=[]
        for month in config['evaluation_months']:
            es=pd.Timestamp(2025,month,1);cs=es-pd.offsets.MonthBegin();ee=es+pd.offsets.MonthBegin()
            a=train[dates<cs-pd.Timedelta(days=2)]
            b=train[(dates>=cs+pd.Timedelta(days=2))&(dates<es-pd.Timedelta(days=2))]
            c=train[(dates>=es+pd.Timedelta(days=2))&(dates<ee-pd.Timedelta(days=2))]
            a=a.sample(n=min(config['train_cap'],len(a)),random_state=42).sort_index();b=b.sample(n=min(config['calibration_cap'],len(b)),random_state=42).sort_index();c=c.sample(n=min(config['evaluation_cap'],len(c)),random_state=42).sort_index()
            ids=[set(d.first_id)|set(d.second_id) for d in [a,b,c]]
            assert all(not ids[i]&ids[j] for i in range(3) for j in range(i+1,3))
            model=make_model(selected[t]);model.fit(features(a),a[f'label_{t}'])
            bp=model.predict_proba(features(b))[:,1];cp=model.predict_proba(features(c))[:,1]
            scores={}
            for method in config['methods']:
                fit=calibrate(method,bp,b[f'label_{t}']);out=calibrated(fit,cp)
                scores[method]=dict(brier=float(np.mean((out-c[f'label_{t}'].to_numpy())**2)),predicted_mean=float(out.mean()),observed_mean=float(c[f'label_{t}'].mean()))
            folds.append(dict(evaluation_month=month,train_rows=len(a),calibration_rows=len(b),evaluation_rows=len(c),scores=scores))
            print('TEMPORAL CAL',t,month,flush=True)
        means={m:float(np.mean([f['scores'][m]['brier'] for f in folds])) for m in config['methods']}
        report['folds'][str(t)]=dict(folds=folds,mean_brier=means)
        report['selected_methods'][str(t)]=min(means,key=means.get)
    # Methods fixed before re-reading the known demo. No choice by its outcome.
    cal=pd.read_csv(ROOT/'data/processed/connections_calibration.csv.gz');cal=cal[cal.status=='operated']
    calibrators={}
    for t in [30,45,60]:
        model=bundle['models'][(t,selected[t])]
        p=raw_predict(selected[t],model,None,cal,f'label_{t}')
        calibrators[t]=calibrate(report['selected_methods'][str(t)],p,cal[f'label_{t}'])
    demo=pd.read_csv(ROOT/'data/processed/connections_demo.csv.gz');demo=demo[demo.status=='operated']
    ps=[]
    for t in [30,45,60]:
        model=bundle['models'][(t,selected[t])];p=raw_predict(selected[t],model,None,demo,f'label_{t}')
        ps.append(calibrated(calibrators[t],p))
    predictions=np.maximum.accumulate(np.column_stack(ps),axis=1)
    for i,t in enumerate([30,45,60]):
        p=predictions[:,i];report['demo'][str(t)]=dict(metrics=evaluate(demo[f'label_{t}'],p),predicted_mean=float(p.mean()),observed_mean=float(demo[f'label_{t}'].mean()))
    path=ROOT/'artifacts/temporal_calibration.pkl'
    with path.open('wb') as f:pickle.dump(dict(models={t:bundle['models'][(t,selected[t])] for t in [30,45,60]},selected=selected,calibrators=calibrators,config=config),f)
    report['artifact_sha256']=hashlib.file_digest(path.open('rb'),'sha256').hexdigest();report['status']='complete'
    (ROOT/'reports/temporal_calibration.json').write_text(json.dumps(report,indent=2)+'\n')
    lines=['# ניסוי המשך: כיול בכמה חלונות זמן','', '**ניסוי התפתחותי נוסף בעקבות פער שנראה ב־demo. TEST נשאר סגור. demo כבר מוכר ואינו בדיקה עצמאית.**','', 'בכל חלון מאמנים את משפחת המודל שנבחרה קודם, מכיילים על החודש הבא, ומשווים שיטות בחודש שאחריו. חודשי הערכה: יוני, יולי ואוגוסט; אין חפיפה של טיסות בין תפקידים. משפחת המודל נבחרה בספטמבר קודם לכן, ולכן ציוני החלונות הם כלי לכוונון כיול ולא הערכה עצמאית של בחירת המודל.','', '| שיטת כיול | Brier ממוצע 30 | Brier ממוצע 45 | Brier ממוצע 60 |','|---|---:|---:|---:|']
    for m in config['methods']:lines.append('| '+m+' | '+' | '.join(f"{report['folds'][str(t)]['mean_brier'][m]:.5f}" for t in [30,45,60])+' |')
    lines+=['','## אבחון על demo לאחר בחירת השיטה בחלונות','', '| סף | שיטה נבחרת | Brier | סיכון חזוי ממוצע | שיעור נצפה |','|---|---|---:|---:|---:|']
    for t,d in report['demo'].items():lines.append(f"| {t} | {report['selected_methods'][t]} | {d['metrics']['brier']:.5f} | {100*d['predicted_mean']:.2f}% | {100*d['observed_mean']:.2f}% |")
    lines+=['','המודל והאתר הקיימים לא הוחלפו. גם אם התוצאה משתפרת ב־demo, אין זו הוכחת הכללה: הניסוי תוכנן לאחר שה־demo כבר נבדק. מועד פרסום תוויות BTS ואופק תכנון דורשים עדיין אימות; חלוקה לפי תאריך אירוע אינה מספיקה להוכיח זמינות במועד ההזמנה.','']
    (ROOT/'reports/temporal_calibration.md').write_text('\n'.join(lines))
    print('Selected calibration methods',report['selected_methods'],flush=True)

if __name__=='__main__':main()
