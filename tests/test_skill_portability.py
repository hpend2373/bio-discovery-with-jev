import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SkillPortabilityTests(unittest.TestCase):
    def test_skill_plans_from_relocated_clone_outside_working_directory(self):
        with tempfile.TemporaryDirectory() as td:
            clone = Path(td) / 'relocated clone'
            clone.mkdir()
            shutil.copytree(ROOT / 'bio_topics', clone / 'bio_topics', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(ROOT / 'skills', clone / 'skills')
            out = Path(td) / 'new run'
            result = subprocess.run([sys.executable, str(clone / 'skills/bio-topic-discovery/scripts/run.py'),
                                     'plan', '--legacy-deg', '--input', str(ROOT / 'examples/deg.csv'),
                                     '--profile', str(ROOT / 'profiles/deg.example.yaml'), '--out', str(out)],
                                    cwd=td, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            contract = json.loads((out / 'manifest.json').read_text())['contract']
            self.assertEqual(contract['units_by_kind'], {'row': 3, 'cell': 2, 'pair': 1})
            self.assertEqual(contract['job_count'], 48)

    def test_new_deg_plan_requires_explicit_historical_contract(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'must not be created'
            result = subprocess.run([sys.executable, '-m', 'bio_topics', 'plan',
                                     '--input', str(ROOT / 'examples/deg.csv'),
                                     '--profile', str(ROOT / 'profiles/deg.example.yaml'),
                                     '--out', str(out)], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('--legacy-deg', result.stderr)
            self.assertFalse(out.exists())
            self.assertFalse(out.with_name(out.name + '.planning').exists())

    def test_meta_plan_keeps_existing_contract(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'meta'
            result = subprocess.run([sys.executable, '-m', 'bio_topics', 'plan',
                                     '--input', str(ROOT / 'examples/meta.csv'),
                                     '--profile', str(ROOT / 'profiles/meta.example.yaml'),
                                     '--out', str(out)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((out / 'manifest.json').read_text())['status'], 'planned')


if __name__ == '__main__':
    unittest.main()
