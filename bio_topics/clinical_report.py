"""Question-family candidates plus a lossless per-job inspection CSV."""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from .clinical import clinical_counts, known
from .facts import record_facts, summarize
from .ranking import ranking_policy, score_clinical
from .store import connect, counts
from .util import canonical, digest, write_json

CLINICAL_COLUMNS = [
    "rank", "id", "candidate_kind", "clinical_question_ids", "route", "operator", "focus", "question",
    "scope", "record_ids", "analysis_group_ids", "inspection_ids", "inspection_count", "model_choice_counts",
    "model_probability_range", "question_complete", "testability_status", "paper_count", "paper_count_basis",
    "missing_paper_identity_rows", "unique_study_count", "cohort_count", "population_count",
    "known_dependency_group_count", "independent_evidence_count", "independence_status",
    "unresolved_independence_count", "eligible_independent_evidence_count", "eligible_paper_count", "eligible_evidence_count", "eligible_record_count",
    "paper_count_bonus", "independent_evidence_bonus", "ranking_score", "ranking_paper_count_weight",
    "ranking_independent_evidence_weight", "cohort_relations", "relation_conflicts", "observations", "required_checks",
    "falsification", "next_action", "limits", "status", "inspection_status", "verification_status", "inspection_coverage"]
INSPECTION_COLUMNS = ["job_id", "unit_id", "unit_kind", "operator", "status", "model_choice", "focus",
                      "model_selection_probability", "candidate_ids", "record_ids", "clinical_question_ids",
                      "error", "inspection_status", "verification_status", "inspection_coverage"]


def write_csv(path, rows, columns):
    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: canonical(v) if isinstance(v, (dict, list)) else v for k, v in row.items() if k in columns})


