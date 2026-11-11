"""Separate validation-only experiment; existing calibrated app remains unchanged."""
from pathlib import Path
import sys,json,pickle,hashlib,warnings
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
import pandas as pd
import xgboost
from xgboost import XGBClassifier
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder,StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.exceptions import ConvergenceWarning
from connection_score.history import collect,augment,HISTORY_COLUMNS,POLICY
from train_models import features,CATEGORICAL,NUMERIC,evaluate,gap_fit,gap_predict

ROOT=Path(__file__).resolve().parents[1]


def main():
    warnings.simplefilter('error',ConvergenceWarning)
    snapshot=collect(ROOT)
    base={s:pd.read_csv(ROOT/f'data/processed/connections_{s}.csv.gz',dtype={k:'category' for k in CATEGORICAL+['status']}) for s in ['train','validation']}
    frames={s:df[df.status=='operated'].copy() for s,df in base.items()}
    frames['train']=frames['train'].sample(n=min(300000,len(frames['train'])),random_state=42).sort_index()
    assert not (set(base['train'].first_id)|set(base['train'].second_id)) & (set(base['validation'].first_id)|set(base['validation'].second_id))
    augmented={s:augment(df,snapshot) for s,df in frames.items()}
    xs={s:features(df) for s,df in augmented.items()}
    for s in xs:xs[s][HISTORY_COLUMNS]=augmented[s][HISTORY_COLUMNS]
    report={'experiment':'v2_history_xgboost_validation_only','history_policy':POLICY,'source_months_by_target':{m:v['source_months'] for m,v in snapshot.items()},'training_rows':len(frames['train']),'validation_rows':len(frames['validation']),'history_available_fraction':{s:float((d.history_missing==0).mean()) for s,d in augmented.items()},'xgboost_version':xgboost.__version__,'thresholds':{},'test_status':'Not downloaded or opened','calibration_status':'Not used in this experiment; existing app/model retained','demo_status':'Not read by this experiment; previously inspected demo is development data, not an independent holdout','parameters':dict(n_estimators=250,max_depth=4,learning_rate=.05,min_child_weight=20,subsample=.8,colsample_bytree=.8,reg_lambda=5,tree_method='hist',n_jobs=2,random_state=42)}
    models={}
    connections=json.loads((ROOT/'reports/connections.json').read_text())
    report['connection_input_sha256']={s:connections['splits'][s]['sha256'] for s in ['train','validation']}
    manifest=json.loads((ROOT/'data/manifest.json').read_text())
    report['history_source_sha256']={r['file']:r['sha256'] for r in manifest if r['file'] in {f'bts_2025_{m:02d}.zip' for m in range(1,9)}}
    for threshold in [30,45,60]:
        y=frames['train'][f'label_{threshold}'];vy=frames['validation'][f'label_{threshold}']
        default=float(y.mean());rates=gap_fit(frames['train'],f'label_{threshold}')
        scores={'constant':evaluate(vy,np.full(len(vy),default)),'gap_empirical':evaluate(vy,gap_predict(frames['validation'],rates,default))}
        for kind,history in [('logistic',False),('logistic',True),('xgboost',False),('xgboost',True)]:
            numeric=NUMERIC+(HISTORY_COLUMNS if history else [])
            cols=CATEGORICAL+numeric
            preprocessing=ColumnTransformer([('cat',OneHotEncoder(handle_unknown='ignore'),CATEGORICAL),('num',StandardScaler(),numeric)])
            estimator=LogisticRegression(C=.5,max_iter=1500,solver='lbfgs',random_state=42) if kind=='logistic' else XGBClassifier(**report['parameters'],objective='binary:logistic',eval_metric='logloss')
            model=make_pipeline(preprocessing,estimator)
            model.fit(xs['train'][cols],y)
            prediction=model.predict_proba(xs['validation'][cols])[:,1]
            name=kind+('_history' if history else '_schedule')
            scores[name]=evaluate(vy,prediction)
            models[(threshold,name)]=model
            print(threshold,name,'Brier',scores[name]['brier'],flush=True)
        chosen=min(scores,key=lambda k:scores[k]['brier'])
        report['thresholds'][str(threshold)]={'scores':scores,'best_validation_brier':chosen,'history_effect_logistic':scores['logistic_history']['brier']-scores['logistic_schedule']['brier'],'history_effect_xgboost':scores['xgboost_history']['brier']-scores['xgboost_schedule']['brier']}
    (ROOT/'artifacts').mkdir(exist_ok=True)
    with (ROOT/'artifacts/advanced_models.pkl').open('wb') as f:pickle.dump(dict(models=models,snapshot=snapshot,policy=POLICY),f)
    report['artifact_sha256']=hashlib.file_digest((ROOT/'artifacts/advanced_models.pkl').open('rb'),'sha256').hexdigest()
    (ROOT/'reports/advanced_comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    rows=['# ניסוי המשך: היסטוריית איחורים ו־XGBoost','', '**ניסוי ולידציה בלבד. TEST לא הורד ולא נקרא; המודל והאתר הקיימים לא הוחלפו.**','', '## ההשוואה','', 'אותו מדגם אימון (עד 300,000 זוגות), אותה ולידציה ואותו מדד Brier לכל החלופות. לא בוצע חיפוש היפרפרמטרים או early stopping על TEST. נבדקו לוגיסטית ו־XGBoost, כל אחת עם ובלי היסטוריה.','', '| סף | קבוע | מרווח בלבד | לוגיסטית | לוגיסטית + היסטוריה | XGBoost | XGBoost + היסטוריה | הנמוך בוולידציה |','|---|---:|---:|---:|---:|---:|---:|---|']
    order=['constant','gap_empirical','logistic_schedule','logistic_history','xgboost_schedule','xgboost_history']
    for t,r in report['thresholds'].items():rows.append('| '+t+' | '+' | '.join(f"{r['scores'][k]['brier']:.5f}" for k in order)+' | '+r['best_validation_brier']+' |')
    rows+=['','## היסטוריה וזמינות מידע','', 'הוספו ספירת טיסות קו/חברה נכנסת, ממוצע ArrDelay ושיעור איחור של 15 דקות ומעלה, לצד סיכומי חברה וסימון חוסר. הגעה מוקדמת נשמרת בערכה השלילי. רק חודשי אימון יכולים להיכנס למקור ההיסטוריה.','', 'הניסוי מניח תכנון 30 יום לפני יציאה ועיכוב פרסום שמרני של 90 יום נוספים. משתמשים רק בחודשים שלמים שהסתיימו לפני החיתוך של היום הראשון בחודש היעד. אין שימוש בהיסטוריה מאותו חודש או מהעתיד. בתחילת 2025 אין היסטוריה זמינה, והחוסר מפורש.','', '**90 יום הם הנחת סימולציה, לא אימות תאריכי הפרסום של BTS. לכן עדיין אי אפשר לטעון שהוכחה זמינות כל נתון במועד ההזמנה.** תיעוד זמינות בפועל או ארכיון פרסומים נדרש לשלב המחקר הבא.','', '## מה המסקנה מאפשרת','', 'זו השוואה התפתחותית על ולידציה שכבר שימשה קודם. בחירת המינימום אינה הוכחת שיפור מובהק או תועלת חיצונית. הוספת מודל מתקדם אינה מבטיחה שיפור, והיסטוריה עשויה לעזור או להזיק. לפני החלפת המודל באתר נדרש להחליט על מועמד, לכייל בנפרד ולתעד את הגרסה; אין לפתוח TEST כדי לבחור.','', 'פירוט מדדים, כיסוי, פרמטרים וחתימת המודל: advanced_comparison.json.','']
    (ROOT/'reports/advanced_comparison.md').write_text('\n'.join(rows))

if __name__=='__main__':main()
