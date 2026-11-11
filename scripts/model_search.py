"""Broad, bounded model experiment with rolling-origin screening and sealed TEST."""
from pathlib import Path
import sys,json,time,pickle,warnings,hashlib,platform
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import numpy as np
import pandas as pd
from scipy.special import logit,expit
from scipy.optimize import brentq,minimize_scalar
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder,StandardScaler,OrdinalEncoder,KBinsDiscretizer,PolynomialFeatures,SplineTransformer
from sklearn.impute import SimpleImputer
from sklearn.decomposition import PCA,TruncatedSVD
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier,ExtraTreesClassifier,AdaBoostClassifier,HistGradientBoostingClassifier
from sklearn.naive_bayes import GaussianNB,MultinomialNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import LinearSVC
from sklearn.isotonic import IsotonicRegression
from sklearn.exceptions import ConvergenceWarning
import sklearn,xgboost
from xgboost import XGBClassifier
from train_models import features,CATEGORICAL,NUMERIC,evaluate,gap_fit,gap_predict

ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'configs/model_search.json').read_text())
NAMES=['constant','gap_empirical','logistic_c01','logistic_c05','logistic_c5','logistic_spline','logistic_poly','logistic_pca','tree_depth4','tree_depth10','random_forest12','random_forest20','extra_trees','adaboost_stump','adaboost_depth2','gaussian_nb','multinomial_nb','knn25_svd','linear_svm','hist_boost','xgb_depth3','xgb_depth4','xgb_depth6']


def preprocessor(numeric=None):
    return ColumnTransformer([('cat',OneHotEncoder(handle_unknown='ignore'),CATEGORICAL),('num',numeric or StandardScaler(),NUMERIC)])


def make_model(name):
    if name.startswith('logistic_'):
        numeric=StandardScaler()
        if name=='logistic_spline':numeric=make_pipeline(SplineTransformer(n_knots=4,degree=2,include_bias=False),StandardScaler())
        if name=='logistic_poly':numeric=make_pipeline(PolynomialFeatures(degree=2,include_bias=False),StandardScaler())
        if name=='logistic_pca':numeric=make_pipeline(StandardScaler(),PCA(n_components=.95,svd_solver='full'))
        c={'logistic_c01':.1,'logistic_c05':.5,'logistic_c5':5}.get(name,.5)
        return make_pipeline(preprocessor(numeric),LogisticRegression(C=c,max_iter=1800,random_state=42))
    if name=='linear_svm':return make_pipeline(preprocessor(),LinearSVC(C=.1,max_iter=10000,dual='auto',random_state=42))
    if name=='gaussian_nb':return make_pipeline(preprocessor(),TruncatedSVD(n_components=20,random_state=42),GaussianNB(var_smoothing=1e-6))
    if name=='multinomial_nb':
        prep=ColumnTransformer([('cat',OneHotEncoder(handle_unknown='ignore'),CATEGORICAL),('num',KBinsDiscretizer(n_bins=8,encode='onehot',strategy='quantile',quantile_method='averaged_inverted_cdf'),NUMERIC)])
        return make_pipeline(prep,MultinomialNB(alpha=1))
    if name=='knn25_svd':return make_pipeline(preprocessor(),TruncatedSVD(n_components=20,random_state=42),StandardScaler(),KNeighborsClassifier(n_neighbors=25,weights='distance',algorithm='brute',n_jobs=2))
    if name=='hist_boost':
        prep=ColumnTransformer([('cat',OrdinalEncoder(handle_unknown='use_encoded_value',unknown_value=np.nan),CATEGORICAL),('num',StandardScaler(),NUMERIC)],sparse_threshold=0)
        # Airports can exceed 255 categories: ordinal codes are treated as numeric.
        return make_pipeline(prep,HistGradientBoostingClassifier(max_iter=180,max_leaf_nodes=15,l2_regularization=5,learning_rate=.05,early_stopping=False,random_state=42))
    if name.startswith('tree_'):est=DecisionTreeClassifier(max_depth=4 if name.endswith('4') else 10,min_samples_leaf=100,random_state=42)
    elif name.startswith('random_forest'):est=RandomForestClassifier(n_estimators=120,max_depth=12 if name.endswith('12') else 20,min_samples_leaf=50,max_features=.5,n_jobs=2,random_state=42)
    elif name=='extra_trees':est=ExtraTreesClassifier(n_estimators=150,max_depth=20,min_samples_leaf=40,max_features=.5,n_jobs=2,random_state=42)
    elif name.startswith('adaboost'):est=AdaBoostClassifier(estimator=DecisionTreeClassifier(max_depth=1 if name.endswith('stump') else 2,min_samples_leaf=100,random_state=42),n_estimators=100,learning_rate=.1,random_state=42)
    elif name.startswith('xgb_'):est=XGBClassifier(n_estimators=250,max_depth=int(name[-1]),learning_rate=.05,min_child_weight=20,subsample=.8,colsample_bytree=.8,reg_lambda=5,tree_method='hist',n_jobs=2,random_state=42,eval_metric='logloss')
    else:raise ValueError(name)
    return make_pipeline(preprocessor(),est)


