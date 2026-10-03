"""Auditable ledger linkage, question partitions, and explicit dependency evidence.

No fuzzy linkage, inferred independence, measure conversion, or metadata imputation.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from itertools import combinations
import math
import unicodedata

from .util import canonical, digest

QUESTION_FIELDS = ("population", "treatment_stage", "exposure_class", "exposure_definition",
                   "exposure_timing", "comparator_type", "comparator_definition",
                   "outcome_definition", "outcome_time")
ANALYSIS_FIELDS = ("estimand", "time_zero", "design", "measure", "unit", "model",
                   "effect_adjusted", "adjustment_variables", "dose", "lag", "exposure_duration")
IDENTITIES = {"publications": "publication_id", "studies": "study_id", "populations": "population_id",
              "analyses": "analysis_id", "effects": "source_effect_id"}
PUBLICATION_FIELDS = {"doi", "pmid", "title", "year", "authors"}
STUDY_FIELDS = {"design", "data_source", "country"}
POPULATION_FIELDS = {"study_id", "cohort_ids", "population", "population_subgroup", "treatment_stage",
                     "recruitment_start", "recruitment_end", "institutions", "eligibility"}
ANALYSIS_METADATA = set(QUESTION_FIELDS + ANALYSIS_FIELDS) | {"population_id", "study_id", "cohort_ids",
                   "analysis_role", "outcome_family", "exposure_start", "exposure_updating"}
ALLOWED = {"publications": PUBLICATION_FIELDS, "studies": STUDY_FIELDS, "populations": POPULATION_FIELDS,
           "analyses": ANALYSIS_METADATA, "effects": ANALYSIS_METADATA | {"publication_id", "analysis_id"}}
RELATIONS = {"same", "partial_overlap", "contains", "disjoint", "unknown"}


def known(value):
    return value is not None and value != [] and str(value).strip().casefold() not in {
        "", "unknown", "na", "n/a", "nan", "none", "null"}


def lexical(value):
    return " ".join(unicodedata.normalize("NFKC", str(value)).split()).casefold()


def enabled(profile):
    return profile.get("domain") == "meta" and profile.get("clinical", {}).get("enabled", True)


def validate_config(profile):
    cfg = profile.get("clinical", {})
    allowed = {"enabled", "ledger", "normalization", "question_fields", "analysis_fields", "cohort_relations", "ledger_inputs"}
    if not isinstance(cfg, dict) or set(cfg) - allowed:
        raise ValueError("Unknown clinical configuration key")
    if "enabled" in cfg and not isinstance(cfg["enabled"], bool):
        raise ValueError("clinical.enabled must be boolean")
    for name in ("question_fields", "analysis_fields"):
        if name in cfg and (not isinstance(cfg[name], list) or any(not isinstance(v, str) or not v for v in cfg[name])
                            or len(set(cfg[name])) != len(cfg[name])):
            raise ValueError(name + " must be a unique list of additional fields")
    ledger = cfg.get("ledger", {})
    if not isinstance(ledger, dict) or set(ledger) - set(IDENTITIES):
        raise ValueError("Unknown ledger entity type")
    for entity, entries in ledger.items():
        seen = set()
        if not isinstance(entries, list):
            raise ValueError("Ledger entries must be a list")
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) - {"id", "fields", "source_reference", "confirmed"}:
                raise ValueError("Invalid ledger entry")
            if not isinstance(entry.get("id"), str) or not known(entry["id"]) or entry["id"] in seen:
                raise ValueError("Ledger IDs must be nonempty and unique within entity type")
            seen.add(entry["id"])
            if not isinstance(entry.get("fields"), dict) or set(entry["fields"]) - ALLOWED[entity]:
                raise ValueError("Fields cannot be inherited at this ledger scope: " + entity)
            if not isinstance(entry.get("confirmed"), bool) or not entry.get("source_reference"):
                raise ValueError("Ledger entry requires confirmed and source_reference")
            for field, value in entry["fields"].items():
                if field in {"cohort_ids", "adjustment_variables"}:
                    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                        raise ValueError(field + " must be a string list")
                elif field == "effect_adjusted":
                    if value is not None and not isinstance(value, bool):
                        raise ValueError("effect_adjusted must be boolean")
                elif value is not None and not isinstance(value, (str, int, float)):
                    raise ValueError("Invalid ledger scalar: " + field)
    norm = cfg.get("normalization", {})
    if not isinstance(norm, dict) or set(norm) - (ANALYSIS_METADATA - {"study_id", "population_id", "cohort_ids"}):
        raise ValueError("Normalization is restricted to clinical attributes")
    for field, rules in norm.items():
        seen = {}
        if not isinstance(rules, list):
            raise ValueError("Normalization rules must be a list")
        for rule in rules:
            if (not isinstance(rule, dict) or set(rule) != {"canonical", "aliases", "confirmed", "source_reference"}
                    or not isinstance(rule["canonical"], str) or not known(rule["canonical"])
                    or not isinstance(rule["aliases"], list) or any(not isinstance(a, str) or not known(a) for a in rule["aliases"])
                    or not isinstance(rule["confirmed"], bool) or not rule["source_reference"]):
                raise ValueError("Invalid normalization rule")
            if rule["confirmed"]:
                for alias in rule["aliases"] + [rule["canonical"]]:
                    key = lexical(alias)
                    if key in seen and seen[key] != rule["canonical"]:
                        raise ValueError("Ambiguous confirmed normalization: " + field)
                    seen[key] = rule["canonical"]
    rels = cfg.get("cohort_relations", [])
    if not isinstance(rels, list):
        raise ValueError("cohort_relations must be a list")
    for rel in rels:
        if (not isinstance(rel, dict) or set(rel) - {"left", "right", "relation", "confirmed", "source_reference", "question_scope"}
                or rel.get("relation") not in RELATIONS or not isinstance(rel.get("confirmed"), bool)
                or not rel.get("source_reference") or not isinstance(rel.get("question_scope", {}), dict)):
            raise ValueError("Invalid cohort relation")
        for end in ("left", "right"):
            if not isinstance(rel.get(end), str) or not rel[end].startswith(("population:", "cohort:")) or not known(rel[end].split(":", 1)[1]):
                raise ValueError("Relation endpoints require population:ID or cohort:ID")


def axes(profile, kind):
    base = QUESTION_FIELDS + ("population_subgroup", "exposure_start", "exposure_updating") if kind == "question" else ANALYSIS_FIELDS
    return tuple(dict.fromkeys(base + tuple(profile.get("clinical", {}).get(kind + "_fields", []))))


def required_axes():
    return QUESTION_FIELDS


def normalized_value(value, field, cfg):
    if isinstance(value, str):
        for rule in cfg.get("normalization", {}).get(field, []):
            if rule["confirmed"] and lexical(value) in {lexical(a) for a in rule["aliases"] + [rule["canonical"]]}:
                return rule["canonical"]
    return value


def prepare(records, profile):
    """Link only explicit scoped identities; freeze all proposals and conflicts."""
    if not enabled(profile):
        return records
    validate_config(profile)
    cfg = profile.get("clinical", {})
    indexes = {entity: {e["id"]: e for e in cfg.get("ledger", {}).get(entity, [])} for entity in IDENTITIES}
    result = deepcopy(records)
    for record in result:
        f = record["fields"]
        record["original_fields"] = deepcopy(f)
        provenance = {k: [{"value": deepcopy(v), "source": "profile_declaration" if k in profile.get("declarations", {}) and k not in profile.get("columns", {}) else "input", "source_row": record["source_row"]}]
                      for k, v in f.items() if known(v)}
        conflicts, proposals, links = set(), [], []
        for entity in ("effects", "analyses", "populations", "studies", "publications"):
            identifier = f.get(IDENTITIES[entity])
            entry = indexes[entity].get(identifier) if isinstance(identifier, str) else None
            if entry is None:
                continue
            links.append({"entity": entity, "id": identifier, "source_reference": entry["source_reference"],
                          "confirmed": entry["confirmed"]})
            if not entry["confirmed"]:
                proposals.append({"entity": entity, **deepcopy(entry)})
                continue
            for field, value in entry["fields"].items():
                if not known(value):
                    continue
                provenance.setdefault(field, []).append({"value": deepcopy(value), "source": "ledger", "entity": entity,
                                                        "id": identifier, "source_reference": entry["source_reference"]})
                if field in conflicts:
                    continue
                if known(f.get(field)) and canonical(normalized_value(f[field], field, cfg)) != canonical(normalized_value(value, field, cfg)):
                    conflicts.add(field)
                    f[field] = None
                elif not known(f.get(field)):
                    f[field] = deepcopy(value)
        normalization = []
        for field, rules in cfg.get("normalization", {}).items():
            if field in conflicts or not known(f.get(field)) or not isinstance(f[field], str):
                continue
            for rule in rules:
                if lexical(f[field]) in {lexical(a) for a in rule["aliases"] + [rule["canonical"]]}:
                    normalization.append({"field": field, "original": f[field], **deepcopy(rule)})
                    if rule["confirmed"]:
                        f[field] = rule["canonical"]
                        break
        missing = [k for k in tuple(dict.fromkeys(required_axes() + tuple(cfg.get("question_fields", [])))) if not known(f.get(k))]
        scope = {k: f.get(k) if known(f.get(k)) else None for k in axes(profile, "question")}
        # Missing required meanings never establish equivalence across different rows.
        discriminator = record["id"] if missing or conflicts else None
        qid = "Q" + digest([scope, discriminator])[:24]
        analysis_scope = {k: f.get(k) if known(f.get(k)) else None for k in axes(profile, "analysis")}
        aid = "A" + digest([qid, analysis_scope])[:24]
        role = f.get("analysis_role")
        if role not in ("effect", "context"):
            role = "effect" if f.get("measure") in {"OR", "RR", "HR", "IRR", "MD", "SMD"} else "unresolved"
        f.update(clinical_question_id=qid, clinical_analysis_id=aid)
        record["clinical"] = {"question_id": qid, "question_scope": scope, "analysis_id": aid,
                              "analysis_scope": analysis_scope, "role": role, "missing_question_fields": missing,
                              "conflicts": sorted(conflicts), "links": links, "proposals": proposals,
                              "provenance": provenance, "normalization": normalization}
    return result


def audit(records, profile):
    return {"version": 1, "rows": len(records), "questions": len({r["clinical"]["question_id"] for r in records}),
            "unresolved_rows": sum(bool(r["clinical"]["missing_question_fields"] or r["clinical"]["conflicts"]) for r in records),
            "relation_declarations": profile.get("clinical", {}).get("cohort_relations", []),
            "records": [{"record_id": r["id"], **r["clinical"]} for r in records]}


class Components:
    def __init__(self, nodes):
        self.parents = {n: n for n in nodes}

    def root(self, node):
        if self.parents[node] != node:
            self.parents[node] = self.root(self.parents[node])
        return self.parents[node]

    def join(self, a, b):
        a, b = self.root(a), self.root(b)
        self.parents[max(a, b)] = min(a, b)


def population_node(record):
    f = record["fields"]
    if known(f.get("population_id")):
        return "population:" + str(f["population_id"]), True
    cohorts = sorted(set(c for c in f.get("cohort_ids", []) if known(c)))
    if len(cohorts) == 1:
        return "cohort:" + cohorts[0], True
    # Never split a combined estimate into multiple independent contributions.
    if cohorts:
        return "combined:" + digest(cohorts)[:16], False
    if known(f.get("study_id")):
        return "study_unresolved:" + str(f["study_id"]), False
    return "row_unresolved:" + record["id"], False


def clinical_counts(records, profile):
    papers = {str(r["fields"]["publication_id"]) for r in records if known(r["fields"].get("publication_id"))}
    studies = {str(r["fields"]["study_id"]) for r in records if known(r["fields"].get("study_id"))}
    cohorts = {c for r in records for c in r["fields"].get("cohort_ids", []) if known(c)}
    effect_records = [r for r in records if r["clinical"]["role"] == "effect"]
    def valid_point(r):
        value = r["fields"].get("value")
        measure = r["fields"].get("measure")
        return (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                and measure in {"OR", "RR", "HR", "IRR", "MD", "SMD"}
                and (measure in {"MD", "SMD"} or value > 0))
    eligible = [r for r in effect_records if valid_point(r) and r["fields"].get("source_blocked") is not True and not r["fields"].get("hold_reason")
                and not r["clinical"]["conflicts"] and not r["clinical"]["missing_question_fields"]]
    nodes = {population_node(r)[0] for r in effect_records}
    relations = []
    scopes = [r["clinical"]["question_scope"] for r in records]
    for rel in profile.get("clinical", {}).get("cohort_relations", []):
        if not all(all(scope.get(k) == v for k, v in rel.get("question_scope", {}).items()) for scope in scopes):
            continue
        relations.append(rel)
    # Keep identity/overlap bridges outside this candidate, but do not import unrelated conflicts.
    reachable = set(nodes)
    changed = True
    while changed:
        before = len(reachable)
        for rel in relations:
            if rel["confirmed"] and rel["relation"] in {"same", "partial_overlap", "contains"} and {rel["left"], rel["right"]} & reachable:
                reachable.update((rel["left"], rel["right"]))
        changed = len(reachable) != before
    relations = [r for r in relations if {r["left"], r["right"]} <= reachable]
    graph_nodes = reachable
    identity = Components(graph_nodes)
    dependencies = Components(graph_nodes)
    for rel in relations:
        if rel["confirmed"] and rel["relation"] == "same":
            identity.join(rel["left"], rel["right"])
    for rel in relations:
        if rel["confirmed"] and rel["relation"] in {"same", "partial_overlap", "contains"}:
            dependencies.join(rel["left"], rel["right"])
    matrix = defaultdict(set)
    conflicts = []
    for rel in relations:
        if not rel["confirmed"] or rel["relation"] == "unknown":
            continue
        a, b = identity.root(rel["left"]), identity.root(rel["right"])
        key = tuple(sorted((a, b)))
        matrix[key].add(rel["relation"])
        if a == b and rel["relation"] != "same":
            conflicts.append({"issue": "relation_within_identical_population", "relation": rel})
    for key, kinds in matrix.items():
        if "disjoint" in kinds and kinds & {"same", "partial_overlap", "contains"}:
            conflicts.append({"issue": "conflicting_overlap_relations", "nodes": key})
    def assess(selected):
        selected_nodes = {identity.root(population_node(r)[0]) for r in selected}
        unresolved = {identity.root(population_node(r)[0]) for r in selected if not population_node(r)[1]}
        for a, b in combinations(sorted(selected_nodes), 2):
            if matrix.get((a, b)) != {"disjoint"}:
                unresolved.update((a, b))
        if conflicts:
            unresolved.update(selected_nodes)
        return (None if unresolved else len(selected_nodes)), unresolved, selected_nodes
    independent, unknown_nodes, all_nodes = assess(effect_records)
    eligible_independent, eligible_unknown, eligible_nodes = assess(eligible)
    eligible_papers = {str(r["fields"]["publication_id"]) for r in eligible if known(r["fields"].get("publication_id"))}
    return {"paper_count": len(papers), "paper_count_basis": "publication_id_only", "unique_study_count": len(studies),
            "missing_paper_identity_rows": sum(not known(r["fields"].get("publication_id")) for r in records),
            "cohort_count": len(cohorts), "population_count": len({population_node(r)[0] for r in effect_records if population_node(r)[1]}),
            "known_dependency_group_count": len({dependencies.root(n) for n in nodes}),
            "independent_evidence_count": independent,
            "independence_status": "unresolved" if independent is None else "confirmed_for_cited_effect_evidence" if effect_records else "no_effect_evidence",
            "eligible_independent_evidence_count": eligible_independent,
            "unresolved_independence_count": len(unknown_nodes), "eligible_paper_count": len(eligible_papers),
            "eligible_evidence_count": len(eligible_nodes), "eligible_record_count": len(eligible),
            "relation_conflicts": conflicts, "cohort_relations": relations,
            "incentive_evidence_count": eligible_independent or 0,
            "population_component_by_record": {r["id"]: identity.root(population_node(r)[0]) for r in effect_records}}
