from pathlib import Path
import os
import re
import shutil
import tempfile
import unittest

from tools.codex_studio.validate import validate_plugin_skill_catalog, validate_skill


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"
EXPECTED_DEPENDENCIES = {
    "bug-report": ("hotfix",),
    "bug-triage": ("team-qa",),
    "dev-story": ("team-qa",),
    "help": ("[command]",),
    "skill-improve": ("skill-test",),
    "skill-test": ("[name]",),
    "smoke-check": ("setup-engine",),
    "sprint-plan": ("team-qa",),
    "story-done": ("team-qa",),
    "test-evidence-review": ("team-qa",),
    "test-helpers": ("setup-engine", "skill-test"),
    "test-setup": ("setup-engine",),
}


def _copy_catalog_fixture(directory: str) -> tuple[Path, Path]:
    root = Path(directory) / "repository"
    plugin = root / "plugins/codex-game-studios"
    shutil.copytree(ROOT / ".agents", root / ".agents")
    shutil.copytree(PLUGIN / "assets/studio", plugin / "assets/studio")
    return root, plugin


def _write_fixture_skill(root: Path, plugin: Path, name: str, text: str) -> None:
    (root / ".agents/skills" / name / "SKILL.md").write_text(text, encoding="utf-8")
    (plugin / "assets/studio/.agents/skills" / name / "SKILL.md").write_text(
        text, encoding="utf-8"
    )


