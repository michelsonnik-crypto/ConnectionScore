"""Stream and validate the source files; output real counts, never sample scores."""
from pathlib import Path
from collections import Counter
import csv
import io
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ["FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline", "Origin", "Dest",
          "CRSDepTime", "CRSArrTime", "DepTime", "ArrTime", "ArrDelay", "Cancelled", "Diverted", "CRSElapsedTime"]


def main():
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    processed = ROOT / "data/processed"
    processed.mkdir(exist_ok=True)
    dates, origins, destinations, carriers, missing = (Counter() for _ in range(5))
    hubs = {h: Counter() for h in ("ATL", "ORD", "DFW")}
    total = cancelled = diverted = delayed = arrival_observed = 0
    seen, duplicates = set(), 0
    with zipfile.ZipFile(ROOT / "data/raw/bts_2025_01.zip") as archive:
        assert archive.testzip() is None, "Corrupted ZIP"
        member = next(n for n in archive.namelist() if n.endswith(".csv"))
        with archive.open(member) as stream, (processed / "hub_flights_2025_01.csv").open("w", newline="") as out:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"))
            assert set(FIELDS) <= set(reader.fieldnames), "Source schema changed"
            writer = csv.DictWriter(out, fieldnames=FIELDS)
            writer.writeheader()
            columns = [x for x in reader.fieldnames if x]
            for row in reader:
                total += 1
                dates[row["FlightDate"]] += 1
                origins[row["Origin"]] += 1
                destinations[row["Dest"]] += 1
                carriers[row["Reporting_Airline"]] += 1
                for field in FIELDS:
                    missing[field] += not bool(row[field].strip())
                cancelled += float(row["Cancelled"] or 0) == 1
                diverted += float(row["Diverted"] or 0) == 1
                if row["ArrDelay"]:
                    arrival_observed += 1
                    delayed += float(row["ArrDelay"]) >= 15
                key = tuple(row[f] for f in ("FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline", "Origin", "Dest", "CRSDepTime"))
                duplicates += key in seen
                seen.add(key)
                if row["Origin"] in hubs or row["Dest"] in hubs:
                    writer.writerow({f: row[f] for f in FIELDS})
                for hub, counts in hubs.items():
                    counts["departures"] += row["Origin"] == hub
                    counts["arrivals"] += row["Dest"] == hub
    with (ROOT / "data/raw/airports.csv").open(newline="") as f:
        airports = list(csv.DictReader(f))
    us = [r for r in airports if r["iso_country"] == "US"]
    bts_airports = set(origins) | set(destinations)
    mapped = {r["iata_code"] for r in airports if r["iata_code"]} & bts_airports
    quality = dict(flight_rows=total, source_columns=len(columns), start=min(dates), end=max(dates),
                   days=len(dates), carriers=len(carriers), airports=len(bts_airports),
                   cancelled=cancelled, diverted=diverted, observed_arrival_delay=arrival_observed,
                   arrival_delay_at_least_15_minutes=delayed,
                   duplicate_candidate_keys=duplicates, missing=dict(missing), hubs={k:dict(v) for k,v in hubs.items()},
                   airport_rows=len(airports), us_airport_rows=len(us),
                   bts_airports_with_iata_match=len(mapped), unmatched_bts_airports=sorted(bts_airports-mapped),
                   fields=columns)
    (reports / "data_quality.json").write_text(json.dumps(quality, indent=2) + "\n")
    lines = ["# דוח נתונים ראשוני — ConnectionScore", "", "הורדה בפועל: 11 בנובמבר 2026. תקופת טיסות: ינואר 2025.", "",
             f"- טיסות מדווחות: **{total:,}**; {len(columns)} שדות מקור שאינם ריקים בשם.",
             f"- כיסוי: {min(dates)} עד {max(dates)}, {len(dates)} ימים, {len(carriers)} חברות מדווחות ו־{len(bts_airports)} שדות תעופה.",
             f"- ביטולים: {cancelled:,}; הסטות: {diverted:,}. אין לחבר ספירות אלה בלי לבדוק חפיפה.",
             f"- רשומות עם ArrDelay: {arrival_observed:,}; מתוכן איחור של 15 דקות ומעלה: {delayed:,} ({delayed/arrival_observed:.2%}).",
             "- זהו שיעור בין רשומות עם איחור הגעה ידוע בחודש זה, לא שיעור פספוס קונקשנים ולא נתון שנתי.",
             f"- מפתחות טיסה מועמדים כפולים: {duplicates:,}.", "", "## שדות מעבר מועמדים", "", "| שדה | יוצאות | נכנסות |", "|---|---:|---:|"]
    lines += [f"| {h} | {v['departures']:,} | {v['arrivals']:,} |" for h,v in hubs.items()]
    lines += ["", "## חוסרים בשדות נבחרים", "", "| שדה | חסרים | שיעור מכל הרשומות |", "|---|---:|---:|"]
    lines += [f"| {f} | {missing[f]:,} | {missing[f]/total:.2%} |" for f in FIELDS]
    lines += ["", "חוסרי הגעה כוללים מצבים תפעוליים כגון ביטולים; אין להמיר אותם אוטומטית לכשל.", "",
              "## מיפוי שדות תעופה", "", f"OurAirports: {len(airports):,} רשומות בעולם, {len(us):,} בארה״ב מכל סוגי השדות.",
              f"התאמת קוד IATA נמצאה עבור {len(mapped)} מתוך {len(bts_airports)} קודי BTS. התאמה בקוד אינה אימות ייחודיות או תוקף היסטורי.",
              "קובץ OurAirports הוא תמונת מצב בעת ההורדה, ואינו כולל מיפוי אזורי זמן מלא לשימוש ישיר.", "",
              "## תוצרים ומגבלות", "", "נוצר data/processed/hub_flights_2025_01.csv: טיסות הנכנסות או יוצאות מ־ATL/ORD/DFW, ללא כפילות עקב הופעה בשני שדות.",
              "הקובץ מכיל טיסות בודדות וזמני מקור מקומיים — טרם נבנו זוגות או תוויות וטרם נורמלו זמנים ל־UTC.",
              "חודש אחד מספיק לבדיקת קליטה; הוא אינו מספיק לביסוס ביצועי מודל, עונתיות או תועלת.",
              "אין כאן מודל מאומן או תחזיות. נדרשים מיפוי אזורי זמן, טיפול בחצות, הרחבת התקופה ופיצול כרונולוגי לפני אימון.",
              "", "ראו docs/sources.md למקורות ו־data/manifest.json לתאריך הורדה וחתימות SHA-256.", ""]
    (reports / "data_quality.md").write_text("\n".join(lines))
    print(json.dumps({k:v for k,v in quality.items() if k != "fields"}, indent=2))


if __name__ == "__main__":
    main()
