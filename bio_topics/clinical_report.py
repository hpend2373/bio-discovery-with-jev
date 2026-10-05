"""Question-family candidates plus a lossless per-job inspection CSV."""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from .clinical import clinical_counts, known
from .analysis_sets import enumerate_analysis_sets, scenario_priority, review_states, discovery_exclusions
from .facts import record_facts, summarize
from .ranking import ranking_policy, score_clinical
from .store import connect, counts
from .util import canonical, digest, write_json

CLINICAL_COLUMNS = [
    "rank", "output_category", "independence_evaluation_status", "id", "candidate_kind", "clinical_question_ids", "route", "operator", "focus", "question", "scope",
    "record_ids", "stratum_ids", "analysis_group_ids", "analysis_set_ids", "analysis_set_counts", "question_origins",
    "generated_hypothesis_origin", "inspection_ids", "inspection_count", "model_choice_counts", "model_probability_range",
    "question_complete", "testability_status", "paper_count", "paper_count_basis", "missing_paper_identity_rows",
    "unique_study_count", "cohort_count", "population_count", "source_verified", "dual_review_completed",
    "outcome_rob_assessed", "synthesis_approved", "synthesis_ready_set_ids", "priority_basis", "priority_usable",
    "priority_independent_floor", "priority_precision_floor", "priority_precision_signature", "priority_worst_rob_rank",
    "priority_completeness_floor", "priority_publication_credit_floor", "paper_count_bonus", "ranking_score",
    "ranking_score_meaning", "ranking_paper_count_weight", "priority_is_statistical_weight", "priority_is_certainty",
    "observations", "required_checks", "falsification", "next_action", "limits", "status",
    "inspection_status", "verification_status", "inspection_coverage"]
ANALYSIS_SET_COLUMNS = ["id", "candidate_ids", "question_id", "stratum_id", "analysis_group_id", "role", "question_origin",
    "selected_record_ids", "selected_effect_ids", "available_record_ids", "stratum_scope", "sensitivity_scope",
    "selection_rule", "duplicate_policy", "source_paper_count", "selected_unit_count", "known_overlap_group_count",
    "independent_evidence_count", "independence_status", "available_analysis_unit_count", "independence_evidence",
    "unresolved_relations", "relation_conflicts", "publication_credit_count", "publication_credit_cap_per_overlap_group",
    "precision_status", "precision_signature", "precision_total_inverse_variance", "low_rob_unit_count", "worst_rob_rank",
    "source_verified", "dual_review_completed", "outcome_rob_assessed", "synthesis_approved", "synthesis_ready",
    "synthesis_blockers", "row_review_states", "excluded_records", "data_completeness", "pooling_weight", "certainty_rating",
    "model_inspection_status", "inspection_status", "verification_status", "inspection_coverage"]
LINK_COLUMNS = ["candidate_id", "record_id", "source_effect_id", "publication_id", "question_id", "stratum_id",
                "analysis_set_id", "role", "selected", "role_reason", "question_origin", "source_verified",
                "dual_review_completed", "outcome_rob_assessed", "rob_judgment", "synthesis_approved"]
INSPECTION_COLUMNS = ["job_id", "unit_id", "unit_kind", "parent_unit_id", "context_mode", "entry_range", "operator", "status", "model_choice", "focus",
                      "model_selection_probability", "candidate_ids", "record_ids", "clinical_question_ids",
                      "error", "inspection_status", "verification_status", "inspection_coverage"]


def write_csv(path, rows, columns):
    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: canonical(v) if isinstance(v, (dict, list)) else v for k, v in row.items() if k in columns})


