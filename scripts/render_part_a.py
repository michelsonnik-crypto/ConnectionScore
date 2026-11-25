"""Render Hebrew academic drafts from completed, explicitly selected run outputs."""
from pathlib import Path
import argparse,json,shutil
ROOT=Path(__file__).resolve().parents[1]

def read(path):return json.loads(path.read_text())
def pct(v):return f'{100*v:.2f}%'
def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rows])
def main():
 p=argparse.ArgumentParser();p.add_argument('--data-run',required=True);p.add_argument('--model-run',required=True);args=p.parse_args()
 data=ROOT/'reports/runs'/args.data_run;model=ROOT/'reports/runs'/args.model_run
 f,a,r,dm,m,mm=map(read,[data/'feasibility.json',data/'analysis.json',data/'rebuild.json',data/'run.json',model/'models.json',model/'run.json'])
 if not all(r['split_hashes_match'].values()) or m['status']!='complete':raise ValueError('Incomplete/unverified runs')
 if dm['test_accessed'] or mm['test_accessed']:raise ValueError('Unexpected TEST access')
 docs=ROOT/'docs';part=docs/'part_a';part.mkdir(exist_ok=True)
 def provenance(meta,filename):
  return f"מקור כל התוצאות המספריות להלן: ריצה `{meta['run_id']}`, commit `{meta['commit']}`, פלט `reports/runs/{meta['run_id']}/{filename}`. עיגול לצורכי הצגה בלבד; הערכים המלאים בפלט. ספים, שעות וחלונות הם הגדרות מהתצורה."
 dsource=provenance(dm,'feasibility.json');asource=provenance(dm,'analysis.json');msource=provenance(mm,'models.json')
 def write(name,lines): (docs/name).write_text('\n\n'.join(lines)+'\n')
 write('01_feasibility.md',['# הוכחת היתכנות — כרטיס מספרים למצגת',dsource,
  '**המחקר רטרוספקטיבי על פיתוח בלבד. מספר זוגות אינו מספר נוסעים או תצפיות עצמאיות.**',
  table(['מדד','תוצאה','מכנה/משמעות'],[
   ['רשומות טיסה גולמיות',f"{f['raw_rows']:,}",'כל קובצי ינואר–אוקטובר, כל השדות; לפני סינון וכפילויות'],
   ['עמודות בגולמי',f['raw_columns'],'ללא עמודת CSV ריקה בסוף השורה'],
   ['זוגות מועמדים',f"{f['pairs']:,}",'לאחר כללי זיווג ודגימת טיסות נכנסות'],
   ['טיסות ייחודיות בזוגות',f"{f['unique_flights_in_pairs']:,}",'לפי מזהה טיסה, לא סכום רגליים'],
   ['תכונות בסיס',f['feature_count'],'לפני הרחבת one-hot; לא כולל תוויות ומזהים'],
   ['עמודות בקובץ הזוגות',f['processed_columns'],'כולל תוויות וסטטוס'],
   ['כיסוי מקור',' עד '.join(f['raw_coverage']),'מוגדר לפי FlightDate'],
   ['כיסוי זוגות בפועל',' עד '.join(f['pair_date_coverage']),'לא כל תאריך מקור נשמר לאחר חלונות והפרדה'],
   ['ביטולי מקור',pct(f['raw_cancellation_rate']),'רשומות טיסה גולמיות'],
   ['הסטות מקור',pct(f['raw_diversion_rate']),'רשומות טיסה גולמיות']]),
  '## פיצולים',table(['פיצול','זוגות','טיסות ייחודיות בזוגות','ימים','תוויות תקינות','אי־עמידה בסף הראשי'],[[s,f"{v['pairs']:,}",f"{v['unique_flights_in_pairs']:,}",v['days'],f"{v['operated']:,}",pct(v['failure_rates']['45'])] for s,v in f['splits'].items()]),
  'הימים נספרים לפי יום יציאה מקומי של הרגל הראשונה; גבולות הפיצול נבדקים ב־UTC, ולכן תאריך מקומי סמוך לגבול עשוי להיראות שונה מהתאריך בתצורה. אין חפיפת מזהי טיסה בין הפיצולים לפי בדיקת הריצה.',
  '## עומק ורוחב הזוגות',table(['שדה מעבר','זוגות'],f['by_hub'].items()),table(['חברה מדווחת','זוגות'],f['by_carrier'].items()),table(['חודש FlightDate','זוגות'],f['by_month'].items()),
  '## רגישות לזמן מעבר',table(['תרחיש דקות','שיעור אי־עמידה בכל פיצולי הפיתוח'],[[t,pct(v)] for t,v in f['all_development_failure_rates'].items()]),
  'המכנה כאן כולל רק זוגות בסטטוס operated. זהו תיאור פיתוח משוקלל לפי מספר זוגות, לא אומדן לאוכלוסיית נוסעים ולא מדד ביצועי מודל.',
  '## נגישות ויכולת טכנולוגית',f"קובצי BTS ציבוריים וקיימים מקומית עם כתובות וטביעות ב־data/manifest.json. התהליך משתמש ב־Python, pandas, SciPy, scikit-learn ו־XGBoost. ריצת הנתונים בפועל ארכה {dm['runtime_seconds']:.1f} שניות בסביבה המתועדת ב־run.json; הזמן כולל בנייה מחדש, ביקורת ותרשימים, ואינו התחייבות למחשב אחר. האתר לא השתנה.",
  '## חסרים',table(['עמודת זוגות','חסרים','אחוז'],[[k,v['missing'],pct(v['rate'])] for k,v in f['processed_missing'].items()]),
  'חסרים בתוויות צפויים כאשר סטטוס אינו תקין; אין למלא אותם באפס. ספירת חסרי מקור נעשתה בשדות הביקורת המפורטים ב־feasibility.json בלבד, ולא נטען שכל עמודות BTS נבדקו לחסרים.',
  '## גרפים לשקופית','![זוגות לפי חודש](../reports/figures/pairs_by_month.png)\n\n![רגישות לסף](../reports/figures/failure_sensitivity.png)\n\n![שעה ושדה](../reports/figures/hour_hub.png)',
  '## מאגרים משלימים — הצעות בלבד','[TAF / Iowa Mesonet](https://mesonet.agron.iastate.edu/request/taf.php) מספק ארכיון תחזיות עם זמן הנפקה וזמן תוקף. מתאים אולי להחלטות בטווח קצר, ולא כמזג אוויר ידוע חודש מראש. [DB1B](https://www.transtats.bts.gov/DatabaseInfo.asp?DB_ID=125) ו־[OD40](https://www.bts.gov/OD-40) עשויים לתרום מסלולי כרטיסים ומשקלי ביקוש; אינם תוויות פספוס נוסע. קישור DB1B שנבדק החזיר שגיאה ולכן זמינותו לא אומתה בבדיקה זו. OD40 משנה משטר דיווח בתוך שנת הנתונים, ולכן אין לצרף תקופות בלי בדיקת סכמה וכיסוי. לא הורדו נתונים משלימים ולא התחייבנו לשילובם.',
  '## איך מסבירים בהצגה','״יש לנו מקור ציבורי שניתן לשחזר, ואנחנו יודעים להבחין בין טיסה, זוג מועמד ונוסע. התוצאה שאנחנו בודקים היא זמן מעבר קצר מסף; ביטולים והסטות נשמרים בנפרד.״'])
 # Filtering is at flight level; pair creation starts a different unit.
 funnel=[]
 for split,v in r['report']['splits'].items():
  c=v['counts'];reject=sum(v['rejections'].values())
  funnel.append([split,c['source_rows'],c['hub_source_rows'],reject,c.get('boundary_excluded',0),c.get('duplicate_flight_excluded',0),c['normalized_flights'],c['sampled_incoming_flights'],c['pairs']])
 write('02_data_quality.md',['# איכות נתונים, ניקוי ושחזור',provenance(dm,'rebuild.json'),
  '## מה נבדק בפועל','הצינור נבנה מחדש לתיקיית artifacts של הריצה. טביעות קובצי train/validation/calibration/demo זהות למקור המתועד; הקבצים הקיימים לא נדרסו. בדיקת טיסות משותפות בין הפיצולים עברה, ושחזור התווית הראשית מן הגולמי תאם לכל זוג תקין באימון.',
  '## משפך סינון',table(['פיצול','רשומות מקור','קשורות לשדות המחקר','דחיות נרמול','מחוץ לגבול','כפילות מזהה','טיסות שנשמרו','נכנסות שנדגמו','זוגות'],funnel),
  'אוקטובר נסרק בנפרד לכיול ולהדגמה: אסור לסכום את רשומות המקור בשתי השורות כדי לתאר גודל מאגר. בשלב הזיווג יחידת הספירה משתנה מטיסה לזוג; מספר זוגות אינו יתרת שורות מהשלב הקודם.',
  '## סיבות דחייה',table(['פיצול','סיבה','רשומות'],[[s,k,n] for s,v in r['report']['splits'].items() for k,n in v['rejections'].items()]),
  '## כללי טיפול והנמקה',table(['בעיה','טיפול','מה לא עושים'],[
   ['hhmm וחצות','2400 מועבר ליום הבא; משך מתוכנן בונה הגעה ב־UTC','לא מחסרים מספרי hhmm'],
   ['אזורי זמן','מיפוי IANA ייחודי ובדיקת התאמה לשעון BTS','לא מניחים שכל שדות התעופה באותו אזור'],
   ['מעבר שעון קיץ','דחיית שעה מקומית עמומה או לא קיימת','לא בוחרים offset בשקט'],
   ['רשומה כפולה','מזהה לוח זמנים יציב; כפילות בתוך פיצול מוחרגת','לא סופרים אותה פעמיים'],
   ['ביטול/הסטה','סטטוס נפרד ותווית חסרה','לא הופכים לתווית הצלחה או כשל של מרווח'],
   ['זמן בפועל לא עקבי','סטטוס invalid_actual_time או דחייה לפי שלב','לא מתקנים בעזרת ניחוש'],
   ['איחור חריג אמיתי','נשמר אם הוא בתוך גבולות החלוקה','לא מוחקים קיצון רק בגלל IQR'],
   ['גבולות פיצול','מרווח יומיים ובדיקת כל זמני הטיסה','לא משתפים מזהי טיסה בין קבוצות']]),
  'בחיבור בתוך אותו שדה אפשר להשוות זמנים מקומיים כשיום הוגדר נכון; ייצוג UTC נבחר לאחידות בין רגליים, חצות וגבולות מחקר. זמן הגעה בפועל משפיע על סינון גבולות הפיצול; זו מגבלת בחירת אוכלוסייה שיש לדווח, ואינה תכונת מודל.',
  '## זרימת הצינור','```mermaid\nflowchart TD\n A[מקורות פיתוח מאומתים] --> B[סינון לשדות המחקר]\n B --> C[נרמול זמן ובדיקות עקביות]\n C --> D[חלונות זמן ומניעת חפיפה]\n D --> E[מניעת כפילויות ודגימת נכנסות]\n E --> F[זיווג לפי שדה וחברה ומרווח]\n F --> G[סטטוס ותוויות נפרדות]\n G --> H[קובצי פיתוח וטביעות שחזור]\n```',
  '## תוצאה לצוות','״הניקוי הוא מערכת כללים מנומקת, לא מחיקה של כל שורה בעייתית. אנחנו שומרים סטטוסים ומכנים ומראים כמה רשומות עברו כל שלב.״'])
 dictionary=[['first_id / second_id','hash של לוח הטיסה','FlightDate, חברה, מספר, שדות ויציאה מתוכננת','קישור בלבד'],['departure_date','יום יציאה מקומי של הרגל הראשונה','FlightDate','פיצול/קיבוץ'],['origin / hub / destination','מסלול זוג הטיסות','Origin/Dest','קלט'],['carrier','חברה מדווחת משותפת','Reporting_Airline','קלט'],['gap_minutes','מרווח מתוכנן בדקות','יציאה שנייה פחות הגעה ראשונה, UTC','קלט'],['duration_minutes','משך הנסיעה המתוכנן','הגעה שנייה פחות יציאה ראשונה','קלט'],['departure_hour','שעת יציאה מקומית ראשונה','CRSDepTime','מקור לתכונה מחזורית'],['weekday / month','יום/חודש המראה ב־UTC','חותמת יציאה מתוכננת','מקור לתכונה מחזורית'],['status','מצב זוג לפי שתי הרגליים','Cancelled/Diverted ועקביות זמנים','סטטוס בלבד'],['label_30 / label_45 / label_60','אי־עמידה בסף; חסר במצב לא תקין','הגעה בפועל ראשונה מול יציאה מתוכננת שנייה','תווית בלבד'],['first_arrival_delay','איחור הגעה ראשונה','ArrDelay','ניתוח/תוצאה בלבד'],['second_departure_delay','איחור יציאה שנייה','DepDelay','תווית חלופית בלבד'],['hub_arrival_hour','שעת הגעה מתוכננת מקומית לשדה מעבר','CRSArrTime/תאריך ו־IANA','ניתוח נוסף; לא קלט במודל הנוכחי'],['same_tail','אותו זנב נצפה בשתי הרגליים','Tail_Number','אבחון בלבד'],['remaining_actual','מרווח עד יציאה בפועל','gap + DepDelay שנייה − ArrDelay ראשונה','תווית חלופית בלבד']]
 write('02_data_dictionary.md',['# מילון נתונים ותפקידי עמודות','שמות עמודות באנגלית נשמרים כלשונם. רשומת זוג אינה רשומת נוסע. התכונות המורשות בפועל נאכפות ב־`safety.assert_features`.',table(['עמודה','משמעות','מקור/חישוב','שימוש מותר'],dictionary),'העמודות הנוספות לניתוח אינן מתווספות לקובצי הזוגות הקיימים או לאפליקציה. דוגמה ממשית: `reports/runs/'+dm['run_id']+'/input_examples.csv`. מפרט התכונות המחזוריות המלא: [רשומת הקלט](04_input_record_and_plan.md).'])
 comparisons=a['comparisons']
 write('03_analysis.md',['# ניתוח תיאורי והיסקי — אימון בלבד',asource,
  '## אוכלוסייה וכללי הסקה',f"נותחו {a['operated_pairs']:,} זוגות אימון עם תווית תקינה. ההשוואות העיקריות מוגבלות למרווח מתוכנן של 60–120 דקות. הדגימה לרווחי הסמך בוחרת ימים שלמים עם החזרה ושומרת את כל הזוגות ביום. זוגות משותפים אינם תצפיות עצמאיות. הימים לפי FlightDate הראשונה, ולכן חיבור לילה עלול לחצות יום; תלות בין ימים אינה נפתרת במלואה.",
  '## מה רואים בנתונים',table(['השוואה B מול A','שיעור A','שיעור B','הפרש בנקודות אחוז','רווח סמך bootstrap'],[[c['name'],pct(c['rate_a']),pct(c['rate_b']),f"{100*c['difference_b_minus_a']:.2f}",f"{100*c['interval_95'][0]:.2f} עד {100*c['interval_95'][1]:.2f}"] for c in comparisons]),
  'נמצא קשר בין שדה/שעה ובין הסיכון גם בתוך טווח מרווח מוגבל. אין להסיק ששדה או שעה גורמים להבדל: הרכב מסלולים, חברות ומרווח מדויק עדיין משתנה. שעת הניתוח היא הגעה מתוכננת לשדה המעבר, ולא שעת היציאה של הרגל הראשונה.',
  '### בדיקת טווחים צרים',table(['מרווח דקות','הפרש ORD−ATL בנקודות אחוז','רווח סמך'],[[str(c['gap_band']),f"{100*c['difference_b_minus_a']:.2f}",f"{100*c['interval_95'][0]:.2f} עד {100*c['interval_95'][1]:.2f}"] for c in a['narrow_gap_comparisons']]),
  'הבדיקה מצמצמת ערבוב לפי מרווח אך אינה מודל מותאם לכל מאפייני המסלול. זו בדיקת גישוש על אימון, לא השערה מאששת שנרשמה לפני חשיפה לכל נתוני הפיתוח.',
  '## גרפים ותובנות','![איחורים](../reports/figures/arrival_delay.png)\n\nההתפלגות אינה סימטרית; הקצוות אינם נמחקים. הגרף מגביל את ציר התצוגה בלבד.',
  '![שעה ושדה](../reports/figures/hour_hub.png)\n\nהקשר בין שעה לסיכון שונה בין שדות; הגרף הזה אינו מחזיק את המרווח קבוע, ולכן ההשוואות בטבלה נדרשות בנפרד.',
  '![מתאמים](../reports/figures/correlation.png)\n\nזהו תיאור של זוגות אימון. משתני תוצאה מופיעים במפת המתאם לצורך הבנה בלבד ואינם מתווספים לקלט המודל.',
  '![רווחי סמך](../reports/figures/daily_effects.png)\n\nרווחים מתקבלים מדגימת ימים, ולא מדגימת כל זוג כאילו היה עצמאי.',
  '## שיטות דרגות — מדוע ומה מגבלותיהן',
  'איחורים מוטים ובעלי זנב, ולכן אין להניח נורמליות אוטומטית. מבחן דרגות גם הוא דורש הנחות: Mann–Whitney ו־Kruskal–Wallis שנשמרו בפלט הם אבחונים משלימים בלבד, משום שקבוצות השדה/השעה חולקות ימים ומערכת תעופה. **אין להשתמש בערכי ה־p שלהם כהוכחה להבדל תחת עצמאות.** Wilcoxon על ימים מזווגים מתאים יותר למבנה ההשוואה, אך גם הוא מוגבל בסימטריית הפרשים ובתלות בזמן. ההפרש ורווח הימים הם התוצאה המרכזית. בפלט נשמר תיקון Holm למשפחת מבחני הדרגות, שאינו מתקן הפרת הנחות.',
  f"Spearman על ממוצעים יומיים של טיסות נכנסות ייחודיות נתן rho={a['daily_spearman']['rho']:.3f}. אין לפרש אותו כמתאם בין כל זוג למאפייניו או כראיה שאין קשר בכל רמת פירוט; בחירת מועמד אחד לטיסה משנה את יחידת הניתוח. ערך p הנאיבי נשמר בפלט ואינו מסקנת ההסקה הראשית.",
  '## רגישות להגדרת ההמראה השנייה',table(['סף','אי־עמידה מול יציאה מתוכננת','מול יציאה בפועל','שיעור שינוי תווית'],[[t,pct(v['primary_rate']),pct(v['actual_departure_rate']),pct(v['disagreement_rate'])] for t,v in a['actual_departure_sensitivity'].items()]),
  'בנתונים אלה שימוש בהמראה בפועל מפחית את שיעור אי־העמידה הכולל, אך גם יציאה בפועל אינה מועד סגירת השער. אין להסיק שהמדד הראשי הוא תמיד חסם עליון לסיכון פספוס של נוסע.',
  '## מספר זנב',table(['אותו זנב נצפה','זוגות','אי־עמידה ראשית','אי־עמידה מול יציאה בפועל'],[[k,v['pairs'],pct(v['primary_failure_rate']),pct(v['actual_departure_failure_rate'])] for k,v in a['same_tail'].items()]),
  'הבדל בין שתי הגדרות הזמן בולט בזוגות אותו מטוס: איחור ברגל הראשונה עשוי להתלוות לאיחור בשנייה. זו אסוציאציה, אינה הבטחת המתנה לנוסע. הכלל הקיים מחריג אותו מספר טיסה ולכן אין כאן כיסוי מלא של סבבי מטוסים.',
  '## כיצד מסבירים למרצה','״אנחנו בודקים אם שעה ושדה מוסיפים מידע מעבר לזמן ההמתנה. מציגים גודל הבדל ורווח סמך, שומרים תלות בתוך יום, ובודקים עד כמה שינוי הגדרת התוצאה משנה את התמונה.״'])
 write('04_model_results.md',['# ניסוי מודלים וכיול — פיתוח בלבד',msource,
  '**המודלים הורצו מחדש לתיקיית artifacts נפרדת. האתר והמודל שבו לא הוחלפו. תוצאות demo אינן TEST.**',
  '## סינון על חלונות זמן',table(['תצורה','ממוצע Brier בסינון'],[[k,f"{v['mean_brier']:.5f}" if v['mean_brier'] is not None else 'נכשל — ראו פלט'] for k,v in m['screen'].items()]),
  '## ולידציה — תרחיש ראשי',table(['מודל','Brier','ROC-AUC','Average Precision'],[[k,f"{v['brier']:.5f}",f"{v['roc_auc']:.4f}",f"{v['average_precision']:.4f}"] for k,v in m['validation']['45']['metrics'].items()]),
  f"נבחר {m['validation']['45']['selected']} לפי Brier בוולידציה. זהו שיפור נקודתי בפיתוח, לא הוכחת יתרון על תקופה עצמאית או שימוש תפעולי. היקפי האימון/הוולידציה והפרמטרים המלאים בפלט.",
  '## כיול והדגמת פיתוח',table(['סף','מודל','שיטת כיול','Brier בהדגמה','שיעור נצפה'],[[t,m['validation'][t]['selected'],m['calibration'][t]['selected'],f"{v['brier']:.5f}",pct(v['prevalence'])] for t,v in m['demo'].items()]),
  '![השוואה](../reports/figures/model_comparison.png)\n\n![כיול](../reports/figures/calibration.png)',
  'כיול נבחר בחלון נפרד באוקטובר; אחריו נבדק demo מוכר. יש לבחון את הפער בין חזוי לנצפה לאורך טווחי הסיכון, ולא להסיק כיול טוב רק מ־AUC. בחירות עבר ותצורות כבר נחשפו לפיתוח, ולכן אין לכנותו ניסוי מאשש.',
  '## האם זה משפר בחירת מסלול?',table(['כלל בחירה','בחירות','תוצאות ידועות','אי־עמידה בתוצאות ידועות','משך ממוצע בדקות'],[[k,v['choices'],v['known_margin_outcomes'],pct(v['margin_failure_rate']),f"{v['mean_duration_minutes']:.1f}"] for k,v in m['decision_experiment']['policies'].items()]),
  f"בהשוואה מזווגת של סיכון נמוך מול מרווח ארוך, ההפרש הוא {100*m['decision_experiment']['paired']['difference_lowest_risk_minus_longest_gap']:.2f} נקודות אחוז, ורווח הסמך {100*m['decision_experiment']['paired']['interval_95'][0]:.2f} עד {100*m['decision_experiment']['paired']['interval_95'][1]:.2f}. הרווח כולל אפס: **אין ראיה מספקת ליתרון על כלל המרווח הארוך בתקופה זו**. אסור להציג רק את שיעורי הקבוצות השונים כהוכחת תועלת.",
  'השוואת הכללים מוגבלת לחלופות עד משך מינימלי ועוד תוספת הזמן שהוגדרה בפרוטוקול; המכנים של תוצאות ידועות שונים בין כללים. ביטולים והסטות אינם נעלמים: ספירותיהם המלאות ב־models.json. הקבוצות אינן מאגר כרטיסים מסחריים ולא נמדד מחיר.',
  '## מסקנה ניהולית','יש הצדקה להמשך המחקר: מודל הסתברות מוסיף חיזוי בפיתוח, אך קידום מוצר דורש גם כיול יציב, יתרון מעשי מול כלל פשוט ואימות זמינות בזמן. אין בסיס להבטחת קונקשן או להכרזה שהפרויקט אומת סופית.'])
 figures=ROOT/'reports/figures';figures.mkdir(exist_ok=True)
 index=[]
 for folder,meta in [(data,dm),(model,mm)]:
  for path in (folder/'figures').glob('*.png'):
   shutil.copy2(path,figures/path.name);index.append(dict(file=str((figures/path.name).relative_to(ROOT)),run_id=meta['run_id'],commit=meta['commit'],source=str(path.relative_to(ROOT))))
 (figures/'provenance.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
 manifest=dict(data_run=dm['run_id'],model_run=mm['run_id'],data_commit=dm['commit'],model_commit=mm['commit'],test_accessed=False)
 (part/'runs.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print('Rendered feasibility, quality, dictionary, analysis and model drafts from completed runs')

if __name__=='__main__':main()
