# מקורות נתונים והורדות בפועל

## 1. BTS — מקור הטיסות העיקרי

ספק: Bureau of Transportation Statistics, משרד התחבורה האמריקאי. מאגר Reporting Carrier On-Time Performance.

- [קובץ ינואר 2025 שהורד](https://www.transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2025_1.zip)
- [מילון השדות הרשמי שהורד](https://www.transtats.bts.gov/Fields.asp?gnoyr_VQ=FGJ)
- [אתר המאגר](https://www.transtats.bts.gov/)

קובץ ZIP מכיל CSV וקובץ readme.html של המקור. השדות כוללים תאריך, חברה מדווחת, מספר טיסה, מוצא ויעד, זמני יציאה והגעה מתוכננים ובפועל, איחורים, ביטולים והסטות.

ArrTime הוא זמן הגעה לשער; WheelsOn הוא זמן נגיעה במסלול. אין להחליף ביניהם. זמני HHMM לבדם אינם חותמות UTC. עמודות בפועל הן תוצאה או מידע בדיעבד ואסור להשתמש בהן כתכונות חיזוי מראש.

האוכלוסייה היא טיסות מדווחות במאגר, לא כל טיסות העולם. אין בו אמת מידה ציבורית על עליית נוסע לטיסת המשך, מחיר הצעה חי או צילום מלא של לוח שהיה ידוע בעת הזמנה. הימצאות זוג טיסות אינה ראיה לכרטיס שנמכר.

## 2. OurAirports — נתוני שדות תעופה

- [CSV שהורד](https://davidmegginson.github.io/ourairports-data/airports.csv)
- [מאגר המקור](https://github.com/davidmegginson/ourairports-data)
- [מילון השדות](https://ourairports.com/help/data-dictionary.html)
- [הורדות ותנאי שימוש — public domain](https://ourairports.com/data/)

כולל שמות, קודים, קואורדינטות, מדינות וסוג שדה. זהו מקור קהילתי גלובלי ותמונת מצב נוכחית, לא מרשם היסטורי רשמי. מספר הרשומות בארה״ב כולל סוגי שדות שאינם רלוונטיים לטיסות מסחריות. נדרש מיפוי אזורי זמן נפרד ואימות התאמות לקודי BTS.

## עקיבות ושחזור

`data/manifest.json` מתעד URL, זמן הורדה ב־UTC, תקופת כיסוי כשידועה, גודל ו־SHA-256 לכל קובץ. `reports/data_quality.json` מכיל ספירות וחוסרים מתוך הקבצים שהורדו בפועל.

טרם הורדו נתוני מזג אוויר, מחירים, MCT או נתונים מסחריים. אין צורך בחשבון ספק בתהליך ההורדה הנוכחי. הפצה ושימוש בהרחבות ייבדקו לפי תנאי כל מקור.

## הרחבה שבוצעה: ינואר–אוקטובר 2025

עשרת חודשי BTS הורדו בפועל. לכל חודש כתובת בתבנית הרשמית:

`https://www.transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2025_{month}.zip`

כל עשרת הקבצים נבדקים ב־ZIP, חתימה וקליטת סכמה. נובמבר ודצמבר מיועדים ל־TEST ואינם מורדים בקוד הנוכחי. תקופת אוקטובר נקראת לצורך כיול והדגמה, אך מספר טיסות המקור שלה נספר בנפרד לכל חלק בדוח; אין לסכום ספירות מקור של אוקטובר פעמיים כדי להציג גודל מאגר.

### airportsdata — מיפוי אזורי זמן

- [מקור נעול שהורד](https://raw.githubusercontent.com/mborsetti/airportsdata/dcc46ce603ca445c0d9d9e074932452ab7d8c2d8/airportsdata/airports.csv)
- [מאגר ותנאי שימוש](https://github.com/mborsetti/airportsdata)
- [רישיון MIT](https://github.com/mborsetti/airportsdata/blob/dcc46ce603ca445c0d9d9e074932452ab7d8c2d8/LICENSE)

מקור קהילתי זה משלים שדה `tz` שנעדר מ־OurAirports. בכל קוד IATA נדרש אזור זמן יחיד; חוסר או סתירה נדחים. זמני השדות עוברים בדיקת התאמה לשעון המקומי של BTS. אין לייחס לנתוני המיפוי אימות היסטורי רשמי.
