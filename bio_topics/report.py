import csv
import json
from collections import defaultdict
from pathlib import Path

from .facts import record_facts
from .plan import FOCI, OPERATORS
from .ranking import evidence_counts, ranking_policy, score_candidate
from .store import connect, counts
from .util import canonical, write_json

FOCUS_KO = {"timing": "노출·측정 시점", "comparator": "비교군·대조 정의", "model": "보정·분석 선택",
            "population": "인구집단·세포 유형·단계", "pattern": "관측 방향·결과 패턴",
            "precision": "근거량·불확실성", "source": "원문·추출 정보", "mechanism": "선언된 기전 관계"}
TEMPLATES = {
    "integrity": "{focus}에 관한 원문·추출 불일치를 확인하면 해석이 달라지는가?",
    "heterogeneity": "{focus}의 차이가 관측 결과의 차이를 설명하는가?",
    "robustness": "{focus}에 관한 허용된 선택을 바꿔도 결론이 유지되는가?",
    "bias": "{focus}에 관련된 편향으로 관측 패턴을 설명할 수 있는가?",
    "gap": "{focus}의 미측정 영역을 조사하면 연구 질문을 해결할 수 있는가?",
    "generalizability": "{focus}가 다른 조건에서도 관측 패턴이 재현되는가?",
    "contradiction": "{focus}의 정의를 맞추면 상충하는 결과가 해소되는가?",
    "decision": "{focus}의 미결 사항을 해결하면 해석·후속 연구 선택이 달라지는가?",
    "mechanism": "선언된 {focus}가 관측된 변화를 연결하며 후속 실험에서 검증되는가?",
}

CSV_COLUMNS = ["rank", "id", "route", "operator", "focus", "question", "scope_text", "record_ids",
               "observations", "limits", "falsification", "required_checks", "model_choice",
               "model_selection_probability", "status", "model", "job_id", "unit_id", "scope",
               "inspection_status", "verification_status", "inspection_coverage",
               "paper_count", "unique_study_count", "paper_count_basis", "missing_paper_identity_rows",
               "incentive_evidence_count", "paper_count_bonus", "ranking_score", "ranking_paper_count_weight"]


def write_candidate_csv(candidates, path, inspection_status, verification_status, coverage):
    """Write the primary deliverable, including evidence and incomplete-run status.

    Structured cells use JSON; source record IDs use semicolons. UTF-8 BOM
    keeps Korean text readable in spreadsheet applications. An empty result
    still has its header and never invents a candidate.
    """
    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for candidate in candidates:
            row = {**candidate, "record_ids": ";".join(candidate["record_ids"]),
                   "inspection_status": inspection_status, "verification_status": verification_status,
                   "inspection_coverage": coverage}
            for field in ("scope", "observations", "limits", "required_checks"):
                row[field] = canonical(candidate.get(field, [] if field != "scope" else {}))
            writer.writerow(row)