def fit_predict(name,train,valid,target):
    if name=='constant':return None,np.full(len(valid),float(train[target].mean()))
    if name=='gap_empirical':
        rates=gap_fit(train,target);default=float(train[target].mean())
        return {'rates':rates,'default':default},gap_predict(valid,rates,default)
    model=make_model(name)
    if name=='linear_svm':
        dates=sorted(train.departure_date.unique());cutoff=dates[max(1,int(len(dates)*.8))]
        early=train[train.departure_date<cutoff];late=train[train.departure_date>=cutoff]
        model.fit(features(early),early[target])
        calibrator=LogisticRegression(C=1e6,max_iter=1000).fit(model.decision_function(features(late)).reshape(-1,1),late[target])
        p=calibrator.predict_proba(model.decision_function(features(valid)).reshape(-1,1))[:,1]
        return (model,calibrator),p
    model.fit(features(train),train[target])
    return model,model.predict_proba(features(valid))[:,1]


def raw_predict(name,model,train,frame,target):
    if name=='constant':return np.full(len(frame),float(train[target].mean()))
    if name=='gap_empirical':return gap_predict(frame,model['rates'],model['default'])
    if name=='linear_svm':return model[1].predict_proba(model[0].decision_function(features(frame)).reshape(-1,1))[:,1]
    return model.predict_proba(features(frame))[:,1]


def calibrate(method,p,y):
    p=np.clip(np.asarray(p),1e-6,1-1e-6);z=logit(p)
    if method=='none':return ('none',None)
    if method=='sigmoid':
        m=LogisticRegression(C=1e6,max_iter=1000).fit(z.reshape(-1,1),y)
        if m.coef_[0,0]<=0:raise ValueError('reversed calibration slope')
        return (method,m)
    if method=='isotonic':return (method,IsotonicRegression(out_of_bounds='clip').fit(p,y))
    if method=='prior_offset':return (method,float(brentq(lambda b:expit(z+b).mean()-np.mean(y),-30,30)))
    if method=='temperature':
        def objective(logt):
            q=np.clip(expit(z/np.exp(logt)),1e-9,1-1e-9)
            return -np.mean(y*np.log(q)+(1-y)*np.log1p(-q))
        r=minimize_scalar(objective,bounds=(-4,4),method='bounded')
        return (method,float(np.exp(r.x)))
    raise ValueError(method)


def calibrated(cal,p):
    kind,m=cal;p=np.clip(np.asarray(p),1e-6,1-1e-6);z=logit(p)
    if kind=='none':return p
    if kind=='sigmoid':return m.predict_proba(z.reshape(-1,1))[:,1]
    if kind=='isotonic':return m.predict(p)
    if kind=='prior_offset':return expit(z+m)
    return expit(z/m)


def checkpoint(report):
    (ROOT/'reports/model_search.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')