def order_candidates(candidates):
    """Evidence quantity precedes precision; different measurement axes are never numerically compared."""
    buckets = defaultdict(list)
    for candidate in candidates:
        buckets[(candidate["route"], candidate["operator"])].append(candidate)
    for key, bucket in buckets.items():
        prefixes = defaultdict(list)
        for c in bucket:
            prefix = (-int(c["question_complete"]), -int(c["priority_usable"]),
                      -int(c["priority_independent_floor"] is not None), -(c["priority_independent_floor"] or 0),
                      -int(c["priority_precision_floor"] is not None))
            prefixes[prefix].append(c)
        ordered_bucket = []
        def rest(c):
            return (c["priority_worst_rob_rank"], -(c["priority_completeness_floor"] or 0), -c["paper_count_bonus"], c["id"])
        for prefix in sorted(prefixes):
            signatures = defaultdict(list)
            for c in prefixes[prefix]: signatures[c["priority_precision_signature"]].append(c)
            for group in signatures.values():
                group.sort(key=lambda c: (-(c["priority_precision_floor"] or 0), *rest(c)))
            # Across incommensurable axes, inspect RoB/completeness rather than the numeric SE scale.
            groups = sorted(signatures.values(), key=lambda group: rest(group[0]))
            for i in range(max(map(len, groups))):
                ordered_bucket.extend(group[i] for group in groups if i < len(group))
        buckets[key] = ordered_bucket
    ordered = []
    for i in range(max((len(v) for v in buckets.values()), default=0)):
        for key in sorted(buckets):
            if i < len(buckets[key]): ordered.append(buckets[key][i])
    return ordered


