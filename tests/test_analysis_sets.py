import csv
import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from bio_topics.analysis_sets import enumerate_analysis_sets, review_states, scenario_priority
from bio_topics.clinical_report import order_candidates
from bio_topics.clinical import clinical_counts, prepare, validate_config
from bio_topics.ranking import ranking_policy, score_clinical
from bio_topics.runtime import create_plan, run
from test_clinical import profile, record, rel
from test_engine import TestBackend

REVIEWED = {"source_verification_status": "full_text_verified", "source_verification_reference": "synthetic paper",
            "dual_review_status": "agreed", "reviewer_ids": ["reviewer_A", "reviewer_B"], "dual_review_reference": "review register",
            "rob_status": "assessed", "rob_judgment": "low", "rob_tool": "specified_tool", "rob_source_reference": "outcome review",
            "rob_outcome_definition": "all_cause_mortality"}


def csv_rows(path):
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))


class AnalysisSetTests(unittest.TestCase):
    def test_hierarchy_does_not_fragment_question_on_stage_model_lag_or_followup(self):
        p = profile()
        rows = prepare([record(1), record(2, treatment_stage="after_surgery"), record(3, treatment_stage="advanced"),
                        record(4, model="alternative_adjustment", lag="12_months", outcome_time="36_months")], p)
        self.assertEqual(len({r["clinical"]["question_id"] for r in rows}), 1)
        self.assertEqual(len({r["clinical"]["stratum_id"] for r in rows}), 3)
        self.assertEqual(len({r["clinical"]["analysis_id"] for r in rows}), 4)
        # Moving a dimension is a declared scientific rule, not a model guess.
        p["clinical"]["partition"] = {"question": ["exposure_class", "exposure_timing", "outcome_definition", "treatment_stage"],
                                      "stratum": ["population"], "sensitivity": ["model", "outcome_time", "lag"]}
        self.assertEqual(len({r["clinical"]["question_id"] for r in prepare([record(1), record(2, treatment_stage="advanced")], p)}), 2)

    def test_unknown_lower_tier_does_not_split_upper_question_or_become_synthesis_ready(self):
        p = profile()
        rows = prepare([record(1), record(2, population=None)], p)
        self.assertEqual(rows[0]["clinical"]["question_id"], rows[1]["clinical"]["question_id"])
        sets = list(enumerate_analysis_sets(rows, p))
        unresolved = next(s for s in sets if "R2" in s["available_record_ids"])
        self.assertFalse(unresolved["synthesis_ready"])
        self.assertEqual(unresolved["selected_record_ids"], [])

    def test_omitted_partition_field_cannot_silently_relax_synthesis_compatibility(self):
        p = profile(partition={"question": ["exposure_class", "exposure_timing", "outcome_definition"],
                               "stratum": ["population", "treatment_stage"], "sensitivity": ["model"]})
        rows = prepare([record(1), record(2, outcome_time="36_months")], p)
        self.assertEqual(rows[0]["clinical"]["question_id"], rows[1]["clinical"]["question_id"])
        self.assertNotEqual(rows[0]["clinical"]["analysis_id"], rows[1]["clinical"]["analysis_id"])
        self.assertEqual(len(list(enumerate_analysis_sets(rows, p))), 2)

    def test_partial_overlap_independence_depends_on_selected_set(self):
        p = profile(cohort_relations=[rel(1, 2, "partial_overlap"), rel(2, 3, "partial_overlap"), rel(1, 3)])
        rows = prepare([record(1), record(2), record(3)], p)
        sets = list(enumerate_analysis_sets(rows, p))
        actual = {tuple(s["selected_record_ids"]): s["independent_evidence_count"] for s in sets}
        self.assertEqual(actual, {("R1", "R3"): 2, ("R2",): 1})
        self.assertTrue(all(s["duplicate_policy"] == "maximal_sets_without_known_pairwise_overlap" for s in sets))
        self.assertEqual(scenario_priority(sets)["priority_independent_floor"], 1)

    def test_documented_sampling_counts_but_inference_and_unspecified_stay_unknown(self):
        p = profile(cohort_relations=[rel(1, 2, evidence_level="documented_sampling", rationale="Different institutions and mutually exclusive eligibility documented by source")])
        rows = prepare([record(1), record(2)], p)
        self.assertEqual(next(enumerate_analysis_sets(rows, p))["independent_evidence_count"], 2)
        for level in ("inferred_design", "unspecified"):
            p["clinical"]["cohort_relations"][0]["evidence_level"] = level
            s = next(enumerate_analysis_sets(rows, p))
            self.assertIsNone(s["available_analysis_unit_count"])
            self.assertEqual(s["selected_unit_count"], 2)
            self.assertTrue(s["unresolved_relations"])
            self.assertEqual(s["publication_credit_count"], 0)
            self.assertFalse(s["independence_evidence"][0]["accepted_for_independence"])

    def test_duplicate_publications_cannot_raise_publication_credit(self):
        p = profile()
        p["ranking"] = {"paper_count_weight": 0.25}
        one = prepare([record(1)], p)
        five = prepare([record(i, population_id="N1", study_id="S1") for i in range(1, 6)], p)
        self.assertEqual(clinical_counts(five, p)["paper_count"], 5)
        sets = list(enumerate_analysis_sets(five, p))
        self.assertEqual(len(sets), 5)
        self.assertEqual({s["publication_credit_count"] for s in sets}, {1})
        small = score_clinical(scenario_priority(list(enumerate_analysis_sets(one, p))), ranking_policy(p))
        repeated = score_clinical(scenario_priority(sets), ranking_policy(p))
        self.assertEqual(small["paper_count_bonus"], repeated["paper_count_bonus"])
        self.assertEqual(ranking_policy(profile())["paper_count_weight"], 0)

    def test_effect_direction_significance_and_precision_never_choose_representative(self):
        p = profile()
        raw = [record(1, value=0.5, p_value=0.0001), record(2, population_id="N1", value=1.0, p_value=0.8),
               record(3, population_id="N1", value=1.8, p_value=0.02)]
        first = list(enumerate_analysis_sets(prepare(raw, p), p))
        self.assertEqual({tuple(s["selected_record_ids"]) for s in first}, {("R1",), ("R2",), ("R3",)})
        changed = deepcopy(raw)
        for i, r in enumerate(changed):
            r["fields"].update(value=2.5 - i * 0.8, p_value=0.5, se=0.05 + i * 0.2)
        second = list(enumerate_analysis_sets(prepare(changed, p), p))
        self.assertEqual({tuple(s["selected_record_ids"]) for s in first}, {tuple(s["selected_record_ids"]) for s in second})
        for forbidden in ("value", "p_value", "se", "ci_lower", "significance", "direction"):
            bad = profile(analysis_sets=[{"id": "favorable", "role": "primary_candidate", "where": {forbidden: 0.05},
                                        "source_reference": "rule", "selection_timing": "after_data_review", "reason": "test"}])
            with self.subTest(field=forbidden), self.assertRaises(ValueError): validate_config(bad)

    def test_protocol_posthoc_and_validation_origins_are_distinct(self):
        registry = []
        for i, kind in enumerate(("protocol", "posthoc_exploratory", "validation_hypothesis")):
            registry.append({"id": f"Q{i}", "scope": {"exposure_class": f"class_{i}", "exposure_timing": "post_diagnosis", "outcome_definition": "all_cause_mortality"},
                             "origin": kind, "source_reference": "protocol_or_amendment", "created_at": "2026-01-01",
                             "before_data_review": kind == "protocol"})
        p = profile(question_registry=registry)
        rows = prepare([record(i, exposure_class=f"class_{i}") for i in range(4)], p)
        self.assertEqual([r["clinical"]["question_origin"]["origin"] for r in rows],
                         ["protocol", "posthoc_exploratory", "validation_hypothesis", "posthoc_exploratory"])
        registry[0]["before_data_review"] = False
        with self.assertRaises(ValueError): validate_config(p)

    def test_approval_and_inspection_do_not_imply_source_dual_review_or_rob(self):
        p = profile()
        raw = record(1, synthesis_approved=True)
        s = next(enumerate_analysis_sets(prepare([raw], p), p))
        self.assertTrue(s["synthesis_approved"])
        self.assertFalse(s["source_verified"])
        self.assertFalse(s["dual_review_completed"])
        self.assertFalse(s["outcome_rob_assessed"])
        self.assertFalse(s["synthesis_ready"])
        reviewed = record(1, **REVIEWED)
        ready = next(enumerate_analysis_sets(prepare([reviewed], p), p))
        self.assertTrue(ready["synthesis_ready"])
        reviewed["fields"]["rob_outcome_definition"] = "different_outcome"
        self.assertFalse(review_states(reviewed)["outcome_rob_assessed"])
        reviewed["fields"]["reviewer_ids"] = ["same", "same"]
        self.assertFalse(review_states(reviewed)["dual_review_completed"])

    def test_independence_priority_crosses_axes_without_comparing_incompatible_precision_numbers(self):
        base = {"route": "research", "operator": "heterogeneity", "question_complete": True, "priority_usable": True,
                "priority_worst_rob_rank": 0, "priority_completeness_floor": 1, "paper_count_bonus": 0}
        a = dict(base, id="A", priority_independent_floor=2, priority_precision_floor=0.01, priority_precision_signature="MD_cm")
        b = dict(base, id="B", priority_independent_floor=1, priority_precision_floor=10000, priority_precision_signature="log_HR")
        c = dict(base, id="C", priority_independent_floor=2, priority_precision_floor=0.02, priority_precision_signature="MD_cm")
        self.assertEqual([r["id"] for r in order_candidates([b,a,c])], ["C", "A", "B"])

    def test_candidate_links_include_opposing_null_and_background_decisions(self):
        class SelectiveBackend(TestBackend):
            def evaluate(self, state, qs):
                receipt = super().evaluate(state, qs)
                if state["unit_kind"] == "row" and state["records"][0]["fields"].get("value") >= 1:
                    for name, answer in receipt["payload"]["answers"].items():
                        if name.endswith("__discovery"):
                            answer.update(choice="background", probabilities={k: float(k == "background") for k in qs[name]["criteria"]})
                return receipt
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw = [record(1, value=0.7), record(2, value=1.0), record(3, value=1.4), record(4, value=0.6, source_blocked=True)]
            keys = sorted(set().union(*(r["fields"].keys() for r in raw)))
            with (root / "data.csv").open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=keys); writer.writeheader(); writer.writerows(r["fields"] for r in raw)
            p = profile(cohort_relations=[rel(i, j) for i in range(1, 5) for j in range(i+1, 5)])
            p.update(schema_version=1, columns={k: k for k in keys})
            (root / "p.json").write_text(json.dumps(p))
            out = root / "run"; create_plan(root / "data.csv", root / "p.json", out)
            result = run(out, backend=SelectiveBackend())
            candidates, links, sets = [csv_rows(out / name) for name in ("candidates.csv", "candidate_effects.csv", "analysis_sets.csv")]
            frozen = json.loads((out / "records.json").read_text())
            all_ids = {r["id"] for r in frozen}
            self.assertEqual(result["counts"]["coverage"], 1)
            for c in candidates:
                self.assertEqual({r["record_id"] for r in links if r["candidate_id"] == c["id"]}, all_ids)
                self.assertNotIn("independent_evidence_count", c)
                self.assertEqual(c["generated_hypothesis_origin"], "posthoc_exploratory")
            self.assertIn("held", {r["role"] for r in links})
            self.assertTrue(all(s["model_inspection_status"] == "inspected" for s in sets))
            self.assertTrue(all(s["synthesis_ready"] == "False" for s in sets))
            self.assertTrue(all(c["verification_status"] == "incomplete_or_invalid" for c in candidates))


if __name__ == "__main__": unittest.main()