class PluginSkillCatalogTests(unittest.TestCase):
    def test_catalog_has_source_parity_and_valid_skills(self):
        source = ROOT / ".agents/skills"
        bundled = PLUGIN / "assets/studio/.agents/skills"
        names = {path.parent.name for path in source.glob("*/SKILL.md")}
        self.assertEqual(73, len(names))
        for name in sorted(names):
            self.assertEqual(
                (source / name / "SKILL.md").read_bytes(),
                (bundled / name / "SKILL.md").read_bytes(),
            )
            self.assertEqual([], validate_skill(bundled / name / "SKILL.md"))

    def test_skills_do_not_probe_repo_local_skill_installation(self):
        pattern = re.compile(r"\.agents/skills/[a-z0-9-]+/SKILL\.md")
        for path in sorted((ROOT / ".agents/skills").glob("*/SKILL.md")):
            self.assertIsNone(pattern.search(path.read_text()), path)

    def test_skills_resolve_static_resources_from_the_plugin_bundle(self):
        resource = re.compile(
            r"(?P<prefix>(?:\.\./)*)"
            r"(?P<path>\.codex/docs/[A-Za-z0-9_./-]+|"
            r"docs/engine-reference/[A-Za-z0-9_./\[\]-]+|"
            r"Codex Studio Testing Framework/[A-Za-z0-9_./*\[\]-]+)"
        )
        for skill in sorted((ROOT / ".agents/skills").glob("*/SKILL.md")):
            for match in resource.finditer(skill.read_text(encoding="utf-8")):
                if match.group("path") == ".codex/docs/technical-preferences.md":
                    expected = ""
                else:
                    expected = "../../../"
                self.assertEqual(expected, match.group("prefix"), (skill, match.group()))

    def test_dependency_contracts_are_complete_for_all_named_skills(self):
        # Arrange / Act / Assert
        self.assertEqual(12, len(EXPECTED_DEPENDENCIES))
        for skill, dependencies in EXPECTED_DEPENDENCIES.items():
            text = (ROOT / ".agents/skills" / skill / "SKILL.md").read_text(
                encoding="utf-8"
            )
            for dependency in dependencies:
                with self.subTest(skill=skill, dependency=dependency):
                    self.assertIn(
                        f"`{dependency}` is present in the current task's available skill catalog",
                        text,
                    )
                    self.assertIn(
                        f"Staged dependency: ${dependency} is not available", text
                    )
                    self.assertRegex(text, rf"(?s)\${re.escape(dependency)}.*?defer")
                    self.assertIn(f"do not invoke `${dependency}`", text)
                    self.assertIn(
                        "do not search for or copy a repository-local skill file", text
                    )

    def test_catalog_validator_rejects_every_incomplete_dependency_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            # Arrange
            root, plugin = _copy_catalog_fixture(directory)
            for skill, dependencies in EXPECTED_DEPENDENCIES.items():
                source_path = root / ".agents/skills" / skill / "SKILL.md"
                original = source_path.read_text(encoding="utf-8")
                for dependency in dependencies:
                    with self.subTest(skill=skill, dependency=dependency):
                        required = f"Staged dependency: ${dependency} is not available"
                        tampered = original.replace(required, "Staged dependency: $wrong is not available", 1)
                        self.assertNotEqual(original, tampered)
                        _write_fixture_skill(root, plugin, skill, tampered)

                        # Act
                        issues = validate_plugin_skill_catalog(root, plugin)

                        # Assert
                        self.assertTrue(
                            any(
                                "dependency contract is incomplete" in issue.message
                                and dependency in issue.message
                                for issue in issues
                            ),
                            (skill, dependency, issues),
                        )
                        _write_fixture_skill(root, plugin, skill, original)

    def test_skill_test_resolves_all_resources_without_project_local_copies(self):
        # Arrange
        skill = PLUGIN / "assets/studio/.agents/skills/skill-test/SKILL.md"
        text = skill.read_text(encoding="utf-8")
        studio = (skill.parent / "../../..").resolve()
        catalog = studio / "Codex Studio Testing Framework/catalog.yaml"
        spec = re.search(r"^\s+spec:\s+(.+)$", catalog.read_text(encoding="utf-8"), re.MULTILINE)
        self.assertIsNotNone(spec)

        # Act
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            project_validator = project / "tools/codex_studio/validate.py"
            project_skills = project / ".agents/skills"
            project_framework = project / "Codex Studio Testing Framework"
            bundled_validator = (skill.parent / "../../../tools/codex_studio/validate.py").resolve()
            bundled_spec = studio / spec.group(1)

            # Assert
            self.assertFalse(project_validator.exists())
            self.assertFalse(project_skills.exists())
            self.assertFalse(project_framework.exists())
            self.assertTrue(bundled_validator.is_file())
            self.assertTrue(bundled_spec.is_file())
            self.assertIn("`../../../tools/codex_studio/validate.py`", text)
            self.assertIn("resolve every `spec:` value against the bundled studio root", text)

    def test_plugin_static_resources_are_read_only_and_outputs_are_project_owned(self):
        # Arrange
        skill_test = (ROOT / ".agents/skills/skill-test/SKILL.md").read_text(encoding="utf-8")
        skill_improve = (ROOT / ".agents/skills/skill-improve/SKILL.md").read_text(encoding="utf-8")
        setup_engine = (ROOT / ".agents/skills/setup-engine/SKILL.md").read_text(encoding="utf-8")

        # Act / Assert
        self.assertIn("production/qa/skill-tests/", skill_test)
        self.assertIn("bundled testing catalog is read-only", skill_test)
        self.assertNotIn("Write results file to `../../../Codex Studio Testing Framework", skill_test)
        self.assertNotIn("Update `../../../Codex Studio Testing Framework/catalog.yaml`", skill_test)
        self.assertIn("explicit canonical source-repository workflow", skill_improve)
        self.assertIn("installed plugin skill resource is read-only", skill_improve)
        self.assertNotIn("catalog-resolved skill resource as\nthe only target", skill_improve)
        self.assertIn("bundled engine references are read-only", setup_engine)
        self.assertNotIn("Create or refresh `../../../docs/engine-reference", setup_engine)

    def test_generated_project_artifacts_use_stable_resource_provenance(self):
        # Arrange
        architecture = (ROOT / ".agents/skills/architecture-decision/SKILL.md").read_text(
            encoding="utf-8"
        )
        manifest = (ROOT / ".agents/skills/create-control-manifest/SKILL.md").read_text(
            encoding="utf-8"
        )

        # Act
        adr_template = architecture.split("Following this format:", 1)[1]
        adr_example = adr_template.split("## Engine Compatibility", 1)[1].split(
            "## ADR Dependencies", 1
        )[0]
        source_example = manifest.split("### Forbidden APIs", 1)[1].split(
            "### Cross-Cutting Constraints", 1
        )[0]

        # Assert
        self.assertNotIn("../../../", adr_example)
        self.assertIn("Codex Game Studios bundled engine reference:", adr_example)
        self.assertNotIn("../../../", source_example)
        self.assertIn("Codex Game Studios bundled engine reference:", source_example)

    def test_resource_validator_rejects_malformed_and_missing_static_targets(self):
        cases = (
            "../../../.codex/Docs/director-gates.md",
            "nested/.codex/docs/technical-preferences.md",
            "../../../.codex/docs/templates/bad name.md",
            "../../../../.codex/docs/director-gates.md",
            "../../../Codex studio Testing Framework/catalog.yaml",
            "../../../.codex/docs/templates/does-not-exist.md",
        )
        for reference in cases:
            with self.subTest(reference=reference), tempfile.TemporaryDirectory() as directory:
                # Arrange
                root, plugin = _copy_catalog_fixture(directory)
                path = root / ".agents/skills/bug-report/SKILL.md"
                text = path.read_text(encoding="utf-8") + f"\nMalformed: `{reference}`\n"
                _write_fixture_skill(root, plugin, "bug-report", text)

                # Act
                issues = validate_plugin_skill_catalog(root, plugin)

                # Assert
                self.assertTrue(
                    any(
                        "invalid plugin skill resource" in issue.message
                        or "plugin skill resource target" in issue.message
                        for issue in issues
                    ),
                    (reference, issues),
                )

    def test_resource_validator_rejects_symlinked_skill_directory(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks unavailable")
        with tempfile.TemporaryDirectory() as directory:
            # Arrange
            root, plugin = _copy_catalog_fixture(directory)
            skill = plugin / "assets/studio/.agents/skills/bug-report"
            target = plugin / "assets/studio/.agents/skills/bug-triage"
            shutil.rmtree(skill)
            skill.symlink_to(target, target_is_directory=True)

            # Act
            issues = validate_plugin_skill_catalog(root, plugin)

            # Assert
            self.assertTrue(
                any("skill directory must not be a symlink" in issue.message for issue in issues),
                issues,
            )


if __name__ == "__main__":
    unittest.main()
