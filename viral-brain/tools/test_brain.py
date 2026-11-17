import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("brain", Path(__file__).parent / 'brain.py')
brain=importlib.util.module_from_spec(spec)
spec.loader.exec_module(brain)

class BrainTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old=(brain.VAULT, brain.CLIP_DIR,brain.REPORT_PATH,brain.EXPORT_PATH)
        brain.VAULT=Path(self.temp.name)
        brain.CLIP_DIR=brain.VAULT/'02 Clips'
        brain.REPORT_PATH=brain.VAULT/'09 Reports'/'Latest Report.md'
        brain.EXPORT_PATH=brain.VAULT/'exports'/'clipper_edit_rules.json'
    def tearDown(self):
        brain.VAULT,brain.CLIP_DIR,brain.REPORT_PATH,brain.EXPORT_PATH=self.old
        self.temp.cleanup()
    def test_url_dedup_ignores_tracking(self):
        a=brain.add_clip({'url':'https://www.tiktok.com/@foo/video/123?foo=bar'},quiet=True)
        b=brain.add_clip({'url':'https://www.tiktok.com/@foo/video/123'},quiet=True)
        self.assertTrue(a[1]);self.assertFalse(b[1]);self.assertEqual(a[0],b[0])
    def test_unknown_metrics_not_zero(self):
        brain.add_clip({'url':'https://www.tiktok.com/@foo/video/124'},quiet=True)
        p,d=brain.all_clips()[0]
        self.assertIsNone(d['views']);self.assertIsNone(brain.engagement(d))
    def test_engagement(self):
        self.assertAlmostEqual(brain.engagement({'views':1000,'likes':100,'comments':20,'shares':30}),15)
    def test_invalid_host(self):
        with self.assertRaises(ValueError): brain.add_clip({'url':'https://fake-tiktok.com/@foo/video/123'},quiet=True)
    def test_report_and_rules(self):
        brain.add_clip({'url':'https://www.tiktok.com/@foo/video/123','views':1000,'likes':100,'comments':10,'shares':20,'category':'gta6','style':'beat-sync','reviewed':'true'},quiet=True)
        brain.report();brain.rules()
        self.assertIn('1**',brain.REPORT_PATH.read_text())
        self.assertEqual(json.loads(brain.EXPORT_PATH.read_text())['candidate_edit_styles'],[])
    def test_date_rejects_invalid(self):
        with self.assertRaises(ValueError):brain.add_clip({'url':'https://www.tiktok.com/@foo/video/123','observed_at':'yesterday'},quiet=True)

if __name__=='__main__':unittest.main()
