import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "rapid-domain-mastery"
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import session  # noqa: E402


class SessionCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.session_dir = Path(self.tmp.name) / "rdm"
        self.material = Path(self.tmp.name) / "material.md"
        self.material.write_text("# material\n", encoding="utf-8")

    def run_cli(self, *args, check=True):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "session.py"), *args],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
        )
        if check and result.returncode != 0:
            self.fail(
                "command failed: "
                + " ".join(args)
                + "\nstdout: "
                + result.stdout
                + "\nstderr: "
                + result.stderr
            )
        return result

    def init_session(self):
        self.run_cli(
            "init",
            "--output",
            str(self.session_dir),
            "--goal",
            "learn a domain",
            "--budget",
            "48h",
            "--materials",
            str(self.material),
        )

    def test_init_personas_default_to_empty_and_are_reported(self):
        self.init_session()
        state = session.load_state(self.session_dir)
        self.assertEqual(state["student_persona"], "")
        self.assertEqual(state["coach_persona"], "")

        status = self.run_cli("status", "--session", str(self.session_dir))
        self.assertIn('"student_persona": ""', status.stdout)
        self.assertIn('"coach_persona": ""', status.stdout)

    def test_init_stores_student_and_coach_personas(self):
        self.run_cli(
            "init",
            "--output",
            str(self.session_dir),
            "--goal",
            "learn a domain",
            "--budget",
            "48h",
            "--student-persona",
            "非技术背景的产品新人",
            "--coach-persona",
            "麦肯锡资深分析家",
            "--materials",
            str(self.material),
        )

        state = session.load_state(self.session_dir)
        self.assertEqual(state["student_persona"], "非技术背景的产品新人")
        self.assertEqual(state["coach_persona"], "麦肯锡资深分析家")

    def test_load_state_normalizes_missing_persona_fields(self):
        self.init_session()
        state = session.load_state(self.session_dir)
        state.pop("student_persona")
        state.pop("coach_persona")
        session.save_state(self.session_dir, state)

        normalized = session.load_state(self.session_dir)
        self.assertEqual(normalized["student_persona"], "")
        self.assertEqual(normalized["coach_persona"], "")

    def test_init_creates_separated_directories(self):
        self.init_session()
        for rel in (
            "student/attempts",
            "student/answers",
            "student/notes",
            "coach/phase-artifacts",
            "coach/feedback",
            "shared/questions",
            "state",
        ):
            self.assertTrue((self.session_dir / rel).is_dir(), rel)

        state = json.loads((self.session_dir / "state" / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(state["schema_version"], 1)
        self.assertEqual(state["materials"][0]["name"], "material.md")
        self.assertTrue(state["materials"][0]["sha256"])

    def test_phase_artifact_requires_student_attempt(self):
        self.init_session()
        denied = self.run_cli(
            "save-phase-artifact",
            "--session",
            str(self.session_dir),
            "--phase",
            "1",
            "--text",
            "coach-only",
            check=False,
        )
        self.assertEqual(denied.returncode, 1)
        self.assertIn("no student attempt", denied.stderr)

        self.run_cli(
            "record-attempt",
            "--session",
            str(self.session_dir),
            "--phase",
            "1",
            "--text",
            "my framework",
        )
        self.run_cli(
            "save-phase-artifact",
            "--session",
            str(self.session_dir),
            "--phase",
            "1",
            "--text",
            "coach skeleton",
        )
        revealed = self.run_cli(
            "reveal-phase",
            "--session",
            str(self.session_dir),
            "--phase",
            "1",
        )
        self.assertIn("coach skeleton", revealed.stdout)

    def test_feedback_requires_submitted_answer(self):
        self.init_session()
        self.run_cli(
            "start-question",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
            "--title",
            "Q1",
            "--text",
            "What is the central tradeoff?",
        )

        denied_feedback = self.run_cli(
            "save-feedback",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
            "--text",
            "feedback",
            check=False,
        )
        self.assertEqual(denied_feedback.returncode, 1)
        self.assertIn("submit an answer", denied_feedback.stderr)

        denied_reveal = self.run_cli(
            "reveal-feedback",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
            check=False,
        )
        self.assertEqual(denied_reveal.returncode, 1)

        self.run_cli(
            "submit",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
            "--text",
            "my answer with reasoning",
        )
        self.run_cli(
            "save-feedback",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
            "--text",
            "feedback",
        )
        revealed = self.run_cli(
            "reveal-feedback",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
        )
        self.assertIn("feedback", revealed.stdout)

    def test_export_excludes_locked_coach_feedback(self):
        self.init_session()
        self.run_cli(
            "start-question",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
            "--title",
            "Q1",
            "--text",
            "Question?",
        )
        self.run_cli(
            "submit",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
            "--text",
            "answer",
        )

        export_dir = Path(self.tmp.name) / "export"
        self.run_cli(
            "export",
            "--session",
            str(self.session_dir),
            "--output",
            str(export_dir),
        )
        self.assertTrue((export_dir / "student" / "answers" / "q01.md").exists())
        self.assertFalse((export_dir / "coach" / "feedback" / "q01.md").exists())

    def test_check_rejects_reviewed_question_without_answer(self):
        self.init_session()
        self.run_cli(
            "start-question",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
            "--title",
            "Q1",
            "--text",
            "Question?",
        )

        state = session.load_state(self.session_dir)
        question = state["phases"]["2"]["questions"]["q01"]
        question["status"] = "reviewed"
        session.save_state(self.session_dir, state)

        result = self.run_cli("check", "--session", str(self.session_dir), check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("reviewed without an answer", result.stderr)


if __name__ == "__main__":
    unittest.main()
