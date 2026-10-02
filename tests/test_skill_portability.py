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
                                     'plan', '--input', str(ROOT / 'examples/deg.csv'),
                                     '--profile', str(ROOT / 'profiles/deg.example.yaml'), '--out', str(out)],
                                    cwd=td, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            contract = json.loads((out / 'manifest.json').read_text())['contract']
            self.assertEqual(contract['units_by_kind'], {'row': 3, 'cell': 2, 'pair': 1})
            self.assertEqual(contract['job_count'], 48)


if __name__ == '__main__':
    unittest.main()
