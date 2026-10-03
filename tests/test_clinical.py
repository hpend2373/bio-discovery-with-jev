import csv
import json
import io
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from bio_topics.analysis_sets import enumerate_analysis_sets, scenario_priority
from bio_topics.clinical import prepare, clinical_counts, validate_config
from bio_topics.ingest import read_profile, read_table
from bio_topics.plan import enumerate_units, preflight
from bio_topics.ranking import ranking_policy, score_clinical
from bio_topics.runtime import create_plan, run, verify
from test_engine import ROOT, TestBackend

BASE = {"population": "adults", "treatment_stage": "first_line", "exposure_class": "class_X",
        "exposure_definition": "drug_X", "exposure_timing": "post_diagnosis", "comparator_type": "nonuse",
        "comparator_definition": "nonusers", "outcome_definition": "all_cause_mortality", "outcome_time": "12_months",
        "measure": "HR", "value": 0.8, "se": 0.1, "se_scale": "log", "model": "adjusted", "estimand": "association",
        "time_zero": "diagnosis", "design": "cohort", "synthesis_approved": True}


def record(i, **overrides):
    return {"id": f"R{i}", "source_row": i + 1, "domain": "meta", "raw": {"id": str(i)}, "parse_issues": [],
            "fields": {**BASE, "publication_id": f"P{i}", "study_id": f"S{i}", "population_id": f"N{i}", **overrides}}


def profile(**clinical):
    return {"domain": "meta", "question": "Synthetic discovery", "clinical": clinical,
            "inspection": {"cell_fields": ["outcome_definition"], "pairs": "within_questions", "operators": ["heterogeneity", "decision"]},
            "synthesis": {"enabled": False}}


def rel(left, right, kind="disjoint", **kwargs):
    return {"left": f"population:N{left}", "right": f"population:N{right}", "relation": kind,
            "confirmed": True, "source_reference": "synthetic participant register",
            "evidence_level": "documented_sampling", "rationale": "Synthetic sampling-register assessment", **kwargs}


