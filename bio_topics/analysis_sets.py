"""Outcome-blind complete analysis-set enumeration and set-specific review gates."""
from collections import defaultdict
from itertools import combinations
import math

from .clinical import clinical_counts, known, population_node
from .clinical_policy import relation_accepted
from .facts import record_facts, compatible_for_synthesis
from .util import canonical, digest

DEFAULT_RULE = {"id": "all_metadata_variants", "role": "sensitivity", "where": {},
                "source_reference": "engine_declared_default", "selection_timing": "after_data_review",
                "reason": "Enumerate every metadata-compatible alternative, irrespective of sign or significance."}


def review_states(record):
    f = record["fields"]
    source = f.get("source_verification_status") == "full_text_verified" and bool(f.get("source_verification_reference"))
    reviewers = f.get("reviewer_ids", [])
    dual = (f.get("dual_review_status") == "agreed" and f.get("dual_review_independent") is True and isinstance(reviewers, list)
            and len(set(reviewers)) >= 2 and bool(f.get("dual_review_reference")))
    rob = (f.get("rob_status") == "assessed" and f.get("rob_judgment") in {"low", "some_concerns", "high"}
           and bool(f.get("rob_tool")) and bool(f.get("rob_source_reference"))
           and f.get("rob_outcome_definition") == f.get("outcome_definition"))
    return {"source_verified": source, "dual_review_completed": dual, "outcome_rob_assessed": rob,
            "rob_judgment": f.get("rob_judgment") if rob else None,
            "synthesis_approved": f.get("synthesis_approved") is True}


def discovery_exclusions(record):
    f, c = record["fields"], record["clinical"]
    reasons = []
    if c["role"] != "effect": reasons.append("not_effect_evidence")
    if f.get("source_blocked") is True or f.get("hold_reason"): reasons.append("held_or_blocked")
    if c["conflicts"]: reasons.append("ledger_conflict")
    if c["missing_question_fields"]: reasons.append("upper_question_incomplete")
    if c["missing_stratum_fields"]: reasons.append("stratum_incomplete")
    value = f.get("value")
    if (not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)
            or f.get("measure") not in {"OR", "RR", "HR", "IRR", "MD", "SMD"}
            or (f.get("measure") in {"OR", "RR", "HR", "IRR"} and value <= 0)):
        reasons.append("invalid_or_unsupported_effect")
    return reasons


def overlap_pairs(records, profile):
    info = clinical_counts(records, profile)
    identity = info["population_component_by_record"]
    overlap = set()
    for rel in info["cohort_relations"]:
        if relation_accepted(rel, profile) and rel["relation"] in {"partial_overlap", "contains", "same"}:
            # Expand endpoints through the confirmed identity map retained by clinical_counts.
            roots = info["identity_roots"]
            overlap.add(frozenset((roots.get(rel["left"], rel["left"]), roots.get(rel["right"], rel["right"]))))
    result = set()
    for left, right in combinations(records, 2):
        a, b = identity.get(left["id"], population_node(left)[0]), identity.get(right["id"], population_node(right)[0])
        if a == b or frozenset((a, b)) in overlap:
            result.add(frozenset((left["id"], right["id"])))
    return result


def maximal_nonoverlapping_sets(records, conflicts):
    # Bron-Kerbosch on the compatibility graph: no result-based choice and no count cap.
    by_id = {r["id"]: r for r in records}
    neighbors = {i: {j for j in by_id if i != j and frozenset((i, j)) not in conflicts} for i in by_id}
    def visit(chosen, possible, excluded):
        if not possible and not excluded:
            yield [by_id[i] for i in sorted(chosen)]
            return
        pivot = max(possible | excluded, key=lambda i: (len(possible & neighbors[i]), i), default=None)
        for node in sorted(possible - (neighbors[pivot] if pivot is not None else set())):
            yield from visit(chosen | {node}, possible & neighbors[node], excluded & neighbors[node])
            possible.remove(node)
            excluded.add(node)
    yield from visit(set(), set(by_id), set())


