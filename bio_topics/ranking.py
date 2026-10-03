"""Post-inspection ranking incentives; never a filter on model inspection."""
import math

from .facts import dependency_components


def ranking_policy(profile):
    settings = profile.get("ranking", {})
    if not isinstance(settings, dict) or set(settings) - {"paper_count_weight"}:
        raise ValueError("ranking에는 paper_count_weight만 설정할 수 있습니다.")
    weight = settings.get("paper_count_weight", 0.25)
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or not 0 <= weight <= 1:
        raise ValueError("ranking.paper_count_weight는 0~1의 유한한 수여야 합니다.")
    return {"paper_count_weight": weight, "formula": "model_selection_probability + weight * log2(1 + incentive_evidence_count)",
            "ordering": "score_within_route_operator_then_round_robin",
            "count_basis": "publication_id_with_study_id_proxy; shared_publication_study_or_cohort_grouped",
            "blocked_or_held_bonus": False, "unknown_identity_bonus": False,
            "scientific_truth_probability": False}


def _identity(value):
    if value is None or str(value).strip().lower() in ("", "unknown", "na", "n/a", "nan", "none", "null"):
        return None
    return str(value).strip()


def evidence_counts(sources):
    """Count cited evidence only, preserving dependencies even through held rows.

    Paper IDs are preferred. Study IDs serve as an explicit proxy when no paper
    identity is available for that study. Shared identifiers form conservative
    groups; absence of a declared link does not establish independence.
    """
    studies = {_identity(r["fields"].get("study_id")) for r in sources} - {None}
    papers = {_identity(r["fields"].get("publication_id")) for r in sources} - {None}
    studies_with_papers = {_identity(r["fields"].get("study_id")) for r in sources
                           if _identity(r["fields"].get("publication_id"))} - {None}
    linked = []
    for r in sources:
        fields = r["fields"]
        study, paper = _identity(fields.get("study_id")), _identity(fields.get("publication_id"))
        # Namespace paper links separately from declared cohort identifiers.
        links = [("cohort", c) for c in fields.get("cohort_ids", []) if _identity(c)]
        if paper:
            links.append(("paper", paper))
        linked.append({"id": r["id"], "fields": {"study_id": study, "cohort_ids": links},
                       "bonus_eligible": bool(study or paper) and fields.get("source_blocked") is not True
                       and not fields.get("hold_reason")})
    components = dependency_components(linked)
    return {"paper_count": len(papers) + len(studies - studies_with_papers),
            "unique_study_count": len(studies),
            "paper_count_basis": "publication_id" if not studies - studies_with_papers else "publication_id_or_study_id_proxy",
            "missing_paper_identity_rows": sum(not _identity(r["fields"].get("publication_id"))
                                               and not _identity(r["fields"].get("study_id")) for r in sources),
            "incentive_evidence_count": sum(any(r["bonus_eligible"] for r in group) for group in components)}


def score_candidate(probability, evidence, domain, policy):
    bonus = policy["paper_count_weight"] * math.log2(1 + evidence["incentive_evidence_count"]) if domain == "meta" else 0.0
    return {**evidence, "paper_count_bonus": bonus, "ranking_score": probability + bonus,
            "ranking_paper_count_weight": policy["paper_count_weight"] if domain == "meta" else 0.0}
