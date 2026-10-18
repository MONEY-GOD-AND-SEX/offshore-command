import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('build_pages', Path(__file__).resolve().parents[1] / 'scripts/build_pages.py')
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)


class PagesTests(unittest.TestCase):
    def test_export_preserves_engine_attendance_and_feasible_plan(self):
        with tempfile.TemporaryDirectory() as folder:
            pages.build(folder)
            result = json.loads((Path(folder) / 'snapshot.json').read_text())
            self.assertTrue(result['audit_valid'])
            self.assertTrue(result['plan']['feasible'])
            self.assertFalse(result['report']['ready'])
            self.assertEqual(len(result['report']['missing']), 4)
            self.assertEqual(len(result['plan']['fixed']), 2)
            self.assertEqual(len(result['plan']['assignments']), 6)
            self.assertEqual(result['audit'][-1]['kind'], 'drill.check_in')
            for person, station in result['plan']['fixed'].items():
                self.assertEqual(result['plan']['assignments'][person], station)
            for station in result['report']['stations']:
                assigned = list(result['plan']['assignments'].values()).count(station['station'])
                self.assertGreaterEqual(assigned, station['minimum'])
                self.assertLessEqual(assigned, station['capacity'])
            for asset in ('index.html', 'styles.css', 'app.js', '.nojekyll'):
                self.assertTrue((Path(folder) / asset).is_file())
