"""Plot measured matched choice-task latency and separately labelled projection."""
import argparse
import json
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
import matplotlib.pyplot as plt


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, default=root / "docs/evaluation/latency-results.json")
    parser.add_argument("--out", type=Path, default=root / "docs/evaluation/latency-comparison.png")
    parser.add_argument("--font", required=True, type=Path)
    args = parser.parse_args()
    data = json.loads(args.metrics.read_text())
    rows = data["measurements"]
    expected = data["sample_unique_units"] * data["repeats"]
    for provider in ("laya", "llm"):
        subset = [r for r in rows if r["provider"] == provider]
        if len(subset) != expected or any(r["status"] != "ok" for r in subset):
            raise ValueError("Incomplete or invalid comparison cannot be plotted as valid throughput")
        keys = {(r["sample_index"], r["repeat"]) for r in subset}
        if len(keys) != expected:
            raise ValueError("Duplicate timing requests")
    if {(r["sample_index"], r["repeat"], r["kind"]) for r in rows if r["provider"] == "laya"} != {(r["sample_index"], r["repeat"], r["kind"]) for r in rows if r["provider"] == "llm"}:
        raise ValueError("Unmatched input sets")
    totals = {p: sum(r["seconds"] for r in rows if r["provider"] == p) for p in ("laya", "llm")}
    means = {p: {k: statistics.mean(r["seconds"] for r in rows if r["provider"] == p and r["kind"] == k and r["repeat"] == 0)
                 for k in data["population_units"]} for p in totals}
    projected = {p: sum(means[p][k] * n for k, n in data["population_units"].items()) / 60 for p in totals}
    font_manager.fontManager.addfont(args.font)
    plt.rcParams.update({"font.family": font_manager.FontProperties(fname=args.font).get_name(),
                         "axes.unicode_minus": False, "font.size": 13, "axes.titlesize": 16,
                         "figure.facecolor": "white", "text.color": "#253043"})
    colors = ["#315C9D", "#C28B2C"]
    devices = data.get("hardware", {}).get("provider_devices", {})
    labels = {"cuda": "GPU", "cpu": "CPU"}
    device_names = {p: labels.get(devices.get(p), "장치 미기록") for p in totals}
    names = ["Laya multilingual\n" + device_names["laya"],
             "일반 LLM\n" + data["llm"]["name"] + " · " + device_names["llm"]]
    population_total = sum(data["population_units"].values())
    fig, axes = plt.subplots(1, 2, figsize=(14, 8))
    fig.suptitle("Laya와 일반 LLM의 동일 판단 작업 소요 시간", x=.06, ha="left", y=.96, fontsize=22)
    fig.text(.06, .89, f"실제 데이터 표본 {data['sample_unique_units']}개 × {data['repeats']}회 · 모델별 {expected}요청 · 요청당 {data['questions_per_request']}개 선택형 판단", fontsize=13)
    for ax, values, title, unit in (
            (axes[0], list(totals.values()), "실측: 동일 표본의 총 요청 시간", "초"),
            (axes[1], list(projected.values()), f"추정: 첫 평가 기준 전체 {population_total:,}개", "분")):
        bars = ax.bar(range(2), values, color=colors, width=.48)
        ax.set_xticks(range(2), names)
        ax.set_ylabel("소요 시간 (" + unit + ")")
        ax.set_title(title, loc="left", pad=18)
        ax.set_ylim(0, max(values) * 1.25)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_axisbelow(True)
        ax.grid(axis="y", color="#E7EBF0")
        for bar, value in zip(bars, values):
            ax.text(bar.get_x()+bar.get_width()/2, value+max(values)*.035, f"{value:,.1f}{unit}", ha="center", fontsize=15)
        if ax is axes[1]:
            for bar in bars:
                bar.set_hatch("//")
    ratio = totals["llm"] / totals["laya"]
    delta = totals["llm"] - totals["laya"]
    fig.text(.06, .28, f"이 표본에서 일반 LLM / Laya 시간 비율: {ratio:.2f}배 · 일반 LLM − Laya: {delta:+.1f}초", fontsize=15)
    fig.text(.06, .215, "전체 추정 = 첫 평가의 행·셀·쌍별 평균 × 각 전체 단위 수. 반복 캐시 효과를 혼합하지 않았습니다.", fontsize=12)
    fig.text(.06, .17, "워밍업·모델 로드 제외 / 동시 요청 1 / Qwen thinking=false / 두 모델에 같은 전체 근거·질문 제공", fontsize=12)
    fig.text(.06, .125, "Laya는 GPU, 현재 Ollama Qwen은 CPU 실행. 이 설치의 비교이며 모델 자체의 속도 차이로 일반화할 수 없습니다.", fontsize=12)
    fig.text(.06, .08, "기존 Laya 143.6분은 중단·재개·검증을 포함해 이 실측과 직접 비교하지 않습니다. 속도는 발굴 품질을 뜻하지 않습니다.", fontsize=11)
    fig.text(.06, .035, f"2026-10-02 · LLM은 선택 ID 생성, Laya는 확률도 반환 · 네이티브 KV 캐시 허용 · Jev 미측정", fontsize=11)
    fig.subplots_adjust(left=.09, right=.95, top=.77, bottom=.40, wspace=.30)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=200)
    plt.close(fig)
    print(json.dumps({"sample_seconds": totals, "projected_full_minutes": projected, "ratio_llm_over_laya": ratio}))


if __name__ == "__main__":
    main()
