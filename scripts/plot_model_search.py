"""Export standalone research figures from measured benchmark results."""
from pathlib import Path
import json
import os
import tempfile
os.environ.setdefault("MPLCONFIGDIR",str(Path(tempfile.gettempdir())/"connectionscore-mpl"))
import numpy as np
os.environ.setdefault("XDG_CACHE_HOME",str(Path(tempfile.gettempdir())/"connectionscore-cache"))
Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True,exist_ok=True)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]

def main():
    r=json.loads((ROOT/'reports/model_search.json').read_text())
    order=sorted(r['screen'],key=lambda n:r['screen'][n]['mean_brier'])
    means=np.array([r['screen'][n]['mean_brier'] for n in order])
    low=np.array([min(f['brier'] for f in r['screen'][n]['folds']) for n in order])
    high=np.array([max(f['brier'] for f in r['screen'][n]['folds']) for n in order])
    fig,ax=plt.subplots(figsize=(11,10))
    colors=['#e77e38' if n.startswith('xgb') else '#15745d' if 'forest' in n or n=='extra_trees' else '#244661' for n in order]
    ax.barh(order,means,color=colors,alpha=.85)
    ax.errorbar(means,range(len(order)),xerr=np.array([means-low,high-means]),fmt='none',ecolor='#788995',capsize=3,label='Range across 3 temporal windows (not a confidence interval)')
    ax.invert_yaxis();ax.set_xlabel('Brier score (lower is better)');ax.set_title('Rolling-origin screening: connection-margin failure, 45-minute scenario\nJune / July / August 2025; TEST untouched',loc='left',pad=18)
    ax.legend(loc='lower right',fontsize=8);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True);fig.tight_layout()
    for ext in ['svg','png']:fig.savefig(ROOT/f'reports/model_screening.{ext}',dpi=160)
    plt.close(fig)
    if r['status']!='complete':return
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    xs=np.arange(3);width=.25
    base=json.loads((ROOT/'reports/models.json').read_text())
    axes[0].bar(xs-width,[base['demo'][str(t)]['brier'] for t in [30,45,60]],width,label='Existing calibrated baseline',color='#8499a6')
    axes[0].bar(xs,[r['demo'][str(t)]['raw']['brier'] for t in [30,45,60]],width,label='New raw model',color='#244661')
    axes[0].bar(xs+width,[r['demo'][str(t)]['calibrated_monotone']['brier'] for t in [30,45,60]],width,label='New calibrated + monotone',color='#e77e38')
    axes[0].set_xticks(xs,['30 min','45 min','60 min']);axes[0].set_ylabel('Brier score');axes[0].set_title('Development demo: prediction error');axes[0].legend(fontsize=8)
    d=r['demo']['45'];bins=d['calibrated_monotone']['calibration_bins'];rawbins=d['raw']['calibration_bins'];oldbins=base['demo']['45']['calibration_bins']
    for points,label,color in [(oldbins,'Existing baseline','#8499a6'),(rawbins,'New raw','#244661'),(bins,'New calibrated','#e77e38')]:
        axes[1].plot([b['predicted'] for b in points],[b['observed'] for b in points],marker='o',label=label,color=color)
    axes[1].plot([0,1],[0,1],linestyle='--',color='#889999',label='Perfect calibration');axes[1].set(xlim=(0,1),ylim=(0,1),xlabel='Mean predicted risk',ylabel='Observed failure rate',title='45-minute scenario: reliability');axes[1].legend(fontsize=8)
    fig.suptitle('Previously inspected October demo: diagnostic only, not TEST',fontsize=11)
    fig.tight_layout()
    for ext in ['svg','png']:fig.savefig(ROOT/f'reports/model_calibration_diagnostics.{ext}',dpi=160)
    plt.close(fig)
    print('Research figures exported.')

if __name__=='__main__':main()
