#!/usr/bin/env python3
"""Reproduce PNG charts from reviewed aggregate metrics; no raw evidence needed."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import PercentFormatter, StrMethodFormatter


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--metrics', type=Path, default=root / 'docs/evaluation/test-metrics.json')
    parser.add_argument('--out', type=Path, default=root / 'docs/evaluation')
    parser.add_argument('--font', type=Path, help='Korean-capable font file, e.g. NotoSansCJKkr-Regular.otf')
    args = parser.parse_args()
    if args.font:
        font_manager.fontManager.addfont(args.font)
        family = font_manager.FontProperties(fname=args.font).get_name()
    else:
        family = font_manager.findfont('Noto Sans CJK KR', fallback_to_default=False)
        family = font_manager.FontProperties(fname=family).get_name()
    plt.rcParams.update({'font.family': family, 'axes.unicode_minus': False,
                         'font.size': 12, 'axes.titlesize': 16, 'axes.labelsize': 12,
                         'figure.facecolor': 'white', 'axes.facecolor': 'white',
                         'text.color': '#253043', 'axes.labelcolor': '#253043',
                         'xtick.color': '#495569', 'ytick.color': '#495569'})
    d = json.loads(args.metrics.read_text())
    units, counts, choices = d['units_by_kind'], d['counts'], d['model_choice']
    assert sum(units.values()) * d['operators_per_unit'] == counts['planned']
    assert sum(choices.values()) == counts['successful']
    assert choices['candidate'] + choices['needs_data'] == sum(d['non_background_routes'].values())
    args.out.mkdir(parents=True, exist_ok=True)
    blue, gold, grey = '#315C9D', '#C28B2C', '#A4ACB8'

    def clean(ax):
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='x', color='#E7EBF0', linewidth=.8)
        ax.set_axisbelow(True)

    fig, axs = plt.subplots(1, 2, figsize=(13, 6.2), gridspec_kw={'width_ratios': [1.0, 1.35]})
    fig.suptitle('실제 메타분석 데이터: 전수 검사 범위와 완료 상태', fontsize=20, x=.06, ha='left', y=.97)
    labels = ['원본 행', '조건별 셀', '선언된 행 쌍']
    vals = [units[k] for k in ('row', 'cell', 'pair')]
    axs[0].barh(labels, vals, color=blue, height=.58)
    axs[0].invert_yaxis(); axs[0].set_xlim(0, max(vals)*1.2)
    for i, val in enumerate(vals):
        axs[0].text(val+70, i, f'{val:,}', va='center', fontsize=13)
    axs[0].set_title('검사 근거 단위 7,005개', loc='left', pad=18)
    axs[0].set_xlabel('단위 수'); axs[0].xaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}')); clean(axs[0])
    cvals = [counts[k] for k in ('successful', 'pending', 'failed')]
    axs[1].barh(['성공', '미검사', '실패'], cvals, color=[blue, gold, grey], height=.58)
    axs[1].invert_yaxis(); axs[1].set_xlim(0, counts['planned']*1.24)
    for i, val in enumerate(cvals):
        axs[1].text(val+800, i, f'{val:,}', va='center', fontsize=13)
    axs[1].set_title('단위 × 8관점 = 56,040개 판정', loc='left', pad=18)
    axs[1].set_xlabel('판정 수'); axs[1].xaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}')); clean(axs[1])
    fig.text(.06, .15, '검사 기록 검증: 통과 · 100% 완료   |   구체적인 연구 질문 발굴 품질: 현재 구현 미달', fontsize=13, color='#253043')
    fig.text(.06, .085, '로컬 Laya multilingual · 2026-10-01 · 행 쌍은 사전에 선언한 조건 안의 모든 쌍', fontsize=11)
    fig.text(.06, .045, '경과 143.6분은 중단·재개·검증 포함. 전수 기록 완료는 가설의 타당성 검증이 아닙니다.', fontsize=11)
    fig.subplots_adjust(left=.10, right=.96, top=.78, bottom=.32, wspace=.38)
    fig.savefig(args.out/'inspection-coverage.png', dpi=220); plt.close(fig)

    fig, ax = plt.subplots(figsize=(13, 7.6))
    fig.suptitle('모델 판정 분포', fontsize=22, x=.06, ha='left', y=.97)
    fig.text(.06, .90, '분모: 각 근거 단위 × 8관점의 판정 수. 서로 다른 연구 주제의 개수가 아닙니다.', fontsize=12)
    keys = ['candidate', 'needs_data', 'background']
    names = ['후보 표시', '추가 자료 필요', '배경']
    colors = [blue, gold, grey]
    rowkeys = ['row', 'cell', 'pair']
    totals = [sum(d['choices_by_kind'][k].values()) for k in rowkeys]
    left = [0.0]*3
    for key, name, color in zip(keys, names, colors):
        widths = [d['choices_by_kind'][k].get(key, 0) / n * 100 for k, n in zip(rowkeys, totals)]
        ax.barh(range(3), widths, left=left, color=color, label=name, height=.55,
                edgecolor='white', linewidth=.8)
        for i, width in enumerate(widths):
            if width >= 6:
                ax.text(left[i]+width/2, i, f'{width:.1f}%', ha='center', va='center',
                        color='white' if key=='candidate' else '#253043', fontsize=12)
        left = [a+b for a,b in zip(left, widths)]
    ax.set_yticks(range(3), [f'{label}\n(n={n:,} 판정)' for label,n in zip(labels,totals)])
    ax.invert_yaxis(); ax.set_xlim(0,100); ax.set_xlabel('각 대상의 판정 비율')
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=100)); clean(ax)
    ax.legend(loc='lower left', bbox_to_anchor=(0, 1.02), ncol=3, frameon=False)
    headers = ['검사 대상', *names, '합계']
    rows = [[label, *(f"{d['choices_by_kind'][k].get(c,0):,}" for c in keys), f'{n:,}']
            for label,k,n in zip(labels,rowkeys,totals)]
    rows.append(['전체', *(f'{choices[c]:,}' for c in keys), f"{counts['successful']:,}"])
    table_ax = fig.add_axes([.08,.21,.86,.20]); table_ax.axis('off')
    table = table_ax.table(cellText=rows, colLabels=headers, cellLoc='center', loc='center', bbox=[0,0,1,1])
    table.auto_set_font_size(False); table.set_fontsize(11)
    for (r,c), cell in table.get_celld().items():
        cell.set_edgecolor('#E1E6EC'); cell.set_linewidth(.6)
        if r==0: cell.set_facecolor('#F0F3F7'); cell.set_text_props(weight='bold')
    fig.text(.06,.13, '후보 표시 3,722건 + 추가 자료 필요 51,842건 → 보고서에서는 모두 ‘추가 확인’으로 분류', fontsize=12)
    fig.text(.06,.085, '연구 가설 분류 0건은 데이터에 연구 질문이 없다는 뜻이 아닙니다. 분류 구현의 결함이 확인됐습니다.', fontsize=11)
    fig.text(.06,.045, '선택 확률은 과학적 진실·새로움의 확률이 아닙니다. 문헌 및 신규성 검토는 미완료입니다.', fontsize=11)
    fig.subplots_adjust(left=.18, right=.94, top=.77, bottom=.50)
    fig.savefig(args.out/'model-decisions.png', dpi=220); plt.close(fig)
    print('PNG graphs reproduced from aggregate metrics')


if __name__=='__main__':
    main()
