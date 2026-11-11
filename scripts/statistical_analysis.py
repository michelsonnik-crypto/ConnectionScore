"""Exploratory hypothesis/effect analysis on training observations only."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]

def contrast(d,selector_a,selector_b,name):
    a=d.loc[selector_a].copy();b=d.loc[selector_b].copy()
    a['group']='a';b['group']='b'
    both=pd.concat([a,b]);both['week']=(pd.to_datetime(both.departure_date)-pd.Timestamp('2025-01-01')).dt.days//7
    counts=both.groupby(['week','group']).label_45.agg(['sum','count']).unstack('group').fillna(0)
    rng=np.random.default_rng(42)
    effects=[]
    for _ in range(2000):
        total=counts.iloc[rng.integers(0,len(counts),len(counts))].sum()
        effects.append(float(total[('sum','b')]/total[('count','b')]-total[('sum','a')]/total[('count','a')]))
    lo,hi=np.quantile(effects,[.025,.975])
    return dict(name=name,null_hypothesis='Difference of failure probabilities is zero',rate_a=float(a.label_45.mean()),rate_b=float(b.label_45.mean()),difference_b_minus_a=float(b.label_45.mean()-a.label_45.mean()),interval_95=[float(lo),float(hi)],ci_excludes_zero=bool(lo>0 or hi<0),n_a=len(a),n_b=len(b),weekly_blocks=len(counts))

def main():
    d=pd.read_csv(ROOT/'data/processed/connections_train.csv.gz',usecols=['departure_date','hub','gap_minutes','departure_hour','month','status','label_45'])
    d=d[(d.status=='operated') & d.gap_minutes.between(60,120)].copy()
    comparisons=[]
    comparisons.append(contrast(d,d.hub=='ATL',d.hub=='ORD','ORD לעומת ATL'))
    atl=d[d.hub=='ATL']
    comparisons.append(contrast(atl,atl.departure_hour.between(6,11),atl.departure_hour.between(18,23),'ATL: יציאה בערב לעומת בבוקר'))
    comparisons.append(contrast(d,d.month.isin([1,2]),d.month.isin([6,7]),'קיץ (יוני–יולי) לעומת חורף (ינואר–פברואר)'))
    report=dict(scope='Training only; margin scenario 45 min, scheduled gap 60–120 min',method='2000 weekly block bootstrap resamples; seed 42',comparisons=comparisons,limitations=['Exploratory analyses, no correction for multiple comparisons; not confirmatory tests','Weekly blocks only approximate dependence from repeated flights and overnight itineraries','Gap range is restricted but exact gap, carrier and route composition are not fully controlled','Associations are not causal; no validation/calibration/demo/test outcomes used'])
    (ROOT/'reports/statistical_analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    text=['# ניתוח סטטיסטי מורחב — אימון בלבד','', 'השערת אפס בכל השוואה: אין הבדל בהסתברות לאי־עמידה. מדווחים אומדן הפרש ורווח bootstrap של 95%, ב־2,000 דגימות של בלוקים שבועיים.','', 'האוכלוסייה: זוגות תקינים באימון, תרחיש 45 דקות, מרווח מתוכנן 60–120 דקות.','', '| השוואה B מול A | זוגות A / B | שיעור A | שיעור B | הפרש בנקודות אחוז | רווח 95% |','|---|---:|---:|---:|---:|---|']
    for c in comparisons:
        text.append(f"| {c['name']} | {c['n_a']:,} / {c['n_b']:,} | {100*c['rate_a']:.2f}% | {100*c['rate_b']:.2f}% | {100*c['difference_b_minus_a']:.2f} | {100*c['interval_95'][0]:.2f} עד {100*c['interval_95'][1]:.2f} |")
    text+=['','## פרשנות וזהירות מחקרית','', 'רווח שאינו כולל אפס מעיד על הבדל במבחן הגישוש המסוים; אין לראות בכך מסקנה סיבתית או ראיה מאששת לאחר ריבוי השוואות. אין תיקון לריבוי השוואות, והרכב קווים, חברות ומרווחים מדויקים לא נשלט במלואו.','', 'נבחרו מראש בסקריפט שלוש השוואות: שדה, שעת יציאה ועונתיות. לא נבחרו לפי תוצאות TEST. ספירת זוגות אינה מספר תצפיות עצמאיות; בלוקים שבועיים מפחיתים אך אינם מבטלים את מגבלת התלות.','', 'המשך נדרש: מודל היסקי מותאם עם משתני בקרה ותוכנית השערות סופית מול המנחה. זהו ניתוח ביניים, לא תחליף לפרק סטטיסטיקה מלא.','']
    (ROOT/'reports/statistical_analysis.md').write_text('\n'.join(text))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
