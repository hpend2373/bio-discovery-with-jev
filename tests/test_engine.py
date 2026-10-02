import csv
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from bio_topics.backend import validate_response
from bio_topics.facts import dependency_components, record_facts, synthesize
from bio_topics.ingest import read_profile, read_table
from bio_topics.plan import FOCI, enumerate_units, operators, questions
from bio_topics.runtime import create_plan, run, verify
from bio_topics.store import connect, counts
from bio_topics.util import canonical, digest

ROOT = Path(__file__).resolve().parents[1]


class TestBackend:
    simulated = True
    identity = {"kind": "test_only", "model": "simulation-v1"}

    def __init__(self, fail_at=None, interrupt_at=None):
        self.calls = 0
        self.fail_at, self.interrupt_at = fail_at, interrupt_at

    def evaluate(self, state, qs):
        self.calls += 1
        if self.calls == self.interrupt_at:
            raise KeyboardInterrupt()
        if self.calls == self.fail_at:
            raise RuntimeError("injected transport failure")
        answers = {}
        for name, q in qs.items():
            choice = "candidate" if name == "discovery" or name.endswith("__discovery") else "pattern"
            answers[name] = {"type": "choice", "choice": choice,
                             "probabilities": {key: float(key == choice) for key in q["criteria"]}}
        return {"payload": {"model": "simulation-v1", "answers": answers},
                "provider_identity": self.identity, "context_receipt": None}