def export_clinical(out):
    from .report import TEMPLATES, FOCUS_KO
    out = Path(out)
    records = json.loads((out / "records.json").read_text())
    profile = json.loads((out / "profile.json").read_text())
    by_id = {r["id"]: r for r in records}
    facts = {r["id"]: record_facts(r) for r in records}
    policy = ranking_policy(profile)
    db = connect(out / "inspection.sqlite3")
    stats = counts(db)
    manifest = json.loads((out / "manifest.json").read_text())
    verification = json.loads((out / "verification.json").read_text()) if (out / "verification.json").exists() else {"status": "not_verified"}
    run_status = {"inspection_status": manifest["status"], "verification_status": verification["status"], "inspection_coverage": stats["coverage"]}
    inspections, families = [], {}
    with (out / "decisions.jsonl").open("w") as all_decisions:
        for job in db.execute("SELECT j.*,u.body FROM jobs j JOIN units u ON j.unit_id=u.id ORDER BY j.seq"):
            unit = json.loads(job["body"])
            receipt = json.loads(job["receipt"]) if job["receipt"] else None
            sources = [by_id[rid] for rid in unit["record_ids"]]
            qids = sorted({r["clinical"]["question_id"] for r in sources})
            inspection = {"job_id": job["id"], "unit_id": unit["id"], "unit_kind": unit["kind"], "operator": job["operator"],
                          "status": job["status"], "error": job["error"], "record_ids": unit["record_ids"],
                          "clinical_question_ids": qids, "candidate_ids": [], **run_status}
            inspections.append(inspection)
            all_decisions.write(canonical({"job_id": job["id"], "unit_id": unit["id"], "operator": job["operator"],
                                          "status": job["status"], "error": job["error"], "receipt": receipt}) + "\n")
            if not receipt or job["status"] not in ("evaluated", "cached"):
                continue
            answers = receipt["payload"]["answers"]
            choice, focus = answers["discovery"]["choice"], answers["focus"]["choice"]
            probability = answers["discovery"]["probabilities"][choice]
            inspection.update(model_choice=choice, focus=focus, model_selection_probability=probability)
            if choice == "background":
                continue
            incomplete = any(r["clinical"]["missing_question_fields"] or r["clinical"]["conflicts"] for r in sources)
            blocked = any(r["fields"].get("source_blocked") is True or r["fields"].get("hold_reason") for r in sources)
            numerical = any(facts[r["id"]]["issues"] for r in sources)
            roles = {r["clinical"]["role"] for r in sources}
            route = ("배경 정보 확인" if roles == {"context"} else "추가 확인" if choice == "needs_data" or incomplete or blocked or numerical or "unresolved" in roles else "연구 가설")
            if focus == "mechanism" and not profile.get("knowledge_relations"):
                route = "추가 확인"
            # A categorical model identifies a question family; no semantic hypothesis deduplication is claimed.
            key = (tuple(qids), job["operator"], focus, route)
            cid = "C" + digest(key)[:24]
            inspection["candidate_ids"].append(cid)
            if key not in families:
                families[key] = {"id": cid, "clinical_question_ids": qids, "operator": job["operator"], "focus": focus,
                                 "route": route, "record_ids": set(), "inspection_ids": [], "choices": [], "probabilities": []}
            family = families[key]
            family["record_ids"].update(unit["record_ids"])
            family["inspection_ids"].append(job["id"])
            family["choices"].append(choice)
            family["probabilities"].append(probability)
    candidates = []
    for family in families.values():
        sources = [by_id[rid] for rid in sorted(family["record_ids"])]
        evidence = clinical_counts(sources, profile)
        scope = {r["clinical"]["question_id"]: r["clinical"]["question_scope"] for r in sources}
        complete = all(not r["clinical"]["missing_question_fields"] and not r["clinical"]["conflicts"] for r in sources)
        checks = [{"record_id": r["id"], "issues": facts[r["id"]]["issues"], "ledger_conflicts": r["clinical"]["conflicts"],
                   "missing_question_fields": r["clinical"]["missing_question_fields"],
                   "source_blocked": r["fields"].get("source_blocked"), "hold_reason": r["fields"].get("hold_reason")}
                  for r in sources if facts[r["id"]]["issues"] or r["fields"].get("source_blocked") is True or r["fields"].get("hold_reason")]
        if evidence["independent_evidence_count"] is None:
            checks.append({"issue": "independence_not_established"})
        checks.extend(evidence["relation_conflicts"])
        if family["focus"] == "mechanism" and not profile.get("knowledge_relations"):
            checks.append({"issue": "sourced_knowledge_relations_required"})
        if evidence["relation_conflicts"]:
            family["route"] = "추가 확인"
        title_parts = []
        for qid, values in scope.items():
            title_parts.append("; ".join(f"{k}={v}" for k, v in values.items() if known(v)) or qid)
        label = " | ".join(title_parts)
        question = label + " — " + TEMPLATES[family["operator"]].format(focus=FOCUS_KO[family["focus"]])
        testable = complete and bool(evidence["eligible_evidence_count"]) and not checks
        c = {k: v for k, v in family.items() if k not in {"choices", "probabilities", "record_ids"}}
        c.update(candidate_kind="clinical_question_family", question=question, scope=scope,
                 record_ids=sorted(family["record_ids"]), analysis_group_ids=sorted({r["clinical"]["analysis_id"] for r in sources}),
                 inspection_count=len(family["inspection_ids"]), model_choice_counts=dict(Counter(family["choices"])),
                 model_probability_range=[min(family["probabilities"]), max(family["probabilities"])],
                 question_complete=complete, testability_status="metadata_ready_for_review" if testable else "requires_resolution",
                 observations={**summarize(sources, facts), "by_record": [facts[r["id"]] for r in sources]},
                 required_checks=checks, falsification="requires_scientific_review",
                 next_action="Resolve listed metadata and overlap issues; specify a falsification analysis before accepting this hypothesis.",
                 limits=["This is a template-based question family; distinct biological hypotheses have not been semantically adjudicated.",
                         "Model probabilities refer to individual classification decisions, not hypothesis truth or independent replications.",
                         "Known dependency components do not establish independence; counts use only cited evidence.",
                         "Background decisions and failed/pending inspections remain in inspection_results.csv."],
                 status="system2_and_human_review_pending", **run_status)
        c.update(score_clinical(evidence, policy))
        candidates.append(c)
    buckets = defaultdict(list)
    for c in candidates:
        buckets[(c["route"], c["operator"])].append(c)
    for bucket in buckets.values():
        bucket.sort(key=lambda c: (-int(c["question_complete"]), -int(c["testability_status"] == "metadata_ready_for_review"),
                                   -int(c["eligible_evidence_count"] > 0), -c["ranking_score"], c["id"]))
    ordered = []
    for i in range(max((len(v) for v in buckets.values()), default=0)):
        for key in sorted(buckets):
            if i < len(buckets[key]):
                ordered.append(buckets[key][i])
    for rank, c in enumerate(ordered, 1):
        c["rank"] = rank
    write_csv(out / "candidates.csv", ordered, CLINICAL_COLUMNS)
    write_csv(out / "inspection_results.csv", inspections, INSPECTION_COLUMNS)
    with (out / "candidates.jsonl").open("w") as handle:
        for c in ordered:
            handle.write(canonical(c) + "\n")
    write_json(out / "candidate-summary.json", {"total": len(ordered), "by_route": dict(Counter(c["route"] for c in ordered)),
               "inspection_records": len(inspections), "all_candidates_exported": True, "primary_output": "candidates.csv",
               "inspection_output": "inspection_results.csv", "ranking_policy": policy,
               "paper_count_incentive_applied": True, "candidate_kind": "clinical_question_family", **run_status,
               "downstream_review": "pending"})
    lines = ["# 임상 질문별 후보", "", f"검사 상태: {manifest['status']}; 검증: {verification['status']}; 검사율: {stats['coverage']:.2%}",
             f"임상 질문별 후보 묶음: {len(ordered)}; 세부 검사: {len(inspections)}", "",
             "candidates.csv는 임상 질문·검사 관점별 후보 묶음입니다. 독립적인 연구 가설의 확정 목록이 아닙니다.",
             "inspection_results.csv는 배경·실패·미검사를 포함한 전체 검사 기록과 후보 연결을 제공합니다.",
             "독립 근거 수의 빈 값은 미확정입니다. 논문 수는 논문 ID만 세며 연구 ID로 대체하지 않습니다.",
             "가점은 분석에 필요한 질문 정보가 있고 보류·차단되지 않은 효과 근거만 사용합니다.",
             "원장 연결·정규화 이력은 clinical-audit.json과 records.json에 보존됩니다.", ""]
    for c in ordered:
        independent = "미확정" if c["independent_evidence_count"] is None else str(c["independent_evidence_count"])
        lines.extend([f"## {c['rank']}. {c['question']}", f"후보: {c['id']}; 경로: {c['route']}",
                      f"논문 {c['paper_count']}편; 독립 근거 {independent}; 연결된 검사 {c['inspection_count']}개.", ""])
    (out / "REPORT.ko.md").write_text("\n".join(lines) + "\n")
    (out / "SYSTEM2-REVIEW.ko.md").write_text("# 과학적 검토 대기\n\n임상 질문별 근거와 모든 세부 검사를 읽고 가설·반대 근거·반증 조건을 작성하세요.\n문헌 검증, 통계적 유의성 평가, 사람의 채택은 아직 수행되지 않았습니다.\n")
    db.close()
    return len(ordered)
