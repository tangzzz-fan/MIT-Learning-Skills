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

    def init_executable_session(self):
        self.run_cli(
            "init",
            "--output",
            str(self.session_dir),
            "--goal",
            "learn executable skills",
            "--budget",
            "48h",
            "--assessment-mode",
            "executable",
            "--workspace-root",
            str(REPO_ROOT),
            "--materials",
            str(self.material),
        )

    def advance_to_phase_2(self):
        self.init_session()
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
        self.run_cli(
            "reveal-phase",
            "--session",
            str(self.session_dir),
            "--phase",
            "1",
        )
        self.run_cli(
            "finish-phase",
            "--session",
            str(self.session_dir),
            "--phase",
            "1",
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
            "student/artifacts",
            "student/notes",
            "coach/phase-artifacts",
            "coach/feedback",
            "shared/questions",
            "shared/tasks",
            "shared/runtime-feedback",
            "state",
        ):
            self.assertTrue((self.session_dir / rel).is_dir(), rel)

        state = json.loads((self.session_dir / "state" / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(state["schema_version"], 4)
        self.assertEqual(state["materials"][0]["name"], "material.md")
        self.assertTrue(state["materials"][0]["sha256"])

    def test_init_stores_executable_mode_and_workspace_root(self):
        self.init_executable_session()
        state = session.load_state(self.session_dir)
        self.assertEqual(state["assessment_mode"], "executable")
        self.assertEqual(state["workspace_root"], str(REPO_ROOT))

        status = self.run_cli("status", "--session", str(self.session_dir))
        self.assertIn('"assessment_mode": "executable"', status.stdout)
        self.assertIn(f'"workspace_root": "{REPO_ROOT}"', status.stdout)

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
        self.assertTrue((self.session_dir / "state" / "locked" / "phase-artifacts" / "phase1.md").exists())
        self.assertTrue((self.session_dir / "coach" / "phase-artifacts" / "phase1.md").exists())

    def test_phase_two_cannot_start_before_phase_one_is_complete(self):
        self.init_session()
        result = self.run_cli(
            "start-question",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
            "--title",
            "Q1",
            "--text",
            "Question?",
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("current phase 2", result.stderr)

    def test_feedback_requires_submitted_answer(self):
        self.advance_to_phase_2()
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
            "结论：这是我的答案\n推理：这是我的推理",
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
        self.assertTrue((self.session_dir / "state" / "locked" / "feedback" / "q01" / "round1.md").exists())
        self.assertFalse((self.session_dir / "coach" / "feedback" / "q01" / "round1.md").exists())
        revealed = self.run_cli(
            "reveal-feedback",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
        )
        self.assertIn("feedback", revealed.stdout)
        self.assertTrue((self.session_dir / "coach" / "feedback" / "q01" / "round1.md").exists())

    def test_submit_requires_reasoning_structure(self):
        self.advance_to_phase_2()
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
        result = self.run_cli(
            "submit",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
            "--text",
            "just the answer",
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("two non-empty lines", result.stderr)

    def test_export_excludes_locked_coach_feedback(self):
        self.advance_to_phase_2()
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
            "结论：answer\n推理：because",
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

        export_dir = Path(self.tmp.name) / "export"
        self.run_cli(
            "export",
            "--session",
            str(self.session_dir),
            "--output",
            str(export_dir),
        )
        self.assertTrue((export_dir / "student" / "answers" / "q01.round1.md").exists())
        self.assertFalse((export_dir / "coach" / "feedback" / "q01" / "round1.md").exists())

    def test_export_excludes_saved_phase_artifact_until_revealed(self):
        self.init_session()
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

        export_dir = Path(self.tmp.name) / "phase-export"
        self.run_cli(
            "export",
            "--session",
            str(self.session_dir),
            "--output",
            str(export_dir),
        )
        self.assertFalse((export_dir / "coach" / "phase-artifacts" / "phase1.md").exists())

    def test_locked_phase_artifact_stays_out_of_coach_until_revealed(self):
        self.init_session()
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
        self.assertTrue((self.session_dir / "state" / "locked" / "phase-artifacts" / "phase1.md").exists())
        self.assertFalse((self.session_dir / "coach" / "phase-artifacts" / "phase1.md").exists())

    def test_check_rejects_reviewed_question_without_answer(self):
        self.advance_to_phase_2()
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
        question["rounds"] = []
        question["revealed"] = True
        session.save_state(self.session_dir, state)

        result = self.run_cli("check", "--session", str(self.session_dir), check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("reviewed without an answer", result.stderr)

    def test_check_rejects_untracked_coach_file_and_changed_material(self):
        self.init_session()
        self.material.write_text("# changed\n", encoding="utf-8")
        leaked = self.session_dir / "coach" / "feedback" / "q99" / "round1.md"
        leaked.parent.mkdir(parents=True, exist_ok=True)
        leaked.write_text("leak", encoding="utf-8")

        result = self.run_cli("check", "--session", str(self.session_dir), check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("material changed since init", result.stderr)
        self.assertIn("untracked coach feedback on disk", result.stderr)

    def test_check_rejects_untracked_locked_feedback_file(self):
        self.advance_to_phase_2()
        leaked = self.session_dir / "state" / "locked" / "feedback" / "q99" / "round1.md"
        leaked.parent.mkdir(parents=True, exist_ok=True)
        leaked.write_text("leak", encoding="utf-8")

        result = self.run_cli("check", "--session", str(self.session_dir), check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("untracked locked feedback on disk", result.stderr)

    def test_finish_phase_two_requires_ten_revealed_questions(self):
        self.advance_to_phase_2()
        for idx in range(1, 10):
            qid = f"q{idx:02d}"
            self.run_cli(
                "start-question",
                "--session",
                str(self.session_dir),
                "--id",
                qid,
                "--title",
                qid,
                "--text",
                f"Question {idx}?",
            )
            self.run_cli(
                "submit",
                "--session",
                str(self.session_dir),
                "--id",
                qid,
                "--text",
                f"结论：{qid}\n推理：because {qid}",
            )
            self.run_cli(
                "save-feedback",
                "--session",
                str(self.session_dir),
                "--id",
                qid,
                "--text",
                f"feedback {qid}",
            )
            self.run_cli(
                "reveal-feedback",
                "--session",
                str(self.session_dir),
                "--id",
                qid,
            )

        result = self.run_cli(
            "finish-phase",
            "--session",
            str(self.session_dir),
            "--phase",
            "2",
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("at least 10 questions", result.stderr)

    def test_next_surfaces_reveal_step_before_finish(self):
        self.init_session()
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

        result = self.run_cli("next", "--session", str(self.session_dir))
        self.assertIn("reveal-phase", result.stdout)

    def test_request_followup_opens_new_round(self):
        self.advance_to_phase_2()
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
            "结论：A1\n推理：R1",
        )
        self.run_cli(
            "save-feedback",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
            "--text",
            "追问：再想一层",
        )
        self.run_cli(
            "reveal-feedback",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
        )
        self.run_cli(
            "request-followup",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
        )

        state = session.load_state(self.session_dir)
        q01 = state["phases"]["2"]["questions"]["q01"]
        self.assertEqual(q01["status"], "open")
        self.assertEqual(q01["round"], 2)
        self.assertEqual(q01["completed_round"], 1)

    def test_followup_round_creates_round_specific_files(self):
        self.advance_to_phase_2()
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
            "结论：A1\n推理：R1",
        )
        self.run_cli("save-feedback", "--session", str(self.session_dir), "--id", "q01", "--text", "F1")
        self.run_cli("reveal-feedback", "--session", str(self.session_dir), "--id", "q01")
        self.run_cli("request-followup", "--session", str(self.session_dir), "--id", "q01")
        self.run_cli(
            "submit",
            "--session",
            str(self.session_dir),
            "--id",
            "q01",
            "--text",
            "结论：A2\n推理：R2",
        )
        self.run_cli("save-feedback", "--session", str(self.session_dir), "--id", "q01", "--text", "F2")
        self.run_cli("reveal-feedback", "--session", str(self.session_dir), "--id", "q01")

        self.assertTrue((self.session_dir / "student" / "answers" / "q01.round1.md").exists())
        self.assertTrue((self.session_dir / "student" / "answers" / "q01.round2.md").exists())
        self.assertTrue((self.session_dir / "coach" / "feedback" / "q01" / "round1.md").exists())
        self.assertTrue((self.session_dir / "coach" / "feedback" / "q01" / "round2.md").exists())

    def test_finish_phase_two_rejects_open_followup_round(self):
        self.advance_to_phase_2()
        for idx in range(1, 11):
            qid = f"q{idx:02d}"
            self.run_cli(
                "start-question",
                "--session",
                str(self.session_dir),
                "--id",
                qid,
                "--title",
                qid,
                "--text",
                f"Question {idx}?",
            )
            self.run_cli(
                "submit",
                "--session",
                str(self.session_dir),
                "--id",
                qid,
                "--text",
                f"结论：{qid}\n推理：because {qid}",
            )
            self.run_cli(
                "save-feedback",
                "--session",
                str(self.session_dir),
                "--id",
                qid,
                "--text",
                f"feedback {qid}",
            )
            self.run_cli(
                "reveal-feedback",
                "--session",
                str(self.session_dir),
                "--id",
                qid,
            )

        self.run_cli("request-followup", "--session", str(self.session_dir), "--id", "q01")
        result = self.run_cli(
            "finish-phase",
            "--session",
            str(self.session_dir),
            "--phase",
            "2",
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("open follow-up round", result.stderr)

    def test_next_suggests_followup_when_feedback_is_revealed(self):
        self.advance_to_phase_2()
        for idx in range(1, 11):
            qid = f"q{idx:02d}"
            self.run_cli(
                "start-question",
                "--session",
                str(self.session_dir),
                "--id",
                qid,
                "--title",
                qid,
                "--text",
                f"Question {idx}?",
            )
            self.run_cli(
                "submit",
                "--session",
                str(self.session_dir),
                "--id",
                qid,
                "--text",
                f"结论：{qid}\n推理：because {qid}",
            )
            self.run_cli(
                "save-feedback",
                "--session",
                str(self.session_dir),
                "--id",
                qid,
                "--text",
                f"feedback {qid}",
            )
            self.run_cli(
                "reveal-feedback",
                "--session",
                str(self.session_dir),
                "--id",
                qid,
            )

        result = self.run_cli("next", "--session", str(self.session_dir))
        self.assertIn("request-followup", result.stdout)

    def test_load_state_migrates_v1_schema(self):
        self.init_session()
        state = json.loads((self.session_dir / "state" / "session.json").read_text(encoding="utf-8"))
        state["schema_version"] = 1
        state["phases"]["1"]["barrier"]["unlocked"] = False
        state["phases"]["1"]["barrier"].pop("revealed", None)
        (self.session_dir / "state" / "session.json").write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        migrated = session.load_state(self.session_dir)
        self.assertEqual(migrated["schema_version"], 4)
        self.assertIn("revealed", migrated["phases"]["1"]["barrier"])
        self.assertIn("locked_file", migrated["phases"]["1"]["barrier"])
        self.assertEqual(migrated["assessment_mode"], "conceptual")


if __name__ == "__main__":
    unittest.main()
