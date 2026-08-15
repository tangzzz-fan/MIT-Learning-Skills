import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "rapid-domain-mastery"


class SkillStructureTest(unittest.TestCase):
    def test_required_files_exist(self):
        for rel in (
            "SKILL.md",
            "agents/openai.yaml",
            "scripts/session.py",
            "references/separation-protocol.md",
            "references/phase-prompts.md",
            "references/executable-mode.md",
        ):
            self.assertTrue((SKILL_DIR / rel).is_file(), rel)

    def test_frontmatter_has_name_and_description(self):
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        self.assertIsNotNone(match, "missing YAML frontmatter")
        frontmatter = match.group(1)
        self.assertIn("name: rapid-domain-mastery", frontmatter)
        self.assertIn("description:", frontmatter)
        self.assertNotIn("[TODO", frontmatter)

    def test_description_contains_triggers(self):
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        for phrase in ("快速学习", "速通", "考试", "项目", "MIT"):
            self.assertIn(phrase, text)

    def test_no_extraneous_docs_inside_skill(self):
        forbidden = {
            "README.md",
            "INSTALLATION_GUIDE.md",
            "QUICK_REFERENCE.md",
            "CHANGELOG.md",
        }
        for name in forbidden:
            self.assertFalse((SKILL_DIR / name).exists(), name)

    def test_separation_rules_are_documented(self):
        protocol = (SKILL_DIR / "references" / "separation-protocol.md").read_text(encoding="utf-8")
        self.assertIn("先学生、后教练", protocol)
        self.assertIn("不直接读取 `coach/`", protocol)
        self.assertIn("reveal-phase", protocol)
        self.assertIn("reveal-feedback", protocol)

    def test_persona_support_is_documented(self):
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        prompts = (SKILL_DIR / "references" / "phase-prompts.md").read_text(encoding="utf-8")
        self.assertIn("--student-persona", skill)
        self.assertIn("--coach-persona", skill)
        self.assertIn("{coach_persona}", prompts)

    def test_executable_mode_is_documented(self):
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        executable = (SKILL_DIR / "references" / "executable-mode.md").read_text(encoding="utf-8")
        self.assertIn("--assessment-mode", skill)
        self.assertIn("assessment_mode=executable", skill)
        self.assertIn("可运行反馈", executable)


if __name__ == "__main__":
    unittest.main()
