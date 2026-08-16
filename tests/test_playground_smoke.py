import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE = REPO_ROOT / "scripts" / "run-playground-smoke.py"


class PlaygroundSmokeTest(unittest.TestCase):
    def test_playground_smoke_script_passes(self):
        result = subprocess.run(
            [sys.executable, str(SMOKE)],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            self.fail(
                "playground smoke failed\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        self.assertIn("playground smoke passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
