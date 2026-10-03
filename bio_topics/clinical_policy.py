"""Declared question hierarchy and outcome-blind analysis policies."""
from .util import canonical

DEFAULT_PARTITION = {
    "question": ["exposure_class", "exposure_timing", "outcome_definition"],
    "stratum": ["population", "treatment_stage"],
    "sensitivity": ["population_subgroup", "exposure_definition", "comparator_type", "comparator_definition", "outcome_time",
                    "model", "effect_adjusted", "adjustment_variables", "dose", "lag", "exposure_duration",
                    "exposure_start", "exposure_updating"],
}
ACCEPTED_LEVELS = {"participant_linkage", "documented_sampling", "author_confirmation"}
EVIDENCE_LEVELS = ACCEPTED_LEVELS | {"inferred_design", "unspecified"}
ORIGINS = {"protocol", "posthoc_exploratory", "validation_hypothesis"}
ROLES = {"primary_candidate", "alternative_model", "sensitivity"}
# No estimate, p value, confidence interval, sign, significance or precision selection.
SELECTION_FIELDS = set(sum(DEFAULT_PARTITION.values(), [])) | {
    "design", "estimand", "time_zero", "measure", "unit", "analysis_variant"}


def partition(profile):
    cfg = profile.get("clinical", {})
    result = cfg.get("partition", DEFAULT_PARTITION)
    if not isinstance(result, dict) or any(not isinstance(v, list) for v in result.values()):
        raise ValueError("partition must map tier names to field lists")
    return {k: list(v) for k, v in result.items()}


def relation_accepted(rel, profile):
    levels = profile.get("clinical", {}).get("independence_policy", {}).get("accepted_levels", sorted(ACCEPTED_LEVELS))
    return rel.get("confirmed") is True and rel.get("evidence_level", "unspecified") in levels


def validate_policy(profile):
    cfg = profile.get("clinical", {})
    if "question_fields" in cfg or "analysis_fields" in cfg:
        raise ValueError("v0.3: replace question_fields/analysis_fields with clinical.partition (question/stratum/sensitivity)")
    parts = partition(profile)
    if set(parts) != {"question", "stratum", "sensitivity"}:
        raise ValueError("partition requires question, stratum and sensitivity lists")
    seen = set()
    for tier, fields in parts.items():
        if not isinstance(fields, list) or (tier == "question" and not fields):
            raise ValueError("Question hierarchy must use lists and a nonempty upper question")
        for field in fields:
            if not isinstance(field, str) or field not in SELECTION_FIELDS or field in seen:
                raise ValueError("Hierarchy fields must be clinical metadata, unique across tiers")
            seen.add(field)
    policy = cfg.get("independence_policy", {})
    if not isinstance(policy, dict) or set(policy) - {"accepted_levels"}:
        raise ValueError("Invalid independence_policy")
    levels = policy.get("accepted_levels", sorted(ACCEPTED_LEVELS))
    if not isinstance(levels, list) or not levels or not set(levels) <= ACCEPTED_LEVELS:
        raise ValueError("Accepted independence evidence must be participant linkage, documented sampling or author confirmation")
    rules = cfg.get("analysis_sets", [])
    if not isinstance(rules, list):
        raise ValueError("analysis_sets must be a list")
    seen = set()
    for rule in rules:
        if (not isinstance(rule, dict) or set(rule) - {"id", "role", "where", "source_reference", "selection_timing", "reason"}
                or not isinstance(rule.get("id"), str) or not rule["id"] or rule["id"] in seen
                or rule.get("role") not in ROLES or not isinstance(rule.get("where", {}), dict)
                or set(rule.get("where", {})) - SELECTION_FIELDS
                or not rule.get("source_reference") or not rule.get("reason")
                or rule.get("selection_timing") not in {"before_data_review", "after_data_review", "unknown"}):
            raise ValueError("Analysis-set rules require unique ID, role, metadata-only where, reason, source_reference and selection_timing")
        seen.add(rule["id"])
        for value in rule.get("where", {}).values():
            if isinstance(value, dict):
                raise ValueError("Analysis selectors support exact metadata values, not expressions")
    registry = cfg.get("question_registry", [])
    if not isinstance(registry, list):
        raise ValueError("question_registry must be a list")
    scopes = set()
    for item in registry:
        if (not isinstance(item, dict) or set(item) - {"id", "scope", "origin", "source_reference", "created_at", "before_data_review", "parent_question_id"}
                or not item.get("id") or not isinstance(item.get("scope"), dict)
                or set(item["scope"]) != set(parts["question"]) or item.get("origin") not in ORIGINS
                or not item.get("source_reference") or not item.get("created_at") or not isinstance(item.get("before_data_review"), bool)):
            raise ValueError("Question registry requires an exact upper-question scope and explicit origin provenance")
        if item["origin"] == "protocol" and not item["before_data_review"]:
            raise ValueError("A protocol question requires declared pre-data-review registration")
        scope = canonical(item["scope"])
        if scope in scopes:
            raise ValueError("Multiple provenance entries for the same upper question")
        scopes.add(scope)


def question_origin(scope, profile):
    for entry in profile.get("clinical", {}).get("question_registry", []):
        if entry["scope"] == scope:
            return {**entry, "provenance_status": "user_declared_not_independently_verified"}
    return {"origin": "posthoc_exploratory", "source_reference": "current_data_inspection",
            "created_at": None, "date_reference": "manifest.created", "before_data_review": False,
            "provenance_status": "default_exploratory"}
