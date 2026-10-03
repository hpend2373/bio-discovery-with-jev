import csv
import json
import tempfile
import unittest
from pathlib import Path

from bio_topics.ingest import read_profile
from bio_topics.ranking import evidence_counts, ranking_policy, score_candidate
from bio_topics.runtime import create_plan, run
from test_engine import ROOT, TestBackend


def record(i, study=None, paper=None, cohorts=(), **fields):
    return {"id": str(i), "fields": {"study_id": study, "publication_id": paper,
                                    "cohort_ids": list(cohorts), **fields}}


class RankingTests(unittest.TestCase):
    def test_more_papers_raise_score_and_can_overcome_small_probability_difference(self):
        policy = ranking_policy({})
        small = evidence_counts([record(1, "S1", "P1")])
        large = evidence_counts([record(i, f"S{i}", f"P{i}") for i in range(4)])
        self.assertGreater(score_candidate(0.7, large, "meta", policy)["ranking_score"],
                           score_candidate(0.9, small, "meta", policy)["ranking_score"])

    def test_duplicate_rows_and_shared_cohorts_do_not_inflate_incentive(self):
        base = [record(1, "S1", "P1", ["C1"]), record(2, "S2", "P2", ["C2"])]
        duplicated = base + [record(3, "S1", "P1", ["C1"])]
        self.assertEqual(evidence_counts(base), evidence_counts(duplicated))
        overlap = duplicated + [record(4, "S3", "P3", ["C1"])]
        self.assertEqual(evidence_counts(overlap)["paper_count"], 3)
        self.assertEqual(evidence_counts(overlap)["incentive_evidence_count"], 2)

    def test_multiple_studies_in_one_paper_and_multiple_papers_in_one_study(self):
        sources = [record(1, "S1", "P1"), record(2, "S2", "P1"), record(3, "S2", "P2")]
        counts = evidence_counts(sources)
        self.assertEqual(counts["paper_count"], 2)
        self.assertEqual(counts["unique_study_count"], 2)
        self.assertEqual(counts["incentive_evidence_count"], 1)

    def test_unknown_blocked_and_held_evidence_receive_no_extra_bonus(self):
        sources = [record(1, "S1", "P1"), record(2, "unknown", "NA"),
                   record(3, "S3", "P3", source_blocked=True), record(4, "S4", "P4", hold_reason="conflict")]
        counts = evidence_counts(sources)
        self.assertEqual(counts["paper_count"], 3)
        self.assertEqual(counts["missing_paper_identity_rows"], 1)
        self.assertEqual(counts["incentive_evidence_count"], 1)

    def test_partial_paper_identity_does_not_count_same_study_twice(self):
        counts = evidence_counts([record(1, "S1", "P1"), record(2, "S1"), record(3, "S2")])
        self.assertEqual(counts["paper_count"], 2)
        self.assertEqual(counts["paper_count_basis"], "publication_id_or_study_id_proxy")

    def test_weight_zero_disables_bonus_and_deg_receives_no_bonus(self):
        counts = evidence_counts([record(1, "S1", "P1")])
        for domain, profile in [("meta", {"ranking": {"paper_count_weight": 0}}), ("deg", {})]:
            scored = score_candidate(0.6, counts, domain, ranking_policy(profile))
            self.assertEqual(scored["ranking_score"], 0.6)
            self.assertEqual(scored["paper_count_bonus"], 0)

    def test_invalid_weight_rejected_during_profile_read(self):
        profile = read_profile(ROOT / "profiles/meta.example.yaml")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "profile.json"
            for settings in [None, {"paper_count_weight": -1}, {"paper_count_weight": 2},
                             {"paper_count_weight": True}, {"paper_count_weight": "0.25"},
                             {"paper_count_weight": float("nan")}, {"paper_count_weigth": 0.25}]:
                profile["ranking"] = settings
                path.write_text(json.dumps(profile))
                with self.subTest(settings=settings), self.assertRaises(ValueError):
                    read_profile(path)

    def test_csv_scores_and_diversity_order_after_exhaustive_inspection(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "run"
            create_plan(ROOT / "examples/meta.csv", ROOT / "profiles/meta.example.yaml", out)
            result = run(out, backend=TestBackend())
            self.assertEqual(result["counts"]["coverage"], 1)
            with (out / "candidates.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), result["counts"]["successful"])
            scores_by_bucket = {}
            for row in rows:
                scores_by_bucket.setdefault((row["route"], row["operator"]), []).append(float(row["ranking_score"]))
                self.assertEqual(float(row["ranking_score"]), float(row["model_selection_probability"]) + float(row["paper_count_bonus"]))
            for scores in scores_by_bucket.values():
                self.assertEqual(scores, sorted(scores, reverse=True))
            self.assertGreater(max(float(row["paper_count_bonus"]) for row in rows), 0.25)
            summary = json.loads((out / "candidate-summary.json").read_text())
            self.assertTrue(summary["paper_count_incentive_applied"])
            self.assertEqual(summary["ranking_policy"]["paper_count_weight"], 0.25)


if __name__ == "__main__":
    unittest.main()
