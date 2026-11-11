"""Historical delay snapshots with an explicit simulated availability policy."""
from collections import defaultdict
from datetime import date, timedelta
import calendar
import csv
import io
import json
from pathlib import Path
import zipfile
import numpy as np

HISTORY_COLUMNS=['history_route_count','history_route_mean_delay','history_route_late15_rate','history_carrier_mean_delay','history_carrier_late15_rate','history_missing']
POLICY=dict(planning_horizon_days=30,assumed_publication_lag_days=90,minimum_route_observations=20,source='Training months only',availability_verified=False)


def allowed_months(target_month,year=2025,source_months=range(1,9),policy=POLICY):
    prediction_day=date(year,target_month,1)-timedelta(days=policy['planning_horizon_days'])
    cutoff=prediction_day-timedelta(days=policy['assumed_publication_lag_days'])
    return [m for m in source_months if date(year,m,calendar.monthrange(year,m)[1])<cutoff]


def snapshots(monthly,year=2025,policy=POLICY):
    result={}
    for target in range(1,11):
        route=defaultdict(lambda:[0,0.,0])
        carrier=defaultdict(lambda:[0,0.,0])
        permitted=allowed_months(target,year,sorted(monthly),policy)
        for month in permitted:
            for key,values in monthly[month].items():
                for table,k in [(route,key),(carrier,key[0])]:
                    for i,v in enumerate(values):table[k][i]+=v
        result[target]={'routes':dict(route),'carriers':dict(carrier),'source_months':permitted}
    return result


def augment(frame,snapshot):
    out=frame.copy()
    # Use FlightDate month, not UTC month, to match the conservative month-start cutoff.
    months=out.departure_date.str.slice(5,7).astype(int)
    vectors=[]
    for month,origin,hub,carrier in zip(months,out.origin,out.hub,out.carrier):
        s=snapshot[int(month)]
        route=s['routes'].get((carrier,origin,hub),[0,0.,0])
        broad=s['carriers'].get(carrier,[0,0.,0])
        rn,rs,rl=route;cn,cs,cl=broad
        known=rn>=POLICY['minimum_route_observations']
        # Unknown rates are explicit zero plus a missing indicator, never future/global means.
        vectors.append([rn,rs/rn if known else 0,rl/rn if known else 0,cs/cn if cn else 0,cl/cn if cn else 0,int(not known)])
    out[HISTORY_COLUMNS]=np.array(vectors,dtype=float)
    return out


def collect(root):
    config=json.loads((root/'configs/research.json').read_text())
    monthly={}
    for month in config['split_months']['train']:
        totals=defaultdict(lambda:[0,0.,0])
        with zipfile.ZipFile(root/f'data/raw/bts_2025_{month:02d}.zip') as archive:
            member=next(n for n in archive.namelist() if n.endswith('.csv'))
            with archive.open(member) as f:
                for row in csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig')):
                    if row['Dest'] not in config['hubs'] or float(row['Cancelled'])!=0 or float(row['Diverted'])!=0 or not row['ArrDelay']:
                        continue
                    delay=float(row['ArrDelay'])
                    key=(row['Reporting_Airline'],row['Origin'],row['Dest'])
                    values=totals[key];values[0]+=1;values[1]+=delay;values[2]+=delay>=15
        monthly[month]=dict(totals)
        print('History source month',month,'observed flights',sum(v[0] for v in totals.values()),flush=True)
    return snapshots(monthly,config['year'])
