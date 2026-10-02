"""Transparent arithmetic and provenance. Never select research candidates here."""
import itertools
import math
from collections import Counter, defaultdict
from statistics import NormalDist

from .util import digest

RATIOS = {"OR", "RR", "HR", "IRR"}
DIFFERENCES = {"MD", "SMD"}


def record_facts(record):
    f = record["fields"]
    issues = list(record["parse_issues"])
    result = {"record_id": record["id"], "issues": issues, "effect": None}
    for key in ("fdr", "p_value"):
        if f.get(key) is not None and not 0 <= f[key] <= 1:
            issues.append({"field": key, "issue": "확률 범위를 벗어남"})
    if record["domain"] == "deg":
        result["observed_direction"] = ("positive" if f["log2fc"] > 0 else "negative" if f["log2fc"] < 0 else "zero") if f.get("log2fc") is not None else "unknown"
        return result
    measure, value = f.get("measure"), f.get("value")
    if measure not in RATIOS | DIFFERENCES:
        issues.append({"field": "measure", "issue": "이 척도는 개별 검사 가능, v0.1 효과량 합성은 미지원"})
        return result
    if value is None or (measure in RATIOS and value <= 0):
        issues.append({"field": "value", "issue": "효과값 누락 또는 척도 정의역 오류"})
        return result
    transform = math.log if measure in RATIOS else float
    axis = "log" if measure in RATIOS else "identity"
    yi = transform(value)
    se = f.get("se")
    se_source = "reported"
    if se is not None and (se <= 0 or f.get("se_scale") != axis):
        issues.append({"field": "se", "issue": "SE가 양수가 아니거나 se_scale이 분석 축과 일치하지 않음"})
        se = None
    lower, upper = f.get("ci_lower"), f.get("ci_upper")
    level = f.get("ci_level")
    if lower is not None and upper is not None:
        if lower >= upper or (measure in RATIOS and lower <= 0):
            issues.append({"field": "ci", "issue": "CI 경계 순서/정의역 오류"})
        elif f.get("ci_method") == "wald" and f.get("ci_distribution") == "normal" and level is not None and 0 < level < 1:
            lo, hi = transform(lower), transform(upper)
            tol = max(0.02 * (hi - lo), 0.002)
            if not lower <= value <= upper or abs((lo + hi) / 2 - yi) > tol:
                issues.append({"field": "ci", "issue": "정규 Wald 구간의 중심과 효과값이 불일치; 역산하지 않음"})
            elif se is None:
                se = (hi - lo) / (2 * NormalDist().inv_cdf((1 + level) / 2))
                se_source = "derived_from_declared_normal_wald_ci"
        elif se is None:
            issues.append({"field": "ci", "issue": "CI 방법·분포·수준을 확인해야 SE 역산 가능"})
    if se is not None and se > 0:
        result["effect"] = {"measure": measure, "axis": axis, "yi": yi, "se": se, "vi": se * se,
                            "se_source": se_source}
    else:
        issues.append({"field": "precision", "issue": "합성 가능한 SE가 없음"})
    return result


def group_key(record, fields):
    return tuple(str(record["fields"].get(f) if record["fields"].get(f) is not None else "unknown") for f in fields)


def group_records(records, fields):
    groups = defaultdict(list)
    for record in records:
        groups[group_key(record, fields)].append(record)
    return sorted(groups.items())


