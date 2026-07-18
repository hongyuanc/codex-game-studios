from pathlib import Path
import re
import unittest

from tools.codex_studio.validate import validate_skill


ROOT = Path(__file__).resolve().parents[2]
BUNDLED_SKILL = (
    ROOT
    / "plugins/codex-game-studios/assets/studio/.agents/skills/setup-engine/SKILL.md"
)
CANONICAL_SPEC = ROOT / "Codex Studio Testing Framework/skills/utility/setup-engine.md"
BUNDLED_SPEC = (
    ROOT
    / "plugins/codex-game-studios/assets/studio/Codex Studio Testing Framework/skills/utility/setup-engine.md"
)


def setup_engine_texts() -> tuple[str, str]:
    return (
        (ROOT / ".agents/skills/setup-engine/SKILL.md").read_text(encoding="utf-8"),
        BUNDLED_SKILL.read_text(encoding="utf-8"),
    )


def setup_engine_spec_texts() -> tuple[str, str]:
    return (
        CANONICAL_SPEC.read_text(encoding="utf-8"),
        BUNDLED_SPEC.read_text(encoding="utf-8"),
    )


def spec_case(text: str, case_number: int) -> str:
    start = text.index(f"### Case {case_number}:")
    end = text.find("\n### Case ", start + 1)
    return text[start:] if end == -1 else text[start:end]