def assess_set(selected, available, profile, rule):
    info = clinical_counts(selected, profile)
    dependency_info = clinical_counts(available, profile)
    reviews = {r["id"]: review_states(r) for r in selected}
    facts = {r["id"]: record_facts(r) for r in selected}
    failures = []
    required = list(dict.fromkeys(["estimand", "time_zero", "measure", "design", "comparator_type",
                    "comparator_definition", "outcome_time", "model", "population", "treatment_stage",
                    "exposure_class", "exposure_definition", "exposure_timing", "outcome_definition"] + profile.get("synthesis", {}).get("required_fields", [])))
    for r in selected:
        reasons = compatible_for_synthesis(r, facts, {"required_fields": required})
        reasons += [key for key, value in reviews[r["id"]].items() if key in
                    {"source_verified", "dual_review_completed", "outcome_rob_assessed", "synthesis_approved"} and not value]
        reasons += ["missing_" + f for f in r["clinical"]["missing_stratum_fields"]]
        if reasons: failures.append({"record_id": r["id"], "reasons": sorted(set(reasons))})
    independent = info["independent_evidence_count"]
    if independent is None: failures.append({"issue": "independence_unresolved", "relations": info["unresolved_relations"]})
    if info["relation_conflicts"]: failures.append({"issue": "independence_conflict", "details": info["relation_conflicts"]})
    if not selected: failures.append({"issue": "no_selected_effects"})
    components = dependency_info["dependency_component_by_record"]
    selected_groups = [components.get(r["id"], population_node(r)[0]) for r in selected]
    if overlap_pairs(selected, profile):
        failures.append({"issue": "known_overlapping_effects_selected_together"})
    # Precision is descriptive on one common analysis axis, never an estimate-selection rule.
    valid_effects = [facts[r["id"]]["effect"] for r in selected]
    precision_complete = bool(selected) and all(e is not None and not facts[r["id"]]["issues"] for r, e in zip(selected, valid_effects))
    precision_signature = sorted({canonical([r["fields"].get(k) for k in ("measure", "unit", "estimand", "time_zero", "outcome_definition", "clinical_stratum_id")]) for r in selected})
    precision = (sum(1 / e["vi"] for e in valid_effects) if precision_complete and len(precision_signature) == 1
                 and independent == len(selected) and not info["relation_conflicts"] else None)
    low_rob = sum(s["rob_judgment"] == "low" for s in reviews.values())
    worst_rob = max(({"low": 0, "some_concerns": 1, "high": 2}.get(s["rob_judgment"], 3) for s in reviews.values()), default=3)
    # At most one eligible publication credit per known overlap group. Unknown population identities get no credit.
    credited = {info["population_component_by_record"].get(r["id"], population_node(r)[0]) for r in selected
                if population_node(r)[1] and known(r["fields"].get("publication_id"))} if independent is not None else set()
    return {"selected_record_ids": [r["id"] for r in selected],
            "selected_effect_ids": [r["fields"].get("source_effect_id") for r in selected],
            "available_record_ids": [r["id"] for r in available],
            "selection_rule": rule, "duplicate_policy": "maximal_sets_without_known_pairwise_overlap",
            "source_paper_count": info["paper_count"], "independent_evidence_count": independent,
            "independence_status": info["independence_status"], "available_analysis_unit_count": independent,
            "selected_unit_count": len(selected), "known_overlap_group_count": len(set(selected_groups)),
            "independence_evidence": info["cohort_relations"], "unresolved_relations": info["unresolved_relations"],
            "relation_conflicts": info["relation_conflicts"], "publication_credit_count": len(credited),
            "publication_credit_cap_per_overlap_group": 1,
            "precision_status": "available_on_common_axis" if precision is not None else "unavailable_or_incomparable",
            "precision_signature": precision_signature, "precision_total_inverse_variance": precision,
            "low_rob_unit_count": low_rob, "worst_rob_rank": worst_rob,
            "source_verified": bool(selected) and all(s["source_verified"] for s in reviews.values()),
            "dual_review_completed": bool(selected) and all(s["dual_review_completed"] for s in reviews.values()),
            "outcome_rob_assessed": bool(selected) and all(s["outcome_rob_assessed"] for s in reviews.values()),
            "synthesis_approved": bool(selected) and all(s["synthesis_approved"] for s in reviews.values()),
            "synthesis_ready": not failures, "synthesis_blockers": failures, "row_review_states": reviews,
            "data_completeness": (sum(not record_facts(r)["issues"] for r in selected) / len(selected) if selected else None),
            "pooling_weight": None, "certainty_rating": None}


def enumerate_analysis_sets(records, profile):
    groups = defaultdict(list)
    for r in records:
        c = r["clinical"]
        groups[(c["question_id"], c["stratum_id"], c["analysis_id"])].append(r)
    declared = profile.get("clinical", {}).get("analysis_sets", [])
    # The complete exploratory set remains, even when a primary rule is declared.
    rules = [DEFAULT_RULE] + declared
    for (qid, sid, aid), available in sorted(groups.items()):
        available = sorted(available, key=lambda r: r["id"])
        dependencies = clinical_counts(available, profile)["dependency_component_by_record"]
        for rule in rules:
            matched = [r for r in available if all(r["fields"].get(k) == v for k, v in rule.get("where", {}).items())]
            if not matched: continue
            eligible = [r for r in matched if not discovery_exclusions(r)]
            conflicts = overlap_pairs(eligible, profile)
            for selected in maximal_nonoverlapping_sets(eligible, conflicts):
                result = assess_set(selected, available, profile, rule)
                result.update(question_id=qid, stratum_id=sid, analysis_group_id=aid, role=rule["role"],
                              stratum_scope=available[0]["clinical"]["stratum_scope"],
                              sensitivity_scope=available[0]["clinical"]["sensitivity_scope"],
                              question_origin=available[0]["clinical"]["question_origin"],
                              excluded_records=[{"record_id": r["id"], "reasons": discovery_exclusions(r) or
                                                 (["metadata_selector"] if r not in matched else ["alternative_overlap_estimate"])}
                                                for r in available if r not in selected])
                result["id"] = "AS" + digest([qid, sid, aid, rule, result["selected_record_ids"], result["excluded_records"]])[:24]
                yield result


def scenario_priority(sets):
    """Conservative envelope over all usable sets; never choose a favorable estimate."""
    usable = [s for s in sets if s["selected_record_ids"]]
    known_counts = [s["independent_evidence_count"] for s in usable]
    independent_floor = min(known_counts) if usable and all(n is not None for n in known_counts) else None
    signatures = {canonical(s["precision_signature"]) for s in usable}
    precisions = [s["precision_total_inverse_variance"] for s in usable]
    precision_floor = min(precisions) if usable and len(signatures) == 1 and all(v is not None for v in precisions) else None
    completeness = [s["data_completeness"] for s in usable]
    return {"priority_basis": "conservative_envelope_of_all_nonempty_analysis_sets",
            "priority_usable": bool(usable), "priority_independent_floor": independent_floor,
            "priority_precision_floor": precision_floor,
            "priority_precision_signature": next(iter(signatures)) if len(signatures) == 1 else "incomparable",
            "priority_worst_rob_rank": max((s["worst_rob_rank"] for s in usable), default=3),
            "priority_completeness_floor": min(completeness) if completeness else None,
            "priority_publication_credit_floor": min((s["publication_credit_count"] for s in usable), default=0),
            "priority_is_statistical_weight": False, "priority_is_certainty": False}
