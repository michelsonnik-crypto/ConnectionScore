"""Paired-day inference and denominator-aware charts; no change to labels/models."""
from pathlib import Path
import sys,json,time,subprocess
from datetime import datetime,timezone
from collections import defaultdict
import csv,io
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src'),str(Path(__file__).resolve().parent)]
from part_a import ROOT,read_development,raw_archive,flight_id,savefig,dump,provenance
import numpy as np
import pandas as pd
from scipy.stats import friedmanchisquare,wilcoxon
import matplotlib.pyplot as plt


def main():
    run_id=sys.argv[1]
    out=ROOT/'reports/runs'/run_id;out.mkdir(parents=True,exist_ok=False)
    started=datetime.now(timezone.utc).isoformat();clock=time.perf_counter()
    d=read_development(ROOT/'data/processed/connections_train.csv.gz',dtype={k:'category' for k in ['origin','hub','destination','carrier','status']})
    d=d[d.status=='operated'].copy();needed=set(d.first_id);mapping={}
    for month in range(1,9):
        with raw_archive(ROOT/f'data/raw/bts_2025_{month:02d}.zip') as archive:
            member=next(n for n in archive.namelist() if n.endswith('.csv'))
            with archive.open(member) as stream:
                for row in csv.DictReader(io.TextIOWrapper(stream,encoding='utf-8-sig')):
                    if row['Dest'] not in {'ATL','ORD','DFW'}:continue
                    fid=flight_id(row)
                    if fid in needed:mapping[fid]=int(row['CRSArrTime'])//100%24
    assert needed<=mapping.keys()
    d['hub_hour']=d.first_id.map(mapping)
    grouped=d.groupby(['hub_hour','hub'],observed=True).label_45.agg(['size','sum','mean']).reset_index()
    grouped.to_csv(out/'hour_hub_denominators.csv',index=False)
    minimum_pairs=500
    displayed=grouped[grouped['size']>=minimum_pairs]
    ax=(displayed.pivot(index='hub_hour',columns='hub',values='mean')*100).plot(figsize=(9,4),marker='o')
    ax.set_xlabel('שעת הגעה מתוכננת לשדה המעבר');ax.set_ylabel('אחוז אי־עמידה')
    savefig(out,'hour_hub_supported','שעה ושדה — מוצגים רק תאים בעלי מכנה מספיק',ax)
    band=d[d.gap_minutes.between(60,120)]
    daily=band.groupby(['departure_date','hub'],observed=True).label_45.agg(['size','mean']).reset_index()
    matrix=daily.pivot(index='departure_date',columns='hub',values='mean').dropna()
    test=friedmanchisquare(*(matrix[h] for h in ['ATL','ORD','DFW']))
    atl=band[band.hub=='ATL'].copy();atl['period']=np.where(atl.hub_hour.between(6,11),'morning',np.where(atl.hub_hour.between(18,23),'evening','other'))
    times=atl[atl.period!='other'].groupby(['departure_date','period'],observed=True).label_45.mean().unstack().dropna()
    paired=wilcoxon(times.morning,times.evening)
    dump(out/'paired_tests.json',dict(minimum_pairs_for_display=minimum_pairs,excluded_display_cells=int((grouped['size']<minimum_pairs).sum()),
      friedman=dict(statistic=float(test.statistic),p=float(test.pvalue),matched_days=len(matrix),method='Friedman on matched daily hub failure rates in gap 60–120'),
      wilcoxon=dict(statistic=float(paired.statistic),p=float(paired.pvalue),matched_days=len(times),method='paired daily ATL morning/evening failure rates'),
      caveats=['Exploratory analyses; repeated use of training data','Matched days address pairing but not serial dependence between days','Wilcoxon additionally assumes symmetric daily differences for its location interpretation','Friedman compares daily ranks; it does not identify causal hub effects','Original Kruskal-Wallis/Mann-Whitney p-values are not used for independent-sample inference']))
    daily.to_csv(out/'hub_daily_rates.csv',index=False);times.to_csv(out/'atl_daily_rates.csv')
    meta=provenance(out,'diagnostics',started);meta['command']=f'.venv/bin/python scripts/part_a_diagnostics.py {run_id}';meta['runtime_seconds']=time.perf_counter()-clock;dump(out/'run.json',meta)
    print('paired diagnostics complete',out.name,flush=True)

if __name__=='__main__':main()