def dependency_components(records):
    """Conservative connected components: shared study or declared cohort identity."""
    parent = list(range(len(records)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    seen = {}
    for i, record in enumerate(records):
        f = record["fields"]
        keys = [("study", f["study_id"])] if f.get("study_id") else [("row", record["id"])]
        keys += [("cohort", c) for c in f.get("cohort_ids", [])]
        for key in keys:
            if key in seen:
                parent[root(i)] = root(seen[key])
            else:
                seen[key] = i
    groups = defaultdict(list)
    for i, record in enumerate(records):
        groups[root(i)].append(record)
    return sorted((sorted(g, key=lambda r: r["id"]) for g in groups.values()), key=lambda g: g[0]["id"])


def summarize(records, facts):
    fields = [r["fields"] for r in records]
    result = {"records": len(records), "study_ids": sorted({f["study_id"] for f in fields if f.get("study_id")}),
              "record_issue_count": sum(len(facts[r["id"]]["issues"]) for r in records),
              "blocked_records": sum(f.get("source_blocked") is True for f in fields),
              "approved_records": sum(f.get("synthesis_approved") is True for f in fields)}
    if records[0]["domain"] == "deg":
        result["direction_counts"] = dict(Counter(facts[r["id"]]["observed_direction"] for r in records))
        result["fdr_available"] = sum(f.get("fdr") is not None for f in fields)
        result["limits"] = ["DEG summary only; no subject-level association, flux, or causal transfer established."]
    else:
        result["dependency_components"] = len(dependency_components(records))
        result["measures"] = sorted({f.get("measure", "unknown") for f in fields})
        result["limits"] = ["Declared cohort links are not proof of independence between other studies.",
                            "No effect-measure conversions, meta-regression, or funnel-asymmetry tests in v0.1."]
    return result


def synthesize(selected, facts, method, level):
    effects = [facts[r["id"]]["effect"] for r in selected]
    if len({e["measure"] for e in effects}) != 1:
        raise ValueError("합성에서 척도 혼합 금지")
    weights = [1 / e["vi"] for e in effects]
    total = sum(weights)
    mean = sum(w * e["yi"] for w, e in zip(weights, effects)) / total
    q = sum(w * (e["yi"] - mean) ** 2 for w, e in zip(weights, effects))
    k = len(effects)
    c = total - sum(w * w for w in weights) / total
    tau2 = max(0.0, (q - (k - 1)) / c) if k > 1 and c > 0 else 0.0
    if method == "random_dl":
        weights = [1 / (e["vi"] + tau2) for e in effects]
        total = sum(weights)
        mean = sum(w * e["yi"] for w, e in zip(weights, effects)) / total
    se = math.sqrt(1 / total)
    z = NormalDist().inv_cdf((1 + level) / 2)
    transform = math.exp if effects[0]["axis"] == "log" else float
    return {"method": method, "k_dependency_components": k, "measure": effects[0]["measure"],
            "axis": effects[0]["axis"], "estimate_axis": mean, "estimate": transform(mean),
            "ci_lower": transform(mean - z * se), "ci_upper": transform(mean + z * se),
            "ci_level": level, "ci_method": "normal_wald", "tau2_dl": tau2 if k > 1 else None,
            "i2_descriptive": max(0.0, (q - k + 1) / q) if k >= 3 and q > 0 else None,
            "assumptions": ["one estimate per declared dependency component", "normal sampling approximation"],
            "limits": ["Exploratory synthesis; not an approved primary conclusion.",
                       "DL/Wald uncertainty is unreliable with few independent studies; no prediction interval.",
                       "No new causal identification is provided by pooling."]}


def compatible_for_synthesis(record, facts, config):
    f = record["fields"]
    reasons = []
    if f.get("synthesis_approved") is not True:
        reasons.append("synthesis_not_approved")
    if f.get("source_blocked") is True or f.get("hold_reason"):
        reasons.append("blocked_or_held")
    if facts[record["id"]]["effect"] is None or facts[record["id"]]["issues"]:
        reasons.append("invalid_or_unverified_effect")
    for key in config["required_fields"]:
        if f.get(key) in (None, "", "unknown", []):
            reasons.append("missing_" + key)
    if f.get("measure") == "MD" and not f.get("unit"):
        reasons.append("missing_MD_unit")
    return reasons


def multiverse(records, facts, config):
    """Full Cartesian product; no count/time cap, no model-based pruning."""
    eligible = [r for r in records if not compatible_for_synthesis(r, facts, config)]
    if not eligible:
        return
    components = dependency_components(eligible)
    for selected_tuple in itertools.product(*components):
        selected = list(selected_tuple)
        for method in config["methods"]:
            value = synthesize(selected, facts, method, config["ci_level"])
            yield selected, value, "multiverse"
            if config.get("leave_one_component_out") and len(selected) > 1:
                for i in range(len(selected)):
                    remaining = selected[:i] + selected[i + 1:]
                    loo = synthesize(remaining, facts, method, config["ci_level"])
                    loo["excluded_record"] = selected[i]["id"]
                    loo["full_estimate_axis"] = value["estimate_axis"]
                    loo["change_axis"] = loo["estimate_axis"] - value["estimate_axis"]
                    loo["direction_changed"] = (loo["estimate_axis"] > 0) != (value["estimate_axis"] > 0)
                    yield remaining, loo, "leave_one_component_out"
