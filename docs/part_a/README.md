# ConnectionScore — חבילת העבודה לחלק א

התחילו מ־[מצב הפרויקט והמשך העבודה](status.md), [טיוטת הדוח](report_draft.md) ו־[דף ההכנה להצגה](presentation_notes.md).

| תוצר | מסמך |
|---|---|
| מפת המאגר | [שלב 0](../00_repo_map.md) |
| כרטיס נתונים לשקף | [היתכנות](../01_feasibility.md) |
| משמעות כל עמודה | [מילון](../02_data_dictionary.md) |
| כללי ניקוי ומשפך | [איכות](../02_data_quality.md) |
| גרפים ותובנות | [ניתוח](../03_analysis.md) |
| רשומה ופרוטוקול | [מפרט קלט](../04_input_record_and_plan.md) |
| השוואת מודלים וכיול | [ניסוי פיתוח](../04_model_results.md) |
| מאמרים לקריאת הצוות | [מטריצת ספרות](../05_literature_matrix.md) |
| מה מכוסה ומה לא | [מפת סיכונים](../05_risk_scope.md) |
| מבנה וקריטריונים | [שלד דוח](outline.md) |
| הסבר קצר לשיטות | [דף כלים](tools_cheatsheet.md) |
| עקיבות מספרים | [מזהי ריצות](runs.json), קובצי run.json תחת reports/runs |

## שחזור

בסביבה נקייה, Python 3.12 על Linux: צרו סביבה וירטואלית והתקינו `requirements-lock.txt`. קובצי המקור נדרשים מקומית לפי `data/manifest.json`. אם חסרים, ההורדה היא פעולה נפרדת: `python scripts/fetch_data.py --research`; אין הורדת TEST. קובץ מקור קיים שאינו תואם לטביעה אינו נדרס.

```bash
make part-a RUN_ID=my-new-run
```

יש לבחור מזהה חדש בכל שחזור; פקודה זו מסרבת לדרוס תיקיית ריצה קיימת. היא מפיקה נתונים, מודלים וניתוח נוסף לתיקיות חדשות, ואז מעדכנת מסמכי טיוטה וגרפים בלבד. היא אינה מפרסמת אתר, אינה מעדכנת את המודל באפליקציה ואינה פותחת TEST. טביעות הנתונים המעובדים הקיימים חייבות להתאים לתיעוד המקור.

להפקת המסמכים מחדש מהריצות שכבר בוצעו, ללא אימון או קריאת טיסות:

```bash
.venv/bin/python scripts/render_part_a.py --data-run part-a-data-20261126-01 --model-run part-a-models-20261126-01 --diagnostics-run part-a-diagnostics-20261126-01
```

החבילה היא בסיס הנדסי ואקדמי מבוסס הרצות. קריאת ספרות, אישורי מנחה, חזרות והגשה נשארים פעולות של הצוות. האתר והמודל שבו לא שונו.

## קבצים להורדה

[דוח Word בעברית](../../deliverables/ConnectionScore_PartA_Draft_HE.docx) · [כל חבילת הסקירה ב־ZIP](../../deliverables/ConnectionScore_PartA_Review_Bundle.zip). אלו טיוטות לבדיקה, לא הגשה סופית. ליצירה מחדש התקינו requirements-documents.txt והריצו scripts/package_part_a.py.

[סדר ה־PRs והמשימות ב־GitHub](github_workflow.md).
