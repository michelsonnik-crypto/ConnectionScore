"""BTS connection construction. Actual outcomes never determine candidate eligibility."""
from __future__ import annotations
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from zoneinfo import ZoneInfo
import csv
import gzip
import hashlib
import io
import json
import zipfile

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]


def hhmm(value: str) -> int:
    n = int(value)
    if n == 2400:
        return 1440
    h, m = divmod(n, 100)
    if not 0 <= h < 24 or not 0 <= m < 60:
        raise ValueError('invalid_hhmm')
    return 60 * h + m


def local_to_utc(day: str, value: str, tz: str) -> datetime:
    naive = datetime.fromisoformat(day) + timedelta(minutes=hhmm(value))
    zone = ZoneInfo(tz)
    candidates = set()
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if candidate.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(candidate)
    if len(candidates) != 1:
        raise ValueError('ambiguous_or_nonexistent_local_time')
    return candidates.pop()


def clock_matches(stamp: datetime, clock: str, tz: str) -> bool:
    local = stamp.astimezone(ZoneInfo(tz))
    return local.hour * 60 + local.minute == hhmm(clock) % 1440


def flight_id(row):
    return hashlib.sha256('|'.join(row[k] for k in ('FlightDate', 'Reporting_Airline', 'Flight_Number_Reporting_Airline', 'Origin', 'Dest', 'CRSDepTime')).encode()).hexdigest()[:24]


