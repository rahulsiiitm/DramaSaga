import os
import subprocess
import sys
import tempfile
import unittest

class CleanCheckoutTest(unittest.TestCase):
    def test_run_py_dry_run(self):
        workdir = tempfile.mkdtemp()
        env = dict(os.environ, MAGICDRAMA_WORKDIR=workdir)
        r = subprocess.run([sys.executable, "run.py"], capture_output=True, text=True, env=env, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertIn("dry run complete", r.stdout)
        self.assertIn('"paid_requests": 0', r.stdout)

if __name__ == "__main__":
    unittest.main()