class AdapterTests(unittest.TestCase):
    def test_declared_ci_percent_conversion_preserves_raw(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "data.csv"
            path.write_text("study,measure,value,level\nS1,HR,1.2,95\nS2,HR,0.8,99\n")
            p = {"domain": "meta", "columns": {"study_id": "study", "measure": "measure", "value": "value", "ci_level": "level"},
                 "transforms": {"ci_level": "percent_to_fraction"}}
            records, _ = read_table(path, p)
            self.assertEqual([r["fields"]["ci_level"] for r in records], [0.95, 0.99])
            self.assertEqual([r["raw"]["level"] for r in records], ["95", "99"])

    def test_all_rows_including_weak_and_held(self):
        p = read_profile(ROOT / "profiles/deg.example.yaml")
        records, _ = read_table(ROOT / "examples/deg.csv", p)
        units = list(enumerate_units(records, p))
        self.assertEqual(len([u for u in units if u["kind"] == "row"]), 3)
        self.assertEqual(len([u for u in units if u["kind"] == "pair"]), 1)
        weak = next(r for r in records if r["fields"]["fdr"] == 0.9)
        self.assertTrue(any(weak["id"] in u["record_ids"] for u in units if u["kind"] == "row"))

    def test_meta_blocked_is_inspected_but_not_pooled(self):
        p = read_profile(ROOT / "profiles/meta.example.yaml")
        records, _ = read_table(ROOT / "examples/meta.csv", p)
        units = list(enumerate_units(records, p))
        held = records[-1]["id"]
        self.assertTrue(any(u["kind"] == "row" and held in u["record_ids"] for u in units))
        pooled = [u for u in units if u["kind"] == "multiverse"]
        self.assertEqual(len(pooled), 2)
        self.assertTrue(all(held not in u["record_ids"] for u in pooled))
        self.assertEqual({u["state"]["observations"]["k_dependency_components"] for u in pooled}, {2})

    def test_no_OR_RR_pool_even_if_cell_omits_measure(self):
        p = read_profile(ROOT / "profiles/meta.example.yaml")
        records, _ = read_table(ROOT / "examples/meta.csv", p)
        records[0]["fields"]["measure"] = "OR"
        records[1]["fields"]["measure"] = "RR"
        p["inspection"]["cell_fields"] = ["outcome_family"]
        for u in enumerate_units(records, p):
            if u["kind"] == "multiverse":
                by_id = {r["id"]: r for r in records}
                self.assertEqual(len({by_id[i]["fields"]["measure"] for i in u["record_ids"]}), 1)

    def test_asymmetric_non_wald_not_automatically_error(self):
        r = {"id": "r", "domain": "meta", "parse_issues": [],
             "fields": {"measure": "OR", "value": 1.2, "ci_lower": 1.0, "ci_upper": 2.0,
                        "ci_method": "profile_likelihood", "ci_level": 0.95, "se": 0.2, "se_scale": "log"}}
        self.assertIsNotNone(record_facts(r)["effect"])
        self.assertFalse(record_facts(r)["issues"])

    def test_shared_cohort_and_study_dependency(self):
        records = [{"id": str(i), "fields": {"study_id": s, "cohort_ids": c}}
                   for i, (s, c) in enumerate([("a", ["x"]), ("b", ["x"]), ("b", ["y"]), ("c", ["z"])])]
        self.assertEqual([len(g) for g in dependency_components(records)], [3, 1])

    def test_known_inverse_variance_result(self):
        records = [{"id": "a"}, {"id": "b"}]
        facts = {i: {"effect": {"measure": "MD", "axis": "identity", "yi": v, "vi": 1.0}}
                 for i, v in (("a", 1.0), ("b", 3.0))}
        result = synthesize(records, facts, "fixed_iv", 0.95)
        self.assertAlmostEqual(result["estimate"], 2.0)
        self.assertIsNone(result["i2_descriptive"])

    def test_xlsx_inline_strings_and_formula_rejection(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "a.xlsx"
            prefix = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            rows = '<row r="1"><c r="A1" t="inlineStr"><is><t>gene</t></is></c><c r="B1" t="inlineStr"><is><t>contrast</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>X</t></is></c><c r="B2" t="inlineStr"><is><t>T_vs_C</t></is></c></row>'
            def build(content):
                with zipfile.ZipFile(path, "w") as z:
                    z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>')
                    z.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
                    z.writestr("xl/worksheets/sheet1.xml", prefix + content + '</sheetData></worksheet>')
            p = {"domain": "deg", "columns": {"entity_id": "gene", "comparison": "contrast"}}
            build(rows)
            records, _ = read_table(path, p)
            self.assertEqual(records[0]["fields"]["entity_id"], "X")
            build(rows.replace('<is><t>X</t></is>', '<f>1+1</f><v>2</v>'))
            with self.assertRaises(ValueError):
                read_table(path, p)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "run"
        create_plan(ROOT / "examples/deg.csv", ROOT / "profiles/deg.example.yaml", self.out)

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_operator_jobs_and_no_simulated_completion(self):
        backend = TestBackend()
        result = run(self.out, backend=backend)
        self.assertEqual(result["counts"]["planned"], (3 + 2 + 1) * 8)
        self.assertEqual(backend.calls, 6)
        self.assertEqual(result["counts"]["coverage"], 1)
        self.assertIn("simulated_backend_not_scientific_coverage", result["errors"])
        self.assertNotEqual(json.loads((self.out / "manifest.json").read_text())["status"], "completed")

    def test_failure_resume_retries_only_failed(self):
        first = TestBackend(fail_at=3)
        result = run(self.out, backend=first)
        self.assertEqual(result["counts"]["failed"], 8)
        resumed = TestBackend()
        result = run(self.out, retry_failed=True, backend=resumed)
        self.assertEqual(resumed.calls, 1)
        self.assertEqual(result["counts"]["failed"], 0)

    def test_candidate_csv_preserves_evidence_and_marks_partial_run(self):
        result = run(self.out, backend=TestBackend(fail_at=3))
        self.assertEqual(result["candidate_csv"], str((self.out / "candidates.csv").resolve()))
        self.assertTrue((self.out / "candidates.csv").read_bytes().startswith(b"\xef\xbb\xbf"))
        with (self.out / "candidates.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        details = [json.loads(line) for line in (self.out / "candidates.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), result["candidates"])
        self.assertEqual(len(rows), len(details))
        self.assertGreater(len(rows), 0)
        self.assertLess(result["counts"]["coverage"], 1)
        for row, detail in zip(rows, details):
            self.assertEqual(row["id"], detail["id"])
            self.assertEqual(row["record_ids"].split(";"), detail["record_ids"])
            self.assertEqual(row["question"], detail["question"])
            self.assertEqual(row["falsification"], detail["falsification"])
            for field in ("scope", "observations", "limits", "required_checks"):
                self.assertEqual(json.loads(row[field]), detail[field])
            self.assertEqual(row["inspection_status"], "incomplete")
            self.assertEqual(row["verification_status"], "incomplete_or_invalid")
            self.assertEqual(float(row["inspection_coverage"]), result["counts"]["coverage"])

    def test_no_candidates_csv_has_header_without_inventing_rows(self):
        class BackgroundBackend(TestBackend):
            def evaluate(self, state, qs):
                receipt = super().evaluate(state, qs)
                for name, answer in receipt["payload"]["answers"].items():
                    if name.endswith("__discovery"):
                        answer["choice"] = "background"
                        answer["probabilities"] = {key: float(key == "background") for key in qs[name]["criteria"]}
                return receipt
        result = run(self.out, backend=BackgroundBackend())
        self.assertEqual(result["candidates"], 0)
        with (self.out / "candidates.csv").open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            self.assertIn("question", reader.fieldnames)
            self.assertIn("verification_status", reader.fieldnames)
            self.assertEqual(list(reader), [])

    def test_interrupt_preserves_successful_receipts(self):
        with self.assertRaises(KeyboardInterrupt):
            run(self.out, backend=TestBackend(interrupt_at=4))
        db = connect(self.out / "inspection.sqlite3")
        self.assertEqual(counts(db)["successful"], 24)
        db.close()
        resumed = TestBackend()
        run(self.out, backend=resumed)
        self.assertEqual(resumed.calls, 3)

    def test_cache_binding_and_full_reuse(self):
        run(self.out, backend=TestBackend())
        other = Path(self.tmp.name) / "second"
        create_plan(ROOT / "examples/deg.csv", ROOT / "profiles/deg.example.yaml", other)
        backend = TestBackend()
        result = run(other, backend=backend)
        self.assertEqual(backend.calls, 0)
        self.assertEqual(result["counts"]["cached"], 48)

    def test_deleted_job_detected(self):
        run(self.out, backend=TestBackend())
        db = connect(self.out / "inspection.sqlite3")
        db.execute("DELETE FROM jobs WHERE seq=1")
        db.commit()
        db.close()
        result = verify(self.out)
        self.assertIn("manifest_counts_mismatch", result["errors"])
        self.assertTrue(any(e.startswith("missing_or_modified_job") for e in result["errors"]))

    def test_receipt_tampering_detected(self):
        run(self.out, backend=TestBackend())
        db = connect(self.out / "inspection.sqlite3")
        db.execute("UPDATE jobs SET receipt='{}' WHERE seq=1")
        db.commit()
        db.close()
        self.assertTrue(any(e.startswith("invalid_receipt") for e in verify(self.out)["errors"]))

    def test_source_change_blocks_resume(self):
        (self.out / "input.csv").write_text("gene,comparison\nX,T_vs_C\n")
        backend = TestBackend()
        with self.assertRaises(ValueError):
            run(self.out, backend=backend)
        self.assertEqual(backend.calls, 0)

    def test_bad_model_probabilities_rejected(self):
        backend = TestBackend()
        q = questions("gap")
        receipt = backend.evaluate({}, q)
        receipt["payload"]["answers"]["discovery"]["probabilities"]["candidate"] = 0.2
        with self.assertRaises(ValueError):
            validate_response(receipt["payload"], q)


if __name__ == "__main__":
    unittest.main()