class SetupEngineSkillTests(unittest.TestCase):
    def test_setup_engine_behavioral_spec_routes_files_to_real_active_profiles(self):
        # Arrange / Act
        texts = setup_engine_spec_texts()

        # Assert
        for text in texts:
            godot = spec_case(text, 1)
            self.assertIn("`godot-gdscript-specialist`", godot)
            self.assertIn("`.gd` → `godot-gdscript-specialist`", godot)
            self.assertNotIn("`gdscript-specialist`", godot)

            unity = spec_case(text, 2)
            self.assertIn("Specialist assignments reference `unity-specialist`", unity)
            self.assertIn("`.cs` → `unity-specialist`", unity)
            self.assertIn("`.asmdef` → `unity-specialist`", unity)
            self.assertIn("`.unity` → `unity-specialist`", unity)
            self.assertNotIn("csharp-specialist", unity)

            unreal = spec_case(text, 3)
            self.assertIn("`ue-blueprint-specialist`", unreal)
            self.assertIn("`.uasset` → `ue-blueprint-specialist`", unreal)
            self.assertNotIn("`blueprint-specialist`", unreal)

    def test_setup_engine_behavioral_spec_orders_version_and_language_choices(self):
        # Arrange / Act
        texts = setup_engine_spec_texts()

        # Assert
        for text in texts:
            godot = spec_case(text, 1)
            self.assertIn(
                "User decisions during workflow: exact version `Godot 4`; primary language `GDScript`.",
                godot,
            )
            self.assertIn(
                "Skill asks for the exact engine version; user selects Godot 4",
                godot,
            )
            self.assertIn(
                "Skill presents Godot language options; user selects GDScript",
                godot,
            )

            unreal = spec_case(text, 3)
            self.assertIn(
                "User decisions during workflow: exact version `Unreal Engine 5`; primary language `Blueprint (Visual Scripting)`.",
                unreal,
            )
            self.assertIn(
                "Skill asks for the exact engine version; user selects Unreal Engine 5",
                unreal,
            )
            self.assertIn(
                "Skill presents Unreal language options; user selects Blueprint (Visual Scripting)",
                unreal,
            )
            self.assertIn(
                "- [ ] Language field is Blueprint (Visual Scripting)",
                unreal,
            )

    def test_setup_engine_behavioral_spec_complete_fixture_matches_secure_runtime(self):
        # Arrange / Act
        cases = tuple(spec_case(text, 4) for text in setup_engine_spec_texts())

        # Assert
        for case in cases:
            self.assertIn("six-field studio authority is valid", case)
            self.assertIn("`.codex/active-engine.json` validates", case)
            self.assertIn("exactly five Godot profiles", case)
            self.assertIn("all technical-preference sections are populated", case)

    def test_setup_engine_behavioral_spec_uses_user_approved_performance_budget(self):
        # Arrange / Act
        texts = setup_engine_spec_texts()

        # Assert
        for text in texts:
            unreal = spec_case(text, 3)
            self.assertIn(
                "Skill asks for the performance budget; user accepts the offered frame/memory defaults or supplies a target",
                unreal,
            )
            self.assertNotIn("pre-set with Unreal defaults", unreal)
            self.assertNotIn("higher draw call budget", unreal)
            self.assertIn(
                "Performance budget values are user-approved",
                text,
            )

    def test_setup_engine_complete_config_offers_safe_section_specific_reconfiguration(self):
        # Arrange / Act
        texts = setup_engine_texts()

        # Assert
        for text in texts:
            self.assertIn("Engine already configured as", text)
            self.assertIn("Reconfigure all", text)
            self.assertIn("Reconfigure a specific section", text)
            self.assertIn("Performance Budgets only", text)
            self.assertIn("preserve every unselected field and path byte-for-byte", text)
            self.assertIn("Do not run pack activation", text)
            self.assertIn("one complete proposed changeset", text)
            self.assertIn("fresh explicit approval", text)
            self.assertIn(
                "full-configuration bullets do not apply to section-specific branches",
                text,
            )
            self.assertIn("apply only the approved selected-section diff", text)
            for section in (
                "Engine / Language",
                "Naming Conventions",
                "Specialists / File Routing",
                "Platform / Input",
                "Testing",
                "Performance Budgets",
            ):
                self.assertIn(section, text)

    def test_setup_engine_documents_engine_specific_naming_and_file_routes(self):
        # Arrange / Act
        texts = setup_engine_texts()

        # Assert
        expected = (
            "GDScript uses `snake_case`",
            "`.gd` → `godot-gdscript-specialist`",
            "`.gdshader` → `godot-shader-specialist`",
            "`.tscn` → `godot-specialist`",
            "C# classes use `PascalCase`",
            "fields use `camelCase`",
            "`.cs` → `unity-specialist`",
            "`.asmdef` → `unity-specialist`",
            "`.unity` → `unity-specialist`",
            "Blueprint (Visual Scripting)",
            "`.uasset` → `ue-blueprint-specialist`",
            "`.umap` → `unreal-specialist`",
            "exactly the five active profiles",
        )
        for text in texts:
            for token in expected:
                self.assertIn(token, text)

    def test_setup_engine_reports_complete_with_contextual_handoff_and_no_gate(self):
        # Arrange / Act
        texts = setup_engine_texts()

        # Assert
        for text in texts:
            self.assertIn("Verdict: COMPLETE", text)
            self.assertIn("Contextual next step", text)
            self.assertIn("`$brainstorm`", text)
            self.assertIn("`$map-systems`", text)
            self.assertIn("No director gates apply", text)
            self.assertIn("No director agents participate", text)
            self.assertIn("does not emit a gate ID", text)
            self.assertIn("gate-skip message", text)

    def test_setup_engine_supplied_engine_argument_skips_engine_selection(self):
        # Arrange / Act
        texts = setup_engine_texts()

        # Assert
        for text in texts:
            self.assertIn("Supplied engine argument", text)
            self.assertIn("skip the Engine selection step", text)
            self.assertIn("do not ask the user to select an engine again", text)

    def test_setup_engine_is_native_transactional_and_approval_gated(self):
        path = ROOT / ".agents/skills/setup-engine/SKILL.md"
        self.assertEqual([], validate_skill(path))
        text = path.read_text(encoding="utf-8")
        for required in (
            "--dry-run",
            "complete activation plan",
            "explicit approval",
            "--apply",
            "rollback evidence",
            "post-apply validation",
            "one decision per turn",
            "five active profiles",
            "--mode plugin-native",
        ):
            self.assertIn(required, text)
        self.assertNotIn("AskUserQuestion", text)  # enforcement-literal
        self.assertNotIn(".Codex/", text)  # enforcement-literal

    def test_setup_engine_uses_supported_engines_and_selected_pack_preferences(self):
        text = (ROOT / ".agents/skills/setup-engine/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Godot", text)
        self.assertIn("Unity", text)
        self.assertIn("Unreal", text)
        self.assertIn("request_user_input", text)
        preferences = (ROOT / ".codex/docs/technical-preferences.md").read_text(encoding="utf-8")
        self.assertIn("Active Engine Pack", preferences)
        self.assertIn("managed by `$setup-engine`", preferences)

    def test_setup_engine_decisions_are_strictly_sequential_and_not_combined(self):
        text = (ROOT / ".agents/skills/setup-engine/SKILL.md").read_text(encoding="utf-8")
        expected = [
            "Engine",
            "Exact engine version",
            "Primary language",
            "Target platform",
            "Primary input",
            "Testing framework",
            "Performance budget",
        ]
        decisions = re.findall(r"^\d+\. \*\*(.+?)\*\*", text, flags=re.MULTILINE)
        self.assertEqual(expected, decisions)
        self.assertIn("Ask exactly one unresolved decision, then stop and wait", text)

    def test_setup_engine_uses_same_exact_values_across_dry_run_approval_and_apply(self):
        text = (ROOT / ".agents/skills/setup-engine/SKILL.md").read_text(encoding="utf-8")
        commands = re.findall(r"python3 -B <resolved BUNDLE>/tools/codex_studio/engine_pack\.py[^\n]+", text)
        dry = next(command for command in commands if "--dry-run" in command)
        apply = next(command for command in commands if "--apply" in command)
        for token in ("<engine>", "<exact-version>", "<primary-language>"):
            self.assertIn(token, dry)
            self.assertIn(token, apply)
        self.assertIn("--source-root <resolved BUNDLE>", dry)
        self.assertNotIn("python3 -m tools.codex_studio.engine_pack", text)
        self.assertIn("physical installed SKILL.md path", text)
        self.assertIn("do not fall back to CWD", text)
        self.assertLess(text.index("complete activation plan"), text.index("explicit approval"))
        self.assertLess(text.index("explicit approval"), text.index("--apply"))
        self.assertIn("No project write is allowed before this approval", text)
        self.assertIn("Stop all remaining setup writes", text)
        self.assertIn("Never claim setup succeeded", text)
        self.assertIn("complete approved write scope", text)
