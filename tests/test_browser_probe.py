import unittest
from pathlib import Path

class BrowserProbePortabilityTests(unittest.TestCase):
    def test_probe_has_explicit_runtime_paths_not_private_machine_locations(self):
        code=(Path(__file__).resolve().parents[1]/'tools/check_dashboard_browser.py').read_text()
        self.assertNotIn('/home/ider/',code)
        self.assertIn('--evidence-dir',code)
        self.assertIn('--browser',code)

if __name__=='__main__':unittest.main()
