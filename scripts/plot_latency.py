"""Render measured request times. Captions and interpretation belong in the docs."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
from matplotlib import font_manager
import matplotlib.pyplot as plt


def main():
    root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--metrics', type=Path, default=root/'docs/evaluation/latency-results.json')
    p.add_argument('--out', type=Path, default=root/'docs/evaluation/latency-comparison.png')
    p.add_argument('--lang', choices=('en','ko'), default='en')
    p.add_argument('--font', type=Path, help='Optional font; use a Korean-capable font for --lang ko')
    args = p.parse_args()
    d = json.loads(args.metrics.read_text())
    expected = d['sample_unique_units']*d['repeats']
    rows = d['measurements']
    totals, sets = {}, {}
    for provider in ('laya','llm'):
        subset = [r for r in rows if r['provider']==provider]
        keys = {(r['sample_index'],r['repeat']) for r in subset}
        if len(subset)!=expected or len(keys)!=expected or any(r['status']!='ok' for r in subset):
            raise ValueError('Incomplete, invalid or duplicate timing requests')
        if keys != {(i,r) for i in range(d['sample_unique_units']) for r in range(d['repeats'])}:
            raise ValueError('Unexpected sample IDs or repeats')
        sets[provider] = keys
        totals[provider] = sum(r['seconds'] for r in subset)
    if sets['laya']!=sets['llm']:
        raise ValueError('Unmatched sample sets')
    if args.font:
        font_manager.fontManager.addfont(args.font)
        family = font_manager.FontProperties(fname=args.font).get_name()
    else:
        family = 'DejaVu Sans'
    plt.rcParams.update({'font.family':family,'font.size':14,'axes.unicode_minus':False,
        'text.color':'#253043','axes.labelcolor':'#253043','figure.facecolor':'white'})
    devices = d['hardware']['provider_devices']
    names = ['Laya multilingual\n'+devices['laya'].upper(),d['llm']['name']+'\n'+devices['llm'].upper()]
    names = [n.replace('CUDA','GPU') for n in names]
    fig,ax = plt.subplots(figsize=(8,5))
    values = [totals['laya'],totals['llm']]
    bars = ax.bar(range(2),values,color=['#315C9D','#C28B2C'],width=.46)
    ax.set_xticks(range(2),names)
    ax.set_ylabel('Measured request time (seconds)' if args.lang=='en' else '실측 요청 시간 (초)')
    ax.set_ylim(0,max(values)*1.19)
    ax.spines[['top','right']].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis='y',color='#E7EBF0')
    for bar,value in zip(bars,values):
        ax.text(bar.get_x()+bar.get_width()/2,value+max(values)*.025,f'{value:.1f}',ha='center',fontsize=16)
    fig.tight_layout(pad=1.6)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(args.out,dpi=200)
    plt.close(fig)
    print(json.dumps({'sample_seconds':totals,'ratio_llm_over_laya':totals['llm']/totals['laya']}))


if __name__=='__main__':
    main()