class ClinicalTests(unittest.TestCase):
    def test_alias_normalization_and_ledger_link_are_scoped_and_auditable(self):
        p = profile(ledger={"effects": [{"id": "E1", "confirmed": True, "source_reference": "table 1",
                  "fields": {"analysis_id": "A1"}}],
                  "analyses": [{"id": "A1", "confirmed": True, "source_reference": "table 1 note",
                  "fields": {"exposure_definition": "drug_X", "exposure_timing": "post_diagnosis"}}]},
                  normalization={"exposure_definition": [{"canonical": "drug_X", "aliases": ["DX"], "confirmed": True, "source_reference": "review dictionary"}]})
        records = prepare([record(1, source_effect_id="E1", exposure_definition="DX", exposure_timing=None), record(2)], p)
        a, b = records
        self.assertEqual(a["clinical"]["question_id"], b["clinical"]["question_id"])
        self.assertEqual(a["original_fields"]["exposure_definition"], "DX")
        self.assertEqual(a["fields"]["exposure_timing"], "post_diagnosis")
        self.assertEqual(len(a["clinical"]["links"]), 2)
        self.assertEqual(a["clinical"]["normalization"][0]["original"], "DX")
        self.assertEqual(a["clinical"]["conflicts"], [])
        bad = profile(ledger={"publications": [{"id": "P1", "confirmed": True, "source_reference": "paper", "fields": {"exposure_timing": "pre_diagnosis"}}]})
        with self.assertRaises(ValueError):
            validate_config(bad)

    def test_conflicts_and_unconfirmed_proposals_never_fill_metadata(self):
        entry = {"id": "E1", "confirmed": True, "source_reference": "table 2", "fields": {"exposure_timing": "pre_diagnosis"}}
        p = profile(ledger={"effects": [entry]})
        out = prepare([record(1, source_effect_id="E1")], p)[0]
        self.assertIsNone(out["fields"]["exposure_timing"])
        self.assertIn("exposure_timing", out["clinical"]["conflicts"])
        entry["confirmed"] = False
        out = prepare([record(1, source_effect_id="E1", exposure_timing=None)], p)[0]
        self.assertIsNone(out["fields"]["exposure_timing"])
        self.assertEqual(len(out["clinical"]["proposals"]), 1)

    def test_unknown_attributes_isolate_rows_and_distinct_questions_do_not_merge(self):
        p = profile()
        rows = prepare([record(1), record(2, exposure_timing="pre_diagnosis"), record(3, outcome_definition="incidence"),
                        record(4, exposure_definition="drug_Y"), record(5, exposure_timing=None), record(6, exposure_timing=None)], p)
        self.assertEqual(len({r["clinical"]["question_id"] for r in rows}), 5)
        self.assertEqual(preflight(rows, p)["pairs"], 1)
        units = list(enumerate_units(rows, p))
        self.assertEqual(sum(u["kind"] == "row" for u in units), 6)
        self.assertEqual(sum(u["kind"] == "cell" for u in units), 5)

    def test_analysis_variants_share_question_but_remain_separate(self):
        p = profile()
        rows = prepare([record(1), record(2, model="unadjusted")], p)
        self.assertEqual(rows[0]["clinical"]["question_id"], rows[1]["clinical"]["question_id"])
        self.assertNotEqual(rows[0]["clinical"]["analysis_id"], rows[1]["clinical"]["analysis_id"])
        self.assertEqual(preflight(rows, p)["pairs"], 1)
        cell = next(u for u in enumerate_units(rows, p) if u["kind"] == "cell")
        self.assertEqual(len(cell["state"]["evidence_rows"]), 2)

    def test_publications_and_populations_are_not_one_to_one(self):
        p = profile(cohort_relations=[rel(1, 2)])
        rows = prepare([record(1, publication_id="P"), record(2, publication_id="P"), record(3, population_id="N1", study_id="S1")], p)
        info = clinical_counts(rows, p)
        self.assertEqual(info["paper_count"], 2)
        self.assertEqual(info["independent_evidence_count"], 2)
        self.assertEqual(info["known_dependency_group_count"], 2)
        duplicated = rows + [deepcopy(rows[0])]
        self.assertEqual(clinical_counts(duplicated, p)["independent_evidence_count"], 2)

    def test_missing_paper_is_not_replaced_by_study_and_unknown_overlap_is_not_independence(self):
        p = profile()
        rows = prepare([record(1, publication_id=None), record(2)], p)
        info = clinical_counts(rows, p)
        self.assertEqual(info["paper_count"], 1)
        self.assertEqual(info["missing_paper_identity_rows"], 1)
        self.assertIsNone(info["independent_evidence_count"])
        self.assertEqual(info["unresolved_independence_count"], 2)
        self.assertEqual(score_clinical(scenario_priority(list(enumerate_analysis_sets(rows, p))), ranking_policy(p))["paper_count_bonus"], 0)
        lone = prepare([record(1, population_id=None, study_id="unknown")], p)
        self.assertIsNone(clinical_counts(lone, p)["independent_evidence_count"])

    def test_partial_overlap_preserved_and_same_identity_can_use_absent_bridge(self):
        p = profile(cohort_relations=[rel(1, 2, "partial_overlap")])
        rows = prepare([record(1), record(2)], p)
        info = clinical_counts(rows, p)
        self.assertEqual(info["known_dependency_group_count"], 1)
        self.assertEqual(info["population_count"], 2)
        self.assertIsNone(info["independent_evidence_count"])
        self.assertEqual(info["cohort_relations"][0]["relation"], "partial_overlap")
        p["clinical"]["cohort_relations"] = [rel(1, 9, "same"), rel(9, 2, "same")]
        info = clinical_counts(rows, p)
        self.assertEqual(info["independent_evidence_count"], 1)

    def test_relation_conflicts_are_reported_and_unrelated_conflicts_do_not_leak(self):
        p = profile(cohort_relations=[rel(1, 2, "same"), rel(1, 2)])
        rows = prepare([record(1), record(2)], p)
        info = clinical_counts(rows, p)
        self.assertTrue(info["relation_conflicts"])
        self.assertIsNone(info["independent_evidence_count"])
        p["clinical"]["cohort_relations"] = [rel(8, 9, "same"), rel(8, 9)]
        info = clinical_counts(prepare([record(1)], p), p)
        self.assertEqual(info["relation_conflicts"], [])
        self.assertEqual(info["independent_evidence_count"], 1)

    def test_context_and_blocked_rows_inspected_without_bonus(self):
        p = profile(cohort_relations=[rel(1, 2)])
        rows = prepare([record(1, analysis_role="context", measure="median"), record(2, source_blocked=True)], p)
        info = clinical_counts(rows, p)
        self.assertEqual(info["paper_count"], 2)
        self.assertEqual(info["eligible_paper_count"], 0)
        self.assertEqual(score_clinical(scenario_priority(list(enumerate_analysis_sets(rows, p))), ranking_policy(p))["ranking_score"], 0)
        self.assertEqual(sum(u["kind"] == "row" for u in enumerate_units(rows, p)), 2)

    def test_synthesis_never_duplicates_same_population_and_blocks_unknown_overlap(self):
        p = profile(cohort_relations=[rel(1, 2, "same")])
        p["synthesis"] = {"enabled": True, "policy": "one_per_dependency_component", "methods": ["fixed_iv"],
                          "ci_level": 0.95, "required_fields": ["population_id", "measure"]}
        reviewed = {"source_verification_status": "full_text_verified", "source_verification_reference": "paper",
                    "dual_review_status": "agreed", "reviewer_ids": ["A", "B"], "dual_review_reference": "review_log",
                    "rob_status": "assessed", "rob_judgment": "low", "rob_tool": "declared_tool",
                    "rob_source_reference": "rob_log", "rob_outcome_definition": "all_cause_mortality"}
        rows = prepare([record(1, **reviewed), record(2, **reviewed)], p)
        pooled = [u for u in enumerate_units(rows, p) if u["kind"] == "multiverse"]
        self.assertEqual(len(pooled), 2)
        self.assertTrue(all(u["state"]["observations"]["k_dependency_components"] == 1 for u in pooled))
        p["clinical"]["cohort_relations"] = []
        self.assertFalse(any(u["kind"] == "multiverse" for u in enumerate_units(rows, p)))

    def test_csv_aggregation_is_lossless_for_success_background_failure_and_pending(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = profile(cohort_relations=[rel(1, 2)])
            p.update(schema_version=1, columns={k: k for k in record(1)["fields"]})
            data, cfg = root / "data.csv", root / "profile.json"
            with data.open("w", newline="") as handle:
                w = csv.DictWriter(handle, fieldnames=p["columns"])
                w.writeheader()
                w.writerows([record(1)["fields"], record(2)["fields"]])
            cfg.write_text(json.dumps(p))
            out = root / "run"
            create_plan(data, cfg, out)
            result = run(out, backend=TestBackend())
            candidates = list(csv.DictReader(io.StringIO((out / "candidates.csv").read_text(encoding="utf-8-sig"))))
            inspections = list(csv.DictReader(io.StringIO((out / "inspection_results.csv").read_text(encoding="utf-8-sig"))))
            self.assertEqual(len(inspections), 10)
            self.assertEqual(len(candidates), 2)
            self.assertEqual(result["candidates"], 2)
            self.assertEqual({int(c["paper_count"]) for c in candidates}, {2})
            self.assertEqual({s["independent_evidence_count"] for c in candidates for s in json.loads(c["analysis_set_counts"])}, {2})
            mapped = {j for c in candidates for j in json.loads(c["inspection_ids"])}
            self.assertEqual(mapped, {i["job_id"] for i in inspections})
            self.assertTrue(all(json.loads(i["candidate_ids"]) for i in inspections))
            self.assertTrue(all(c["verification_status"] == "incomplete_or_invalid" for c in candidates))
            self.assertTrue((out / "clinical-audit.json").exists())
            out2 = root / "new_cache" / "failed"
            create_plan(data, cfg, out2)
            run(out2, backend=TestBackend(fail_at=2))
            failed = list(csv.DictReader(io.StringIO((out2 / "inspection_results.csv").read_text(encoding="utf-8-sig"))))
            self.assertEqual(len(failed), 10)
            self.assertEqual(sum(i["status"] == "failed" for i in failed), 2)
            self.assertTrue(all(not json.loads(i["candidate_ids"]) for i in failed if i["status"] == "failed"))

    def test_external_ledger_is_frozen_and_tampering_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "effects.csv").write_text("id,exposure\nE1,drug_X\n")
            (root / "data.csv").write_text("study,paper,effect,measure,value\nS1,P1,E1,HR,0.8\n")
            p = profile(ledger_files=[{"entity": "effects", "path": "effects.csv", "id_column": "id",
                        "columns": {"exposure_definition": "exposure"}, "confirmed": True, "source_reference": "synthetic ledger"}])
            p.update(schema_version=1, columns={"study_id": "study", "publication_id": "paper", "source_effect_id": "effect", "measure": "measure", "value": "value"})
            cfg = root / "profile.json"
            cfg.write_text(json.dumps(p))
            out = root / "run"
            create_plan(root / "data.csv", cfg, out)
            records = json.loads((out / "records.json").read_text())
            self.assertEqual(records[0]["fields"]["exposure_definition"], "drug_X")
            (root / "effects.csv").unlink()
            self.assertNotIn("normalized_records_do_not_match_source", verify(out)["errors"])
            (out / "ledger_inputs/0.csv").write_text("tampered")
            self.assertIn("frozen_ledger_changed:ledger_inputs/0.csv", verify(out)["errors"])


if __name__ == "__main__":
    unittest.main()