def export_clinical(out):
    from .report import TEMPLATES, FOCUS_KO
    out = Path(out)
    records = json.loads((out / "records.json").read_text())
    profile = json.loads((out / "profile.json").read_text())
    by_id = {r["id"]: r for r in records}
    facts = {r["id"]: record_facts(r) for r in records}
    policy = ranking_policy(profile)
    analysis_sets = list(enumerate_analysis_sets(records, profile))
    analysis_inspections = defaultdict(list)
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
                          "parent_unit_id": unit.get("parent_unit_id", unit["id"]), "context_mode": unit.get("context_mode", "joint_full"), "entry_range": unit.get("entry_range"),
                          "clinical_question_ids": qids, "candidate_ids": [], **run_status}
            inspections.append(inspection)
            if unit["kind"] == "analysis_set":
                analysis_inspections[unit["scope"]["analysis_set_id"]].append(job["status"])
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
    candidates, candidate_links = [], []
    scenario_candidates = defaultdict(list)
    for family in families.values():
        # Every same-question row is linked, even if its own model judgment was background.
        sources = [r for r in records if r["clinical"]["question_id"] in family["clinical_question_ids"]]
        family["record_ids"] = {r["id"] for r in sources}
        family_sets = [s for s in analysis_sets if s["question_id"] in family["clinical_question_ids"]]
        priority = scenario_priority(family_sets)
        row_states = [review_states(r) for r in sources if r["clinical"]["role"] == "effect"]
        evidence = clinical_counts(sources, profile)
        scope = {r["clinical"]["question_id"]: r["clinical"]["question_scope"] for r in sources}
        complete = all(not r["clinical"]["missing_question_fields"] and not r["clinical"]["conflicts"] for r in sources)
        checks = [{"record_id": r["id"], "issues": facts[r["id"]]["issues"], "ledger_conflicts": r["clinical"]["conflicts"],
                   "missing_question_fields": r["clinical"]["missing_question_fields"],
                   "source_blocked": r["fields"].get("source_blocked"), "hold_reason": r["fields"].get("hold_reason")}
                  for r in sources if facts[r["id"]]["issues"] or r["fields"].get("source_blocked") is True or r["fields"].get("hold_reason")]
        for scenario in family_sets:
            if not scenario["synthesis_ready"]:
                checks.append({"analysis_set_id": scenario["id"], "synthesis_blockers": scenario["synthesis_blockers"]})
        if family["focus"] == "mechanism" and not profile.get("knowledge_relations"):
            checks.append({"issue": "sourced_knowledge_relations_required"})

        title_parts = []
        for qid, values in scope.items():
            title_parts.append("; ".join(f"{k}={v}" for k, v in values.items() if known(v)) or qid)
        label = " | ".join(title_parts)
        question = label + " — " + TEMPLATES[family["operator"]].format(focus=FOCUS_KO[family["focus"]])
        testable = complete and priority["priority_usable"]
        c = {k: v for k, v in family.items() if k not in {"choices", "probabilities", "record_ids"}}
        c.update(candidate_kind="clinical_question_family", question=question, scope=scope,
                 record_ids=sorted(family["record_ids"]), stratum_ids=sorted({r["clinical"]["stratum_id"] for r in sources}),
                 analysis_set_ids=[s["id"] for s in family_sets],
                 analysis_set_counts=[{"analysis_set_id": s["id"], "independent_evidence_count": s["independent_evidence_count"],
                                       "selected_unit_count": s["selected_unit_count"], "independence_status": s["independence_status"]} for s in family_sets],
                 question_origins={r["clinical"]["question_id"]: r["clinical"]["question_origin"] for r in sources},
                 generated_hypothesis_origin="posthoc_exploratory",
                 source_verified=bool(row_states) and all(s["source_verified"] for s in row_states),
                 dual_review_completed=bool(row_states) and all(s["dual_review_completed"] for s in row_states),
                 outcome_rob_assessed=bool(row_states) and all(s["outcome_rob_assessed"] for s in row_states),
                 synthesis_approved=bool(row_states) and all(s["synthesis_approved"] for s in row_states),
                 synthesis_ready_set_ids=[s["id"] for s in family_sets if s["synthesis_ready"]],
                 analysis_group_ids=sorted({r["clinical"]["analysis_id"] for r in sources}),
                 inspection_count=len(family["inspection_ids"]), model_choice_counts=dict(Counter(family["choices"])),
                 model_probability_range=[min(family["probabilities"]), max(family["probabilities"])],
                 question_complete=complete, testability_status="metadata_ready_for_review" if testable else "requires_resolution",
                 observations={**summarize(sources, facts), "by_record": [facts[r["id"]] for r in sources]},
                 required_checks=checks, falsification="requires_scientific_review",
                 next_action="Resolve listed metadata and overlap issues; specify a falsification analysis before accepting this hypothesis.",
                 limits=["This is a template-based question family; distinct biological hypotheses have not been semantically adjudicated.",
                         "Model probabilities refer to individual classification decisions, not hypothesis truth or independent replications.",
                         "Independence counts belong to selected analysis sets; no candidate-level total is inferred.",
                         "Model inspection does not verify original papers, dual review, outcome RoB or synthesis approval.",
                         "Opposing, null and favorable results are linked with the same outcome-blind rules.",
                         "Background decisions and failed/pending inspections remain in inspection_results.csv.",
                         "Partitioned inspections are local page judgments. Full page coverage does not establish a global joint conclusion."],
                 status="system2_and_human_review_pending", **run_status)
        c.update({k: evidence[k] for k in ("paper_count", "paper_count_basis", "missing_paper_identity_rows", "unique_study_count", "cohort_count", "population_count")})
        c.update(score_clinical(priority, policy))
        linked_records = set()
        for scenario in family_sets:
            scenario_candidates[scenario["id"]].append(c["id"])
            for rid in scenario["available_record_ids"]:
                r = by_id[rid]
                selected = rid in scenario["selected_record_ids"]
                reasons = discovery_exclusions(r)
                role = ("background" if r["clinical"]["role"] == "context" else "held" if reasons else
                        scenario["role"] if selected else "alternative_model")
                candidate_links.append({"candidate_id": c["id"], "record_id": rid, "source_effect_id": r["fields"].get("source_effect_id"),
                    "publication_id": r["fields"].get("publication_id"), "question_id": r["clinical"]["question_id"],
                    "stratum_id": r["clinical"]["stratum_id"], "analysis_set_id": scenario["id"], "role": role,
                    "selected": selected, "role_reason": reasons or [scenario["selection_rule"]["id"] if selected else "other_metadata_or_overlap_alternative"],
                    "question_origin": r["clinical"]["question_origin"], **review_states(r)})
                linked_records.add(rid)
        assert linked_records == family["record_ids"], "Every same-question row must have an explicit candidate link"
        candidates.append(c)
    for c in candidates:
        c["output_category"] = "clinical_candidate" if c["question_complete"] else "metadata_review"
        c["independence_evaluation_status"] = "available" if c.get("priority_independent_floor") not in (None, "") else "not_established"
    all_families = order_candidates(candidates)
    ordered = [c for c in all_families if c["question_complete"]]
    review_queue = [c for c in all_families if not c["question_complete"]]
    write_csv(out / "all_candidate_families.csv", all_families, CLINICAL_COLUMNS)
    write_csv(out / "review_queue.csv", review_queue, CLINICAL_COLUMNS)
    for rank, c in enumerate(ordered, 1):
        c["rank"] = rank
    write_csv(out / "candidates.csv", ordered, CLINICAL_COLUMNS)
    write_csv(out / "inspection_results.csv", inspections, INSPECTION_COLUMNS)
    write_csv(out / "candidate_effects.csv", candidate_links, LINK_COLUMNS)
    for scenario in analysis_sets:
        statuses = analysis_inspections[scenario["id"]]
        scenario.update(candidate_ids=scenario_candidates[scenario["id"]], **run_status,
                        model_inspection_status="inspected" if statuses and all(s in ("evaluated", "cached") for s in statuses) else "incomplete")
    write_csv(out / "analysis_sets.csv", analysis_sets, ANALYSIS_SET_COLUMNS)
    with (out / "analysis_sets.jsonl").open("w") as handle:
        for scenario in analysis_sets:
            handle.write(canonical(scenario) + "\n")
    with (out / "candidates.jsonl").open("w") as handle:
        for c in ordered:
            handle.write(canonical(c) + "\n")
    write_json(out / "candidate-summary.json", {"total": len(ordered), "by_route": dict(Counter(c["route"] for c in ordered)),
               "inspection_records": len(inspections), "all_candidates_exported": True, "all_families_output": "all_candidate_families.csv", "review_queue_count": len(review_queue), "primary_output": "candidates.csv",
               "inspection_output": "inspection_results.csv", "analysis_sets_output": "analysis_sets.csv",
               "candidate_effects_output": "candidate_effects.csv", "analysis_set_count": len(analysis_sets), "ranking_policy": policy,
               "paper_count_incentive_applied": policy["paper_count_weight"] > 0, "candidate_kind": "clinical_question_family", **run_status,
               "downstream_review": "pending"})
    lines = ["# 임상 질문별 후보", "", f"검사 상태: {manifest['status']}; 검증: {verification['status']}; 검사율: {stats['coverage']:.2%}",
             f"임상 질문별 후보 묶음: {len(ordered)}; 세부 검사: {len(inspections)}", "",
             "candidates.csv는 임상 질문·검사 관점별 후보 묶음입니다. 독립적인 연구 가설의 확정 목록이 아닙니다.",
             "inspection_results.csv는 배경·실패·미검사를 포함한 전체 검사 기록과 후보 연결을 제공합니다.",
             "독립 근거 수는 analysis_sets.csv의 선택된 효과 행과 중복 규칙에 붙습니다. 빈 값은 미확정이며 0과 다릅니다.",
             "candidate_effects.csv는 모든 같은 질문 행을 주 분석 후보·대안 모형·민감도·배경·보류 역할로 연결합니다.",
             "검사 완료는 원문 확인·독립 이중검토·결과별 RoB 평가·합성 승인을 의미하지 않습니다.",
             "가점은 분석에 필요한 질문 정보가 있고 보류·차단되지 않은 효과 근거만 사용합니다.",
             "원장 연결·정규화 이력은 clinical-audit.json과 records.json에 보존됩니다.", ""]
    for c in ordered:
        lines.extend([f"## {c['rank']}. {c['question']}", f"후보: {c['id']}; 경로: {c['route']}",
                      f"논문 {c['paper_count']}편; 분석 세트 {len(c['analysis_set_ids'])}개; 연결된 검사 {c['inspection_count']}개.", ""])
    (out / "REPORT.ko.md").write_text("\n".join(lines) + "\n")
    (out / "SYSTEM2-REVIEW.ko.md").write_text("# 과학적 검토 대기\n\n임상 질문별 근거와 모든 세부 검사를 읽고 가설·반대 근거·반증 조건을 작성하세요.\n문헌 검증, 통계적 유의성 평가, 사람의 채택은 아직 수행되지 않았습니다.\n")
    db.close()
    return len(ordered)
