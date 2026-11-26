from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
run=sys.argv[1];r=json.loads((ROOT/'reports/runs'/run/'results.json').read_text())
assert r['status']=='complete'
def table(head,rows):return '\n'.join(['| '+' | '.join(head)+' |','|'+'|'.join(['---']*len(head))+'|']+['| '+' | '.join(map(str,row))+' |' for row in rows])
primary=r['validation']['45'];dif=r['validation_differences'];s=r['matched_inference'];demo=r['demo']['45']
lines=['# תשובה לשאלת המחקר — ניסוי רטרוספקטיבי מבוקר',f"מקור כל התוצאות: ריצה `{run}`, commit `{r['commit']}`, פלט `reports/runs/{run}/results.json`. ספים ופרמטרים הם תצורה. ניסוי פיתוח מוכר; TEST לא נקרא.",
'## השאלה שנבדקה','האם מאפייני לו״ז והיסטוריית טיסות מוסיפים חיזוי אי־עמידה בסף מעבר מעבר למרווח בלבד, באוכלוסיית BTS המוגדרת? לא נבחנה הבטחה לפני הזמנה או פספוס נוסע.',
'## השוואה הוגנת בוולידציה',table(['קלט ומודל','Brier','ROC-AUC','AP'],[[name,f"{m['brier']:.5f}",f"{m['roc_auc']:.4f}",f"{m['average_precision']:.4f}"] for name,m in primary['metrics'].items()]),
'אותם פרמטרי XGBoost ואותן תצפיות משמשים במרווח בלבד, לו״ז והיסטוריה. CDF הוא בסיס נוסף המבוסס על האירוע ArrDelay > gap − threshold, עם טיסה נכנסת אחת לכל מזהה במדגם ההתאמה.',
'## מה המידע הנוסף תורם?',table(['הפרש ראשון פחות שני','הפרש Brier','רווח ימים'],[[name,f"{v['brier_difference']:.6f}",f"{v['interval_95'][0]:.6f} עד {v['interval_95'][1]:.6f}"] for name,v in dif.items()]),
'ערך שלילי מעדיף את המודל הראשון. רווחים אלה הם גישושיים על ולידציה שכבר נבדקה בעבר; תלות בין ימים ובחירות מודל קודמות מגבילות פרשנות מאששת.',
'## האם אפשר לענות על השאלה?',
('נמצאה עדות פיתוח לכך שמאפייני לו״ז נוספים משפרים Brier מעבר ל־XGBoost שמקבל מרווח בלבד.' if dif['xgb_schedule_minus_xgb_gap']['interval_95'][1]<0 else 'אין כרגע ראיה מספקת לשיפור יציב של מאפייני לו״ז נוספים מעבר ל־XGBoost שמקבל מרווח בלבד.'),
('היסטוריה שיפרה את XGBoost בניסוי זה.' if dif['xgb_history_minus_xgb_schedule']['interval_95'][1]<0 else 'לא נמצאה ראיה מספקת שהיסטוריה משפרת את XGBoost בניסוי זה; אין הצדקה לכפות אותה על המודל הנבחר.'),
'זו תשובה לשאלת תרומת המידע במחקר רטרוספקטיבי, במסגרת מדגם השדות/החברות שנבדק. אין להסיק ממנה תוקף לכל ארה״ב או זמינות מידע ביום ההזמנה.',
'## ניתוח סטטיסטי באוכלוסייה בת השוואה',f"הניתוח מוגבל ל־ATL/DL, מרווח 60–120 ולשעת היציאה המקומית של הרגל הראשונה. נשמרו {s['retained_pairs']:,} זוגות מתוך {s['candidate_pairs']:,}, ב־{s['matched_cells']:,} תאי יום/מוצא/יעד/טווח מרווח וב־{s['days']} ימים. בכל תא יש בוקר וערב.",f"הפרש ערב פחות בוקר משוקלל: {100*s['standardized_evening_minus_morning']:.2f} נקודות אחוז, רווח ימים {100*s['interval_95'][0]:.2f} עד {100*s['interval_95'][1]:.2f}. זו אסוציאציה באוכלוסיית החפיפה, לא סיבתיות. שעת הניתוח אינה שעת ההגעה לשדה המעבר. טווח המרווח מותאם במקטעים ולכן נשאר ערבוב לפי הדקה המדויקת.",
'## כיול והדגמת פיתוח',f"נבחר {primary['selected']} בתרחיש הראשי. שיטת הכיול: {r['calibration_methods']['45']['selected']}, לפי חלונות אימון מתגלגלים. בהדגמה: Brier {demo['brier']:.5f}, ממוצע חזוי {100*demo['prediction_mean']:.2f}%, נצפה {100*demo['prevalence']:.2f}%.",
'חלונות הכיול לבחירת שיטה הופרדו מאימון ומהערכה. לאחר הבחירה הותאמה השיטה על חלון הכיול הקיים באוקטובר. ההדגמה מוכרת, ולכן אינה הערכה עצמאית. שינוי שיטת הבחירה אינו מבטיח תיקון כיול בתקופה חדשה.',
'## רגישות לסף',table(['סף','מודל נבחר','Brier ולידציה','Brier הדגמה'],[[t,v['selected'],f"{v['metrics'][v['selected']]['brier']:.5f}",f"{r['demo'][t]['brier']:.5f}"] for t,v in r['validation'].items()]),
'## מה עדיין לא נענה','ניסוי התועלת הקודם אינו מוכיח יתרון מול המרווח הארוך; הריצה הזו אינה מחליפה אותו בטענת תועלת חדשה. עדיין נדרשת הקפאת פרוטוקול והערכה סופית באישור הצוות. סקירת הספרות, PBI, רגישות לדגימה, תלות בין ימים ושאלת זמינות המידע נשארות מתועדות. האתר והמודל שבו לא שונו.',
'## שחזור',f'`OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venv/bin/python scripts/retrospective.py <new-run-id>`','התצורה והפרוטוקול ב־configs/retrospective.json וב־docs/retrospective_protocol.md. לא נוצר אישור G4.']
(ROOT/'docs/retrospective_results.md').write_text('\n\n'.join(lines)+'\n')
print('Rendered retrospective results')