def export_report(out):
    out = Path(out)
    records = json.loads((out / "records.json").read_text())
    by_id = {r["id"]: r for r in records}
    facts = {r["id"]: record_facts(r) for r in records}
    profile = json.loads((out / "profile.json").read_text())
    policy = ranking_policy(profile)
    evidence_by_unit = {}
    db = connect(out / "inspection.sqlite3")
    buckets = defaultdict(list)
    with (out / "decisions.jsonl").open("w") as all_decisions:
        for row in db.execute("SELECT j.*,u.body FROM jobs j JOIN units u ON j.unit_id=u.id ORDER BY j.seq"):
            unit = json.loads(row["body"])
            receipt = json.loads(row["receipt"]) if row["receipt"] else None
            all_decisions.write(canonical({"job_id": row["id"], "unit_id": row["unit_id"], "operator": row["operator"],
                                          "status": row["status"], "error": row["error"], "receipt": receipt}) + "\n")
            if receipt is None or row["status"] not in ("evaluated", "cached"):
                continue
            answers = receipt["payload"]["answers"]
            choice = answers["discovery"]["choice"]
            if choice == "background":
                continue
            focus = answers["focus"]["choice"]
            sources = [by_id[rid] for rid in unit["record_ids"]]
            if row["unit_id"] not in evidence_by_unit:
                evidence_by_unit[row["unit_id"]] = evidence_counts(sources)
            unresolved = any(facts[r["id"]]["issues"] or r["fields"].get("source_blocked") is True
                             or r["fields"].get("hold_reason") for r in sources)
            required_checks = [{"record_id": r["id"], "issues": facts[r["id"]]["issues"],
                                "source_blocked": r["fields"].get("source_blocked", False),
                                "hold_reason": r["fields"].get("hold_reason", "")}
                               for r in sources if facts[r["id"]]["issues"]
                               or r["fields"].get("source_blocked") is True or r["fields"].get("hold_reason")]
            if focus == "mechanism" and not profile.get("knowledge_relations"):
                unresolved = True
                required_checks.append({"issue": "sourced_knowledge_relations_required"})
            route = "추가 확인" if choice == "needs_data" or unresolved else "연구 가설"
            scope_text = ", ".join(f"{k}={v}" for k, v in unit["scope"].items())
            entities = sorted({r["fields"]["entity_id"] for r in sources if r["fields"].get("entity_id")})
            if entities:
                scope_text += "; entity=" + ",".join(entities)
            candidate = {"id": "C" + row["id"][1:], "job_id": row["id"], "unit_id": row["unit_id"],
                         "operator": row["operator"], "focus": focus, "route": route,
                         "question": TEMPLATES[row["operator"]].format(focus=FOCUS_KO[focus]),
                         "scope": unit["scope"], "scope_text": scope_text,
                         "record_ids": unit["record_ids"], "observations": unit["state"]["observations"],
                         "model_choice": choice, "model_selection_probability": answers["discovery"]["probabilities"][choice],
                         "status": "system2_and_human_review_pending", "falsification": "대안 설명과 반증 조건은 근거를 읽고 추가 작성해야 함",
                         "limits": unit["state"]["limits"], "required_checks": required_checks,
                         "model": receipt["payload"]["model"]}
            candidate.update(score_candidate(candidate["model_selection_probability"],
                                             evidence_by_unit[row["unit_id"]], profile["domain"], policy))
            buckets[(route, row["operator"])].append(candidate)
    # Round-robin diversity ordering after every inspection, retaining every detected candidate.
    for bucket in buckets.values():
        bucket.sort(key=lambda c: (-c["ranking_score"], -c["model_selection_probability"], c["id"]))
    candidates = []
    keys = sorted(buckets)
    index = 0
    while any(index < len(buckets[k]) for k in keys):
        for key in keys:
            if index < len(buckets[key]):
                candidates.append(buckets[key][index])
        index += 1
    with (out / "candidates.jsonl").open("w") as handle:
        for rank, candidate in enumerate(candidates, 1):
            candidate["rank"] = rank
            handle.write(canonical(candidate) + "\n")
    stats = counts(db)
    manifest = json.loads((out / "manifest.json").read_text())
    verification = (json.loads((out / "verification.json").read_text())
                    if (out / "verification.json").exists() else {"status": "not_verified"})
    write_candidate_csv(candidates, out / "candidates.csv", manifest["status"], verification["status"], stats["coverage"])
    lines = ["# 전수 검사 결과", "", "입력은 " + ("합성 예제입니다." if profile.get("synthetic_example") else "제공된 프로젝트 데이터입니다."),
             "", f"검사 상태: **{manifest['status']}**", f"검사: {stats['successful']}/{stats['planned']} ({stats['coverage']:.2%})",
             f"실제 평가 {stats['evaluated']}, 검증된 캐시 {stats['cached']}, 실패 {stats['failed']}, 미검사 {stats['pending']}",
             f"모델이 표시한 후보·추가 확인 항목: {len(candidates)}개", "",
             "기본 결과물은 candidates.csv입니다. 모든 후보를 CSV에 수록했으며 JSONL과 아래 보고서는 보조 자료입니다.",
             "순위 확률은 과학적 참일 확률이 아닙니다.",
             "메타분석 후보에는 논문 수 가점을 적용하며 경로·연산자별 점수순을 다양성 순서로 배치합니다. 점수는 확률이 아닙니다.",
             "문헌 확인·System 2 해석·사람의 채택은 아직 완료되지 않았습니다.", "",
             "## 후보", ""]
    for c in candidates:
        lines.extend([f"### {c['rank']}. [{c['route']}] {c['question']}",
                      f"- 범위: {c['scope_text']}", f"- 연산자: {OPERATORS[c['operator']][0]}",
                      f"- 근거: {c['unit_id']}; 원본 행 ID: {', '.join(c['record_ids'])}",
                      f"- 후보 ID: {c['id']}; 상태: 후속 검토 필요", ""])
        if profile["domain"] == "meta":
            lines.extend([f"- 논문 수: {c['paper_count']}; 중복·상태 반영 가점 근거 수: {c['incentive_evidence_count']}; "
                          f"가점: {c['paper_count_bonus']:.4f}; 선정 점수: {c['ranking_score']:.4f}", ""])
    if not candidates:
        lines.append("현재 성공한 검사에서 모델이 후보를 선택하지 않았습니다. 실패·미검사를 후보 없음으로 해석하지 마세요.")
    (out / "REPORT.ko.md").write_text("\n".join(lines) + "\n")
    (out / "SYSTEM2-REVIEW.ko.md").write_text(
        "# 후속 과학적 검토\n\n이 파일은 검토 요청이며 검토 완료 기록이 아닙니다.\n\n"
        "1. verification.json이 verified인지 확인한다. 미완료 결과는 임시 결과로 표시한다.\n"
        "2. candidates.jsonl의 모든 후보와 inspection.sqlite3의 근거, records.json의 원본을 읽는다.\n"
        "3. 관측 사실, 추정, 가설을 구분한다. 기존 수치·계산 ID를 인용하고 수치를 만들지 않는다.\n"
        "4. 문헌 검색은 사용자가 허용한 범위에서 수행하고 검색식·검색일·출처·반대 근거를 기록한다.\n"
        "5. 후보별 연구 가치, 대안 설명, 반증 조건, 추가 분석·실험 계획을 작성한다.\n"
        "6. 후보를 수정한 뒤 속성·출처·수치·승인 상태를 재검토한다. 모델 판정을 생물학적 확인으로 쓰지 않는다.\n"
        "7. 사람의 채택·기각·보류는 실제 사용자의 결정을 별도 기록한다.\n")
    write_json(out / "candidate-summary.json", {"total": len(candidates), "by_route": dict(__import__('collections').Counter(c["route"] for c in candidates)),
                                               "all_candidates_exported": True, "primary_output": "candidates.csv",
                                               "inspection_status": manifest["status"], "verification_status": verification["status"],
                                               "ranking_policy": policy, "paper_count_incentive_applied": profile["domain"] == "meta",
                                               "downstream_review": "pending"})
    db.close()
    return len(candidates)