def main():
    warnings.simplefilter('error',ConvergenceWarning)
    train=pd.read_csv(ROOT/'data/processed/connections_train.csv.gz',dtype={k:'category' for k in CATEGORICAL+['status']})
    train=train[train.status=='operated'].copy()
    report={'status':'running','configuration':CONFIG,'model_names':NAMES,'screen':{},'screen_failures':[],'final_validation':{},'calibration':{},'demo':{},'test_status':'LOCKED_NOT_DOWNLOADED_NOT_OPENED','versions':dict(python=platform.python_version(),sklearn=sklearn.__version__,xgboost=xgboost.__version__),'notes':['Rolling screening on June/July/August 2025; each training window ends two days before evaluation month.','All candidates use same scheduled features; projections/ordinal encoding are documented variants.','KNN cost is bounded by screening cap; finalists train on up to 300000 pairs.','Calibration method chosen within calibration period only. Demo has already been inspected in earlier work and is not an untouched test.']}
    for name in NAMES:
        scores=[]
        for month in CONFIG['screen_months']:
            start=pd.Timestamp(2025,month,1);end=start+pd.offsets.MonthBegin()
            a=train[pd.to_datetime(train.departure_date)<start-pd.Timedelta(days=2)]
            b=train[(pd.to_datetime(train.departure_date)>=start+pd.Timedelta(days=2))&(pd.to_datetime(train.departure_date)<end-pd.Timedelta(days=2))]
            a=a.sample(n=min(CONFIG['screen_train_cap'],len(a)),random_state=42).sort_values(['departure_date','first_id','second_id'])
            b=b.sample(n=min(CONFIG['screen_evaluation_cap'],len(b)),random_state=42).sort_values(['departure_date','first_id','second_id'])
            assert not (set(a.first_id)|set(a.second_id)) & (set(b.first_id)|set(b.second_id)),'Rolling split flight overlap'
            started=time.monotonic()
            try:
                _,p=fit_predict(name,a,b,'label_45')
                score=evaluate(b.label_45,p);score.update(month=month,training_rows=len(a),elapsed_seconds=round(time.monotonic()-started,2))
                scores.append(score)
            except Exception as e:
                report['screen_failures'].append(dict(model=name,month=month,error=type(e).__name__+': '+str(e)))
                print('FAILED',name,month,type(e).__name__,str(e)[:180],flush=True)
                break
        if len(scores)==len(CONFIG['screen_months']):
            report['screen'][name]={'folds':scores,'mean_brier':float(np.mean([s['brier'] for s in scores]))}
            print('SCREEN',name,report['screen'][name]['mean_brier'],flush=True)
        checkpoint(report)
    ranking=sorted(report['screen'],key=lambda n:report['screen'][n]['mean_brier'])
    finalists=ranking[:CONFIG['finalist_count']]
    # Keep original reference models even if not top ranked.
    for n in ['gap_empirical','logistic_c05','xgb_depth4']:
        if n not in finalists and n in report['screen']:finalists.append(n)
    report['screen_ranking']=ranking;report['finalists']=finalists
    tr=train.sample(n=min(CONFIG['final_train_cap'],len(train)),random_state=42).sort_index()
    validation=pd.read_csv(ROOT/'data/processed/connections_validation.csv.gz',dtype={k:'category' for k in CATEGORICAL+['status']});validation=validation[validation.status=='operated'].copy()
    assert not (set(tr.first_id)|set(tr.second_id)) & (set(validation.first_id)|set(validation.second_id))
    models={};selected={}
    for t in [30,45,60]:
        scores={}
        for name in finalists:
            model,p=fit_predict(name,tr,validation,f'label_{t}');models[(t,name)]=model
            scores[name]=evaluate(validation[f'label_{t}'],p)
            print('FINAL',t,name,scores[name]['brier'],flush=True)
        selected[t]=min(scores,key=lambda n:scores[n]['brier'])
        report['final_validation'][str(t)]={'scores':scores,'selected':selected[t]}
        checkpoint(report)
    cal=pd.read_csv(ROOT/'data/processed/connections_calibration.csv.gz');cal=cal[cal.status=='operated'].copy()
    early=cal.departure_date<'2025-10-08';late=cal.departure_date>=CONFIG['calibration_holdout_start']
    assert early.any() and late.any()
    assert not (set(cal.loc[early].first_id)|set(cal.loc[early].second_id)) & (set(cal.loc[late].first_id)|set(cal.loc[late].second_id))
    calibrators={}
    # Choose and freeze methods before opening the already-known development demo.
    for t in [30,45,60]:
        name=selected[t];raw=raw_predict(name,models[(t,name)],tr,cal,f'label_{t}')
        results={}
        for method in CONFIG['calibration_methods']:
            c=calibrate(method,raw[early],cal.loc[early,f'label_{t}'])
            results[method]=evaluate(cal.loc[late,f'label_{t}'],calibrated(c,raw[late]))
        chosen=min(results,key=lambda n:results[n]['brier'])
        calibrators[t]=calibrate(chosen,raw,cal[f'label_{t}'])
        report['calibration'][str(t)]={'method_scores':results,'selected_method':chosen,'fit_rows':int(early.sum()),'selection_rows':int(late.sum()),'full_refit_rows':len(cal)}
        checkpoint(report)
    report['status']='selection_and_calibration_frozen_before_demo';checkpoint(report)
    demo=pd.read_csv(ROOT/'data/processed/connections_demo.csv.gz');demo=demo[demo.status=='operated'].copy()
    predictions=[];raws=[]
    for t in [30,45,60]:
        raw=raw_predict(selected[t],models[(t,selected[t])],tr,demo,f'label_{t}');raws.append(raw)
        predictions.append(calibrated(calibrators[t],raw))
    probs=np.maximum.accumulate(np.column_stack(predictions),axis=1)
    for i,t in enumerate([30,45,60]):
        p=probs[:,i];report['demo'][str(t)]={'raw':evaluate(demo[f'label_{t}'],raws[i]),'calibrated_monotone':evaluate(demo[f'label_{t}'],p),'predicted_mean':float(p.mean()),'observed_mean':float(demo[f'label_{t}'].mean())}
    artifact=ROOT/'artifacts/model_search.pkl'
    with artifact.open('wb') as f:pickle.dump(dict(models=models,selected=selected,calibrators=calibrators,config=CONFIG),f)
    report['artifact_sha256']=hashlib.file_digest(artifact.open('rb'),'sha256').hexdigest()
    report['status']='complete';checkpoint(report)
    write_report(report)