def normalize(row, timezones):
    origin, dest = row['Origin'], row['Dest']
    dep = local_to_utc(row['FlightDate'], row['CRSDepTime'], timezones[origin])
    elapsed = float(row['CRSElapsedTime'])
    if elapsed <= 0 or elapsed > 24*60:
        raise ValueError('invalid_scheduled_duration')
    arr = dep + timedelta(minutes=elapsed)
    if not clock_matches(arr, row['CRSArrTime'], timezones[dest]):
        raise ValueError('scheduled_arrival_clock_mismatch')
    cancelled = float(row['Cancelled']) == 1
    diverted = float(row['Diverted']) == 1
    status = 'cancelled' if cancelled else 'diverted' if diverted else 'operated'
    actual = None
    if status == 'operated':
        if not row['ArrDelay'] or not row['ArrTime']:
            status = 'missing'
        else:
            actual = arr + timedelta(minutes=float(row['ArrDelay']))
            if not clock_matches(actual, row['ArrTime'], timezones[dest]):
                status, actual = 'invalid_actual_time', None
    return dict(id=flight_id(row), date=row['FlightDate'], carrier=row['Reporting_Airline'],
                number=row['Flight_Number_Reporting_Airline'], origin=origin, dest=dest,
                dep=dep, arr=arr, actual=actual, status=status,
                hour=hhmm(row['CRSDepTime'])//60 % 24, month=dep.month, weekday=dep.weekday())


def outcome(first, second, threshold):
    statuses = {first['status'], second['status']}
    for value in ('cancelled', 'diverted', 'invalid_actual_time', 'missing'):
        if value in statuses:
            return value, None
    if first['actual'] is None:
        return 'missing', None
    remaining = (second['dep'] - first['actual']).total_seconds()/60
    return 'operated', int(remaining < threshold)


def permitted(flight, start, end, embargo):
    # Both scheduled and observed arrivals must remain within this partition.
    # This avoids sharing delayed flights across split boundaries.
    lo = datetime.combine(start + timedelta(days=embargo), datetime.min.time(), UTC)
    hi = datetime.combine(end - timedelta(days=embargo), datetime.min.time(), UTC)
    times = [flight['dep'], flight['arr']]
    if flight['actual'] is not None:
        times.append(flight['actual'])
    return all(lo <= t < hi for t in times)


def build():
    config = json.loads((ROOT/'configs/research.json').read_text())
    raw = ROOT/'data/raw'
    processed = ROOT/'data/processed'
    reports = ROOT/'reports'
    processed.mkdir(exist_ok=True)
    reports.mkdir(exist_ok=True)
    with (raw/'airport_timezones.csv').open() as f:
        records = list(csv.DictReader(f))
    zones = defaultdict(set)
    for row in records:
        if row['iata'] and row['tz']:
            zones[row['iata']].add(row['tz'])
    timezones = {k:next(iter(v)) for k,v in zones.items() if len(v)==1}
    report = {'configuration':config, 'splits':{}, 'test':{'status':'locked_not_downloaded_not_opened','months':config['split_months']['test']}}
    shared_ids = set()
    fields = ['first_id','second_id','departure_date','origin','hub','destination','carrier','gap_minutes','duration_minutes','departure_hour','weekday','month','status','label_30','label_45','label_60']
    sample = []
    for split in ('train','validation','calibration','demo'):
        months = config['split_months'][split]
        start, end = map(date.fromisoformat, config['split_windows'][split])
        stats = Counter()
        rejects = Counter()
        incoming, outgoing = [], defaultdict(list)
        flight_ids = set()
        for month in months:
            archive_path = raw/f"bts_{config['year']}_{month:02d}.zip"
            with zipfile.ZipFile(archive_path) as archive:
                member = next(n for n in archive.namelist() if n.endswith('.csv'))
                with archive.open(member) as f:
                    for row in csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig')):
                        stats['source_rows'] += 1
                        if not ({row['Origin'],row['Dest']} & set(config['hubs'])):
                            continue
                        stats['hub_source_rows'] += 1
                        try:
                            flight = normalize(row,timezones)
                        except (ValueError, KeyError) as exc:
                            rejects[str(exc)] += 1
                            continue
                        if not permitted(flight,start,end,config['embargo_days']):
                            stats['boundary_excluded'] += 1
                            continue
                        if flight['id'] in flight_ids:
                            stats['duplicate_flight_excluded'] += 1
                            continue
                        flight_ids.add(flight['id'])
                        if flight['origin'] in config['hubs']:
                            outgoing[(flight['origin'],flight['carrier'])].append(flight)
                        if flight['dest'] in config['hubs']:
                            # Sampling depends only on the scheduled flight identity.
                            if int(flight['id'],16) % config['incoming_sample_modulus'] == 0:
                                incoming.append(flight)
        assert not shared_ids.intersection(flight_ids), 'Flight leakage between partitions'
        shared_ids.update(flight_ids)
        for group in outgoing.values():
            group.sort(key=lambda f:(f['dep'],f['id']))
        indexes = {key:[f['dep'] for f in group] for key,group in outgoing.items()}
        pair_ids = set()
        active_ids = set()
        path = processed/f'connections_{split}.csv.gz'
        # Fixed gzip timestamp makes identical runs byte-reproducible.
        with path.open('wb') as binary, gzip.GzipFile(fileobj=binary,mode='wb',mtime=0,filename='') as compressed, io.TextIOWrapper(compressed,encoding='utf-8',newline='') as f:
            writer = csv.DictWriter(f,fieldnames=fields)
            writer.writeheader()
            for first in sorted(incoming,key=lambda f:(f['dep'],f['id'])):
                key = (first['dest'],first['carrier'])
                group, stamps = outgoing.get(key,[]), indexes.get(key,[])
                low = first['arr']+timedelta(minutes=config['gap_min'])
                high = first['arr']+timedelta(minutes=config['gap_max'])
                for second in group[bisect_left(stamps,low):bisect_right(stamps,high)]:
                    if first['origin']==second['dest'] or first['number']==second['number']:
                        continue
                    pair = (first['id'],second['id'])
                    assert pair not in pair_ids
                    pair_ids.add(pair)
                    active_ids.update(pair)
                    status, _ = outcome(first,second,45)
                    labels = {f'label_{t}':outcome(first,second,t)[1] for t in config['thresholds']}
                    result = dict(first_id=first['id'],second_id=second['id'],departure_date=first['date'],origin=first['origin'],hub=first['dest'],destination=second['dest'],carrier=first['carrier'],gap_minutes=int((second['dep']-first['arr']).total_seconds()/60),duration_minutes=int((second['arr']-first['dep']).total_seconds()/60),departure_hour=first['hour'],weekday=first['weekday'],month=first['month'],status=status,**labels)
                    writer.writerow(result)
                    stats['pairs'] += 1
                    stats['status_'+status] += 1
                    if status=='operated':
                        assert labels['label_30'] <= labels['label_45'] <= labels['label_60']
                        for t in config['thresholds']:
                            stats[f'fail_{t}'] += labels[f'label_{t}']
                    if split=='validation' and len(sample)<100:
                        sample.append(result)
        stats['sampled_incoming_flights'] = len(incoming)
        stats['normalized_flights'] = len(flight_ids)
        stats['flights_in_pairs'] = len(active_ids)
        report['splits'][split] = {'counts':dict(stats),'rejections':dict(rejects),'scheduled_window_start':str(start),'scheduled_window_end_exclusive':str(end),'sha256':hashlib.file_digest(path.open('rb'),'sha256').hexdigest()}
        print(split,json.dumps(dict(stats)),flush=True)
    (reports/'connections.json').write_text(json.dumps(report,indent=2)+'\n')
    # This audit sample deliberately stays out of the app (which serves predictions).
    with (reports/'connection_audit_sample.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(sample)
    return report


if __name__=='__main__':
    build()
