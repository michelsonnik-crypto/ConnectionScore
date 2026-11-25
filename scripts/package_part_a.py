"""Create a readable RTL Word draft and a portable part-A review bundle."""
from pathlib import Path
import json,re,zipfile,shutil
ROOT=Path(__file__).resolve().parents[1]

def main():
    part=ROOT/'docs/part_a';runs=json.loads((part/'runs.json').read_text())
    data=ROOT/'reports/runs'/runs['data_run'];models=ROOT/'reports/runs'/runs['model_run']
    f=json.loads((data/'feasibility.json').read_text());a=json.loads((data/'analysis.json').read_text());m=json.loads((models/'models.json').read_text())
    ds=f"ריצה {runs['data_run']}; commit {runs['data_commit']}; פלט reports/runs/{runs['data_run']}/feasibility.json"
    ars=f"ריצה {runs['data_run']}; commit {runs['data_commit']}; פלט reports/runs/{runs['data_run']}/analysis.json"
    ms=f"ריצה {runs['model_run']}; commit {runs['model_commit']}; פלט reports/runs/{runs['model_run']}/models.json"
    c=a['comparisons'][0];c2=a['comparisons'][1];p=m['decision_experiment']['paired'];metrics=m['validation']['45']['metrics']
    text=f'''# ConnectionScore — טיוטת דוח חלק א

הנדסת תעשייה וניהול, התמחות מדעי הנתונים. גרסת עבודה לצוות, 26.11.2026.

טיוטה מבוססת הרצות פיתוח. נדרשת קריאת הצוות ואישור הגדרות מול המנחה. אין כאן תוצאות TEST, אישור תפעולי או הגשה בשם הסטודנטים.

## תקציר

הפרויקט בוחן הערכת סיכון לחיבור בין שתי טיסות פנים בארה״ב. המדד הוא אי־עמידה בזמן מעבר מוגדר, ולא פספוס נוסע בפועל. מקור הנתונים הוא BTS. בריצת השחזור נספרו {f['raw_rows']:,} רשומות טיסה גולמיות מינואר עד אוקטובר 2025, ומהן נבנו {f['pairs']:,} זוגות מועמדים לאחר סינון ודגימה. בזוגות מופיעות {f['unique_flights_in_pairs']:,} טיסות ייחודיות. מספר זוגות אינו מספר תצפיות עצמאיות.

מקור: {ds}.

נמצאו קשרים בין שדה מעבר ושעה ובין הסיכון גם בתוך טווח מרווח מוגבל. ניסוי מודלים מצא שיפור חיזוי בפיתוח לעומת בסיסים פשוטים, אך ניסוי בחירת המסלול אינו מספק ראיה ליתרון על כלל המרווח הארוך. השימוש המוצרי לפני הזמנה דורש אימות זמינות לוחות והיסטוריה בזמן. כל ההערכה הנוכחית רטרוספקטיבית.

## הבעיה, המשתמש והתועלת ההנדסית

משתמש המתכנן נסיעה משווה מסלולים לפי משך ומרווח, אך אותו מרווח עשוי להיות קשור לרמות שונות של סיכון היסטורי. מטרת ConnectionScore היא להציג הסתברות מוסברת במסגרת תחולה ברורה ולבחון אם היא מסייעת לבחירה תחת מגבלת זמן.

הערך התעשייתי־ניהולי אינו מסתכם בבניית מסווג: נדרש להגדיר תהליך החלטה, אילוץ משך, בסיס השוואה ומדד תועלת. בשלב זה אין נתוני מחיר, עלויות טיפול בנוסע או תצפיות על פספוסים אמיתיים; לכן לא מוצג חיסכון כספי מומצא.

## שאלת המחקר והיקף

באיזו מידה מאפייני לוח זמנים של זוג טיסות מנבאים שהזמן הזמין למעבר יהיה קצר מסף מוגדר? האם דירוג לפי הסיכון משפר בחירה ביחס למסלול הקצר או למרווח הארוך באותה מגבלת משך?

האוכלוסייה הנוכחית: טיסות פנים דרך ATL, ORD או DFW, באותה חברה מדווחת, עם מרווח מתוכנן של 30–240 דקות, מספרי טיסה שונים וללא חזרה למוצא. כרטיס משותף, כבודה ליעד והישארות באזור המאובטח הם הנחות תחום, שאינן מאומתות מעצם חברותה של טיסה ב־BTS. ההגדרות הן תצורת העבודה הקיימת, ולא אישור מנחה חדש.

התווית: אי־עמידה אם יציאה מתוכננת שנייה פחות הגעה בפועל לשער ראשונה קטנה מסף התרחיש. הספים בתצורה הם 30, 45 ו־60 דקות; 45 הוא הראשי. שוויון לסף הוא עמידה. ביטול והסטה הם סטטוסים נפרדים, לא כשל או הצלחה של יעד המרווח. זהו מדד תחליפי ולא MCT רשמי או תוצאת נוסע.

## מקורות נתונים והיתכנות

מקורות הטיסות, כתובות ההורדה וטביעות הקבצים מתועדים ב־data/manifest.json וב־docs/sources.md. מיפוי אזורי הזמן הוא מקור קהילתי בגרסה נעולה. המיפוי חסר את PBI, וטיסות קשורות הוחרגו; נדרש מקור מוסמך או הגדרת כיסוי מצומצם מפורשת.

בגולמי {f['raw_columns']} עמודות בעלות שם; במודל הבסיס {f['feature_count']} תכונות לפני הרחבת קידוד הקטגוריות. שיעור ביטולי המקור {100*f['raw_cancellation_rate']:.2f}% וההסטות {100*f['raw_diversion_rate']:.2f}%, עם מכנה רשומות טיסה. אין לערבב מכנה זה עם מכנה זוגות תקינים.

מקור: {ds}.

![זוגות לפי חודש](../../reports/figures/pairs_by_month.png)

הנתונים הציבוריים נגישים והצינור ניתן לשחזור. עומק הנתונים מאפשר לחקור הבדלים בין חודשים, חברות ושדות, אבל זוגות רבים חולקים טיסה ולכן נפח הקובץ אינו גודל מדגם עצמאי.

## טיפול בנתונים

הצינור ממיר hhmm לחותמות זמן מלאות, מטפל בחצות ובמעברי שעון, ממפה אזורים, בודק התאמה לזמני BTS, מסנן גבולות זמן, מונע כפילות מזהים ובונה זוגות לפי שדה וחברה. דגימת הטיסות הנכנסות נקבעת לפי מזהה לוח זמנים, ללא שימוש בתוצאה. פירוט כמויות בכל שלב מופיע ב־docs/02_data_quality.md.

בשחזור נבנו קובצי פיתוח חדשים לתיקייה נפרדת וטביעותיהם התאימו למקור. לא נדרסו נתונים גולמיים. נבדק שאין מזהי טיסה משותפים לפיצולים. תוויות חסרות לא מולאו באפס ואיחורים אמיתיים לא הוסרו רק מפני שהם קיצוניים.

החלוקה כרונולוגית: אימון בינואר–אוגוסט, ולידציה בספטמבר, כיול והדגמת פיתוח בחלונות נפרדים באוקטובר, עם מרווחי הפרדה. תאריכי FlightDate מקומיים עשויים להיות סמוכים לתאריך UTC אחר. זמן הגעה בפועל משמש גם לבדיקת גבול הפיצול; זו מגבלת בחירת אוכלוסייה שדורשת דיווח.

## סטטיסטיקה תיאורית והיסקית

בכל פיצולי הפיתוח, בקרב זוגות עם תווית תקינה בלבד, שיעורי אי־העמידה הם {100*f['all_development_failure_rates']['30']:.2f}%, {100*f['all_development_failure_rates']['45']:.2f}% ו־{100*f['all_development_failure_rates']['60']:.2f}% בהתאמה לתרחישים. אלה שיעורי תוצאה, לא ציוני המודל.

מקור: {ds}.

בנתוני האימון ובמרווח מתוכנן 60–120 דקות, ORD לעומת ATL הציג הפרש של {100*c['difference_b_minus_a']:.2f} נקודות אחוז, עם רווח סמך דגימת ימים {100*c['interval_95'][0]:.2f} עד {100*c['interval_95'][1]:.2f}. ב־ATL, ערב לעומת בוקר לפי שעת הגעה מתוכננת הציג הפרש של {100*c2['difference_b_minus_a']:.2f} נקודות אחוז, ורווח {100*c2['interval_95'][0]:.2f} עד {100*c2['interval_95'][1]:.2f}.

מקור: {ars}.

![הפרשים ורווחי סמך](../../reports/figures/daily_effects.png)

נדגמו ימים שלמים כדי לשמור תלות בין זוגות באותו יום. נוספו השוואות בטווחי מרווח צרים ומבחנים מזווגים בין ימים; יש לדווח שהם גישושיים ושתלות סדרתית וערבוב מסלולים עדיין קיימים. היעדר נורמליות אינו פוטר מבדיקת הנחות מבחן דרגות. פרטי Friedman ו־Wilcoxon ותוצאותיהם נמצאים ב־docs/03_analysis.md ובפלט הריצה הנוספת.

בניתוח הרגישות, יעד המבוסס על המראת ההמשך בפועל שינה את שיעורי אי־העמידה. נבחן גם אותו מספר זנב בשתי הרגליים. שני הנתונים הם מידע בדיעבד ומשמשים לבדיקת משמעות המדד בלבד, לא כקלט בתכנון. התוצאות אינן מוכיחות ששדה מסוים, שעה או מטוס גורמים לכשל.

## רשומת קלט וניסוי מודלים מקדים

רשומה כוללת מסלול, חברה, מרווח ומשך מתוכננים ומאפייני זמן מחזוריים. תוויות, סטטוס, איחורים, מספר זנב ומזהי טיסה נחסמים כתכונות. זמינות לוח מדויק במועד הזמנה עדיין לא הוכחה; גם השוואה כרונולוגית אינה פותרת זאת.

ניסוי ההמשך השווה מודלי בסיס, לוגיסטית, עץ, יער ו־boosting על חלונות עבר. בתרחיש הראשי, בוולידציית ספטמבר, Brier של שיעור קבוע היה {metrics['constant']['brier']:.5f}, מרווח בלבד {metrics['gap_empirical']['brier']:.5f}, לוגיסטית {metrics['logistic_c05']['brier']:.5f} ו־XGBoost {metrics['xgb_depth4']['brier']:.5f}. ערך נמוך עדיף. אין להחליף כאן חיזוי הסתברותי ב־Accuracy בלבד.

מקור: {ms}.

![השוואת מודלים](../../reports/figures/model_comparison.png)

כיול נבחר בחלון נפרד, והדגמת סוף אוקטובר משמשת אבחון פיתוח שכבר נצפה. אלה אינם ביצועי TEST. בתרחיש הראשי, ממוצע הסיכון החזוי בהדגמה הוא {100*sum(b['n']*b['predicted'] for b in m['demo']['45']['calibration_bins'])/m['demo']['45']['n']:.2f}%, לעומת {100*m['demo']['45']['prevalence']:.2f}% נצפה (מקור: אותה ריצת מודלים, ממוצע משוקלל מתאי הכיול). קיימת הערכת חסר גם לאחר כיול, ולכן המודל אינו מוכן לשימוש תפעולי. האתר ממשיך להשתמש בגרסה הקיימת, ללא החלפת מודל אוטומטית.

## תועלת, סיכונים ומשמעות ניהולית

בניסוי חלופות מדגמיות תחת אותו אילוץ משך, סיכון נמוך לעומת כלל המרווח הארוך נתן הפרש מזווג של {100*p['difference_lowest_risk_minus_longest_gap']:.2f} נקודות אחוז ורווח סמך {100*p['interval_95'][0]:.2f} עד {100*p['interval_95'][1]:.2f}. הרווח כולל אפס. לכן אין כרגע ראיה מספקת ליתרון על כלל זה, גם אם מדד החיזוי השתפר.

מקור: {ms}.

סיכונים שלא נמדדו ישירות כוללים זמני הליכה, סגירת שער, תנועת כבודה, ניידות אישית ותהליכי מכס/בידוק. כבודה שדורשת איסוף ומסירה מחדש מחייבת מסלול זמן אחר, כולל אילוץ סגירת דלפק. אין לקבוע תוספת שרירותית או להציג הסתברות המותנית בביצוע טיסות כסיכון הכולל לנסיעה. המיפוי המלא נמצא ב־docs/05_risk_scope.md.

## ספרות ותוכנית המשך

מטריצת הספרות כוללת מקורות על קישוריות נוסעים לפי אופק החלטה, עיכובי נוסעים לעומת טיסות, כיול הסתברויות ודליפת מידע. הקישורים אומתו, אך עמודת ממצאי הצוות נשארת ריקה עד קריאה ואישור. אין להציג תקציר או סיכום AI כסקירת ספרות שהסטודנטים השלימו.

לפני סיום חלק א נדרשים אישור הגדרות עם המנחה, החלטת PBI, קריאת ספרות, בדיקת תובנות וחזרות להצגה. לפני הערכה סופית נדרשת נעילת פרוטוקול והחלטת G4 חתומה; TEST נותר סגור. תוכנית המועדים והאחריות מפורטת ב־docs/part_a/status.md.

## שחזור ושימוש ב־AI

הקוד, התצורות, טביעות הקלט, גרסאות הספריות ונתיבי הפלט מתועדים לכל ריצה. make part-a מפעיל את תהליך הפיתוח עם מזהה חדש; יומן AI מתאר מה Codex יצר ומה דורש בדיקה אנושית. הצוות צריך להיות מסוגל להסביר כל כלל, שיטה ומסקנה, ולא רק להציג פלט.

## מקורות לקריאה

BTS ומיפוי אזורי זמן: docs/sources.md ו־data/manifest.json.

Guimarães et al. (2021): https://arxiv.org/abs/2111.01915

Barnhart, Fearing & Vaze (2014): https://doi.org/10.1287/opre.2014.1268

Niculescu-Mizil & Caruana (2005): https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf

Kapoor & Narayanan (2023): https://doi.org/10.1016/j.patter.2023.100804

United, דפי כבודה ותהליך שדה: קישורים ומגבלות ב־docs/05_risk_scope.md.
'''
    (part/'report_draft.md').write_text(text)
    # Word is a convenience export of the same reviewed draft; use real RTL XML.
    from docx import Document
    from docx.shared import Inches,Pt,RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    doc=Document();doc.core_properties.title='ConnectionScore — טיוטת דוח חלק א';doc.core_properties.author='ConnectionScore team';sec=doc.sections[0];sec.header.paragraphs[0].text='ConnectionScore | טיוטת עבודה לצוות'
    style=doc.styles['Normal'];style.font.name='Arial';style.font.size=Pt(11);style.paragraph_format.space_after=Pt(7)
    for style_name in ['Title','Heading 1','Heading 2']:
        doc.styles[style_name].font.name='Arial';doc.styles[style_name].font.color.rgb=RGBColor.from_string('147D92')
    def rtl(par):
        par.alignment=WD_ALIGN_PARAGRAPH.RIGHT
        el=OxmlElement('w:bidi');el.set(qn('w:val'),'1');par._p.get_or_add_pPr().append(el)
    for block in text.split('\n\n'):
        if not block.strip():continue
        image=re.fullmatch(r'!\[(.*?)\]\((.*?)\)',block.strip())
        if image:
            path=(part/image[2]).resolve();doc.add_picture(str(path),width=Inches(6));caption=doc.add_paragraph(image[1]);rtl(caption);continue
        if block.startswith('# '):par=doc.add_paragraph(block[2:].strip(),'Title')
        elif block.startswith('## '):par=doc.add_paragraph(block[3:].strip(),'Heading 1')
        else:par=doc.add_paragraph();
        if not block.startswith('#'):
            for segment in re.split(r'([A-Za-z][A-Za-z0-9_:/.,%+()= —-]*|\d[\d.,%:–-]*)',block):
                if not segment:continue
                run=par.add_run(segment);rp=run._r.get_or_add_rPr();el=OxmlElement('w:rtl');el.set(qn('w:val'),'1' if re.search('[\u0590-\u05ff]',segment) else '0');rp.append(el)
        rtl(par)
    footer=sec.footer.paragraphs[0];footer.text='טיוטה — נתוני פיתוח בלבד; נדרשת בדיקת צוות ומנחה';rtl(footer)
    exports=ROOT/'exports';exports.mkdir(exist_ok=True)
    doc.save(exports/'ConnectionScore_PartA_Draft_HE.docx')
    bundle=exports/'ConnectionScore_PartA_Review_Bundle.zip'
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as archive:
        for folder in ['docs','reports/figures','reports/runs']:
            for path in sorted((ROOT/folder).rglob('*')):
                if path.is_file():archive.write(path,str(path.relative_to(ROOT)))
        for name in ['Makefile','requirements-lock.txt','reports/source_checks_20261126.json','reports/verification_20261126.json']:
            archive.write(ROOT/name,name)
        archive.write(exports/'ConnectionScore_PartA_Draft_HE.docx','ConnectionScore_PartA_Draft_HE.docx')
    deliverables=ROOT/'deliverables';deliverables.mkdir(exist_ok=True)
    for path in [exports/'ConnectionScore_PartA_Draft_HE.docx',bundle]:shutil.copy2(path,deliverables/path.name)
    print('Created',exports/'ConnectionScore_PartA_Draft_HE.docx','and',bundle)

if __name__=='__main__':main()
