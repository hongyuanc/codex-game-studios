from pathlib import Path
import unittest

from tools.codex_studio.validate import validate_skill


ROOT = Path(__file__).resolve().parents[2]
NAMES = set(
    """adopt architecture-decision architecture-review art-bible asset-audit asset-spec
balance-check brainstorm consistency-check content-audit create-architecture
create-control-manifest design-review design-system gate-check help map-systems
perf-profile project-stage-detect propagate-design-change prototype quick-design
review-all-gdds scope-check start tech-debt ux-design ux-review vertical-slice""".split()
)


class DesignSkillTests(unittest.TestCase):
    def test_exact_skill_set_exists(self):
        found = {path.parent.name for path in (ROOT / ".agents/skills").glob("*/SKILL.md")}
        self.assertTrue(NAMES <= found)

    def test_design_skills_are_native(self):
        issues = []
        for name in sorted(NAMES):
            issues.extend(validate_skill(ROOT / ".agents/skills" / name / "SKILL.md"))
        self.assertEqual([], issues)