def write_report(r):
    rows=['# השוואת משפחות מודלים ושיטות כיול','', '**TEST נותר סגור ולא הורד. האתר הקיים לא הוחלף בעקבות חיפוש זה.**','', '## מתודולוגיה','', 'סינון ראשוני: חלונות זמן יוני, יולי ואוגוסט; בכל חלון אימון על עבר בלבד, עד 60,000 זוגות, ובדיקה על עד 20,000 זוגות. תרחיש 45 דקות משמש לסינון. נבדקת אי־חפיפת טיסות בין חלונות. ארבעת המובילים ומודלי הייחוס מותאמים ל־300,000 זוגות ונבדקים על כל ולידציית ספטמבר בשלושת הספים.','', 'בחירת כיול בין ללא כיול, sigmoid, isotonic, תיקון prior ו־temperature: אימון כיול בתחילת אוקטובר ובחירה בסופו של חלון הכיול, עם הפרדה של יומיים. לאחר הבחירה מכיילים שוב על כל חלון הכיול. סוף אוקטובר הוא demo שכבר נבדק בעבר ואינו TEST עצמאי.','', '## סינון בחלונות זמן','', '| מודל | Brier ממוצע (45 דקות) | זמן כולל לשלושת החלונות, שניות |','|---|---:|---:|']
    rows += [f"| {n} | {r['screen'][n]['mean_brier']:.5f} | {sum(f['elapsed_seconds'] for f in r['screen'][n]['folds']):.1f} |" for n in r['screen_ranking']]
    rows+=['','## בחירה סופית בוולידציה','', '| סף | מודל נבחר | Brier בוולידציה | שיטת כיול |','|---|---|---:|---|']
    for t,v in r['final_validation'].items():rows.append(f"| {t} | {v['selected']} | {v['scores'][v['selected']]['brier']:.5f} | {r['calibration'][t]['selected_method']} |")
    rows+=['','## כל המועמדים בוולידציה המלאה','', '| מודל | Brier 30 | Brier 45 | Brier 60 |', '|---|---:|---:|---:|']
    for name in r['finalists']:
        rows.append('| '+name+' | '+' | '.join(f"{r['final_validation'][str(t)]['scores'][name]['brier']:.5f}" for t in [30,45,60])+' |')
    rows+=['','## השוואת כיול בתוך חלון הכיול בלבד','', '| שיטה | Brier 30 | Brier 45 | Brier 60 |', '|---|---:|---:|---:|']
    for method in CONFIG['calibration_methods']:
        rows.append('| '+method+' | '+' | '.join(f"{r['calibration'][str(t)]['method_scores'][method]['brier']:.5f}" for t in [30,45,60])+' |')
    rows+=['','## אבחון בהדגמה — לא בסיס לבחירה','', '| סף | Brier ללא כיול | Brier אחרי כיול ומונוטוניות | סיכון חזוי ממוצע | אי־עמידה נצפית |','|---|---:|---:|---:|---:|']
    for t,d in r['demo'].items():rows.append(f"| {t} | {d['raw']['brier']:.5f} | {d['calibrated_monotone']['brier']:.5f} | {100*d['predicted_mean']:.2f}% | {100*d['observed_mean']:.2f}% |")
    rows+=['','## תפקידי המודלים והגבולות','', '- לוגיסטית, עצים, Random Forest, Naive Bayes, KNN, SVM ו־AdaBoost קשורים לחומר בקובץ הקורס. ExtraTrees ו־HistGradientBoosting הן הרחבות להשוואה.','- PCA נבדק על התכונות המספריות בלבד, ו־TruncatedSVD על מטריצה דלילה עבור KNN/GaussianNB; SVD לא ממורכז אינו זהה ל־PCA.','- SVM לינארי מקבל כיול פנימי על סוף חלון האימון, בלי cross-validation אקראי.','- HistGradientBoosting מקבל קודי קטגוריות כספרות כדי להתמודד עם יותר מ־255 שדות; זו מגבלת ייצוג מוצהרת.','- אין כאן ניסיון לכפות K-Means, HMM, מערכות המלצה שיתופיות או Isolation Forest על יעד סיווג שאינו מתאים להנחותיהם.','- רגרסיה לינארית אינה בחירה ראשית להסתברות בינארית, שעלולה לחרוג מ־0–1.','- נתוני היסטוריה כבר נבדקו בניסוי קודם; החיפוש הנוכחי משווה משפחות על אותן תכונות לו״ז כדי לבודד את השפעת האלגוריתם.','- חלוקת הזמן מתייחסת למועד האירוע ואינה מאמתת מתי תוויות BTS פורסמו או היו זמינות לאימון מודל 30 יום לפני נסיעה. לפני טענת תקפות למועד הזמנה יש לאכוף גם אופק תכנון ועיכוב פרסום על גבול נתוני האימון.', '- ריבוי ניסויים על אותה ולידציה מגדיל סיכון להתאמת יתר; מינימום Brier אינו הוכחת הכללה או מובהקות. נדרש TEST אחרי נעילת התהליך.','- אין מחיקת חריגים רק מפני שהם איחורים קשים; אלה אירועים חשובים ליעד.','- ציוני הסתברות דורשים כיול, ושיפור Brier אינו בהכרח הוכחת תועלת בבחירת מסלול.','']
    rows+=['## תרשימים','', '![סינון מודלים בשלושה חלונות זמן](model_screening.svg)', '', 'טווחי התרשים הם מינימום ומקסימום של שלושה חלונות זמן, ולא רווחי סמך.', '', '![אבחון שגיאה וכיול בתקופת ההדגמה](model_calibration_diagnostics.svg)', '']
    if r['screen_failures']:rows+=['## ניסיונות שנכשלו','']+[f"- {x['model']} בחודש {x['month']}: {x['error']}" for x in r['screen_failures']]
    (ROOT/'reports/model_search.md').write_text('\n'.join(rows))

if __name__=='__main__':main()
