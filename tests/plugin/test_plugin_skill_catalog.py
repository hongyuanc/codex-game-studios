from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.codex_studio.validate import (
    EXPECTED_SKILL_NAMES,
    validate_plugin_skill_catalog,
    validate_skill,
)


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"
sys.path.insert(0, str(PLUGIN / "scripts"))
import payload  # noqa: E402

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
DELEGATION_MARKER = "<!-- codex-studio-delegation: governed -->"
DELEGATION_PREFLIGHT = (
    "Resolve every role through `../../../.codex/docs/plugin-agent-delegation.md`;\n"
    "do not require a repository-local `.codex/agents/` or `.codex/agent-packs/` tree."
)
DELEGATION_RESOLVER = (
    "Before default delegation, run `python3 "
    "../../../tools/codex_studio/agent_delegation.py resolve --project-root "
    "<project-root> --role <role>` and use only its returned role contract."
)
EXPECTED_DELEGATING_SKILLS = set(
    """architecture-decision architecture-review art-bible asset-spec brainstorm
bug-report bug-triage changelog code-review create-architecture
create-control-manifest create-epics create-stories day-one-patch design-review
design-system dev-story estimate gate-check hotfix launch-checklist localize
map-systems milestone-review onboard patch-notes playtest-report
propagate-design-change prototype qa-plan regression-suite release-checklist
retrospective reverse-document review-all-gdds security-audit skill-improve
skill-test smoke-check soak-test sprint-plan sprint-status story-done
story-readiness team-audio team-combat team-level team-live-ops team-narrative
team-polish team-qa team-release team-ui test-evidence-review test-flakiness
test-helpers test-setup ux-design vertical-slice""".split()
)


def _dependency_gate(dependency: str) -> str:
    return (
        f"### Native readiness gate for `${dependency}`\n\n"
        f"Before invoking or routing to `${dependency}`, confirm that `{dependency}` is "
        "present in the current task's available skill catalog. If unavailable, report\n"
        f"`Staged dependency: ${dependency} is not available`, defer the handoff, do not "
        f"invoke `${dependency}`, do not route to `${dependency}`, and do not search for "
        "or copy a repository-local skill file."
    )


def _namespace_api(testcase: unittest.TestCase):
    transform = getattr(payload, "namespace_skill_invocations", None)
    catalog = getattr(payload, "approved_skill_names", None)
    testcase.assertTrue(callable(transform), "payload namespace transform is missing")
    testcase.assertTrue(callable(catalog), "approved skill-name derivation is missing")
    return transform, catalog


def _plain_catalog_invocations(text: str, names: tuple[str, ...]) -> set[str]:
    pattern = re.compile(
        r"(?<![A-Za-z0-9_$])\$(?P<name>"
        + "|".join(sorted(map(re.escape, names), key=len, reverse=True))
        + r")(?![A-Za-z0-9_-])"
    )
    return {match.group("name") for match in pattern.finditer(text)}


def _copy_catalog_fixture(directory: str) -> tuple[Path, Path]:
    root = Path(directory) / "repository"
    plugin = root / "plugins/codex-game-studios"
    shutil.copytree(ROOT / ".agents", root / ".agents")
    shutil.copytree(PLUGIN / "assets/studio", plugin / "assets/studio")
    return root, plugin


def _write_fixture_skill(root: Path, plugin: Path, name: str, text: str) -> None:
    source_bytes = text.encode("utf-8")
    (root / ".agents/skills" / name / "SKILL.md").write_bytes(source_bytes)
    (plugin / "assets/studio/.agents/skills" / name / "SKILL.md").write_bytes(
        payload.namespace_skill_invocations(
            source_bytes, tuple(sorted(EXPECTED_SKILL_NAMES))
        )
    )


class PluginSkillCatalogTests(unittest.TestCase):
    def test_plugin_bundles_shared_agent_delegation_protocol(self):
        # Arrange
        source = ROOT / ".codex/docs/plugin-agent-delegation.md"
        bundled = PLUGIN / "assets/studio/.codex/docs/plugin-agent-delegation.md"

        # Act / Assert
        self.assertEqual(source.read_bytes(), bundled.read_bytes())

    def test_bundled_delegating_skills_use_shared_agent_preflight(self):
        # Arrange
        source = ROOT / ".agents/skills"
        bundled = PLUGIN / "assets/studio/.agents/skills"

        # Act
        paths = tuple(
            path
            for path in sorted(source.glob("*/SKILL.md"))
            if DELEGATION_MARKER in path.read_text(encoding="utf-8")
        )

        # Assert
        self.assertEqual(EXPECTED_DELEGATING_SKILLS, {path.parent.name for path in paths})
        for path in paths:
            bundled_path = bundled / path.parent.name / "SKILL.md"
            with self.subTest(skill=path.parent.name):
                self.assertEqual(
                    1,
                    bundled_path.read_text(encoding="utf-8").count(
                        DELEGATION_PREFLIGHT
                    ),
                )
                self.assertEqual(
                    1,
                    bundled_path.read_text(encoding="utf-8").count(
                        DELEGATION_RESOLVER
                    ),
                )

    def test_start_skill_preserves_plugin_native_initialization_protocol(self):
        # Arrange
        source = ROOT / ".agents/skills/start/SKILL.md"
        bundled = PLUGIN / "assets/studio/.agents/skills/start/SKILL.md"

        # Act
        source_text = source.read_text(encoding="utf-8")
        bundled_text = bundled.read_text(encoding="utf-8")

        # Assert
        for token in (
            "$codex-game-studios:start",
            "Initialization changeset",
            "at most 10 unique path mutations",
            "No writes precede approval",
            "Forbidden roots and every descendant",
            "tools.codex_studio.start_initialization",
        ):
            with self.subTest(token=token):
                self.assertIn(token, source_text)
                self.assertIn(token, bundled_text)

    def test_catalog_has_defined_namespace_parity_and_valid_skills(self):
        source = ROOT / ".agents/skills"
        bundled = PLUGIN / "assets/studio/.agents/skills"
        names = {path.parent.name for path in source.glob("*/SKILL.md")}
        transform, catalog = _namespace_api(self)
        policy = __import__("json").loads(
            (PLUGIN / "assets/payload-policy.json").read_text(encoding="utf-8")
        )
        approved_names = catalog(policy)
        self.assertEqual(73, len(names))
        for name in sorted(names):
            self.assertEqual(
                transform((source / name / "SKILL.md").read_bytes(), approved_names),
                (bundled / name / "SKILL.md").read_bytes(),
            )
            self.assertEqual([], validate_skill(bundled / name / "SKILL.md"))

    def test_bundled_catalog_has_no_plain_known_skill_invocations(self):
        # Arrange
        source = ROOT / ".agents/skills"
        bundled = PLUGIN / "assets/studio/.agents/skills"
        names = tuple(sorted(path.parent.name for path in source.glob("*/SKILL.md")))

        # Act / Assert
        self.assertEqual(73, len(names))
        for path in sorted(bundled.glob("*/SKILL.md")):
            with self.subTest(skill=path.parent.name):
                self.assertEqual(
                    set(),
                    _plain_catalog_invocations(path.read_text(encoding="utf-8"), names),
                )

    def test_canonical_catalog_keeps_source_local_plain_handoffs(self):
        # Arrange / Act / Assert
        cases = {
            "start": ("brainstorm", "setup-engine", "dev-story"),
            "setup-engine": ("brainstorm", "map-systems"),
            "skill-test": ("skill-test", "story-done", "gate-check"),
        }
        for skill, commands in cases.items():
            text = (ROOT / ".agents/skills" / skill / "SKILL.md").read_text(
                encoding="utf-8"
            )
            for command in commands:
                with self.subTest(skill=skill, command=command):
                    self.assertIn(f"${command}", text)
                    self.assertNotIn(f"$codex-game-studios:{command}", text)

    def test_bundled_start_handoffs_are_actual_namespaced_commands(self):
        # Arrange / Act
        text = (
            PLUGIN / "assets/studio/.agents/skills/start/SKILL.md"
        ).read_text(encoding="utf-8")

        # Assert
        for command in ("brainstorm", "setup-engine", "dev-story", "help"):
            with self.subTest(command=command):
                self.assertIn(f"$codex-game-studios:{command}", text)

    def test_skills_do_not_probe_repo_local_skill_installation(self):
        pattern = re.compile(r"\.agents/skills/[a-z0-9-]+/SKILL\.md")
        for path in sorted((ROOT / ".agents/skills").glob("*/SKILL.md")):
            self.assertIsNone(
                pattern.search(path.read_text(encoding="utf-8")), path
            )

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
                    self.assertEqual(1, text.count(_dependency_gate(dependency)))

    def test_catalog_validator_rejects_every_mutated_dependency_branch_action(self):
        mutations = {
            "availability": (
                "present in the current task's available skill catalog",
                "present in a repository-local catalog",
            ),
            "message": ("is not available", "was not discovered"),
            "defer": ("defer the handoff", "continue the handoff"),
            "do-not-invoke": ("do not invoke", "invoke"),
            "do-not-route": ("do not route", "route"),
            "do-not-search-copy": (
                "do not search for or copy a repository-local skill file",
                "search for and copy a repository-local skill file",
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            # Arrange
            root, plugin = _copy_catalog_fixture(directory)
            for skill, dependencies in EXPECTED_DEPENDENCIES.items():
                source_path = root / ".agents/skills" / skill / "SKILL.md"
                original = source_path.read_text(encoding="utf-8")
                for dependency in dependencies:
                    gate = _dependency_gate(dependency)
                    self.assertEqual(1, original.count(gate))
                    for action, (required, replacement) in mutations.items():
                        with self.subTest(
                            skill=skill, dependency=dependency, action=action
                        ):
                            tampered_gate = gate.replace(required, replacement, 1)
                            self.assertNotEqual(gate, tampered_gate)
                            tampered = original.replace(gate, tampered_gate, 1)
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
                                (skill, dependency, action, issues),
                            )
                            _write_fixture_skill(root, plugin, skill, original)

    def test_catalog_validator_enforces_delegation_governance_mutations(self):
        additions = (
            "Delegate to `qa-tester`.",
            "This workflow Spawns a named specialist.",
            "Use Codex custom agents by role and profile when delegation is useful.",
        )
        with tempfile.TemporaryDirectory() as directory:
            # Arrange
            root, plugin = _copy_catalog_fixture(directory)
            path = root / ".agents/skills/adopt/SKILL.md"
            original = path.read_text(encoding="utf-8")

            for instruction in additions:
                with self.subTest(instruction=instruction):
                    _write_fixture_skill(root, plugin, "adopt", original + f"\n{instruction}\n")

                    # Act
                    issues = validate_plugin_skill_catalog(root, plugin)

                    # Assert
                    self.assertTrue(
                        any("ungoverned delegation instruction" in issue.message for issue in issues),
                        issues,
                    )

            examples_only = original + """
```markdown
Delegate to `qa-tester` and spawn custom agents.
```
<!-- Use Codex custom agents by role. -->
"""
            _write_fixture_skill(root, plugin, "adopt", examples_only)
            self.assertEqual([], validate_plugin_skill_catalog(root, plugin))

            governed = root / ".agents/skills/code-review/SKILL.md"
            governed_text = governed.read_text(encoding="utf-8")
            _write_fixture_skill(
                root,
                plugin,
                "code-review",
                governed_text.replace(DELEGATION_MARKER, "", 1),
            )
            issues = validate_plugin_skill_catalog(root, plugin)
            self.assertTrue(
                any("delegation marker" in issue.message for issue in issues), issues
            )

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

    def test_bundled_validator_executes_validate_skill_from_empty_project(self):
        with tempfile.TemporaryDirectory() as directory:
            # Arrange
            project = Path(directory)
            bundled_validator = (
                PLUGIN / "assets/studio/tools/codex_studio/validate.py"
            ).resolve()
            bundled_skill = (
                PLUGIN / "assets/studio/.agents/skills/skill-test/SKILL.md"
            ).resolve()
            environment = {
                "PATH": os.environ.get("PATH", ""),
                "PYTHONDONTWRITEBYTECODE": "1",
            }

            # Act
            result = subprocess.run(
                [
                    sys.executable,
                    str(bundled_validator),
                    "--skill-file",
                    str(bundled_skill),
                ],
                cwd=project,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            # Assert
            self.assertFalse((project / "tools").exists())
            self.assertFalse((project / ".agents/skills").exists())
            self.assertFalse((project / "Codex Studio Testing Framework").exists())
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("Skill validation: PASS", result.stdout)

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
        self.assertNotIn("Add `category: [name]` to the skill entry", skill_test)
        self.assertNotIn("update the skill\n  or the test spec", skill_test)
        self.assertNotIn("to create new specs", skill_test)
        self.assertIn("verified canonical studio source checkout", skill_test)
        self.assertIn("stop without writing", skill_test)
        self.assertNotIn("show the reference-only changeset", setup_engine)
        self.assertIn("verified canonical studio source checkout", setup_engine)

    def test_generated_project_artifacts_use_stable_resource_provenance(self):
        # Arrange
        skills = {
            name: (ROOT / ".agents/skills" / name / "SKILL.md").read_text(
                encoding="utf-8"
            )
            for name in (
                "adopt",
                "architecture-decision",
                "create-architecture",
                "create-control-manifest",
                "test-setup",
            )
        }

        # Act
        adr_template = skills["architecture-decision"].split("Following this format:", 1)[1]
        adr_example = adr_template.split("## Engine Compatibility", 1)[1].split(
            "## ADR Dependencies", 1
        )[0]
        source_example = skills["create-control-manifest"].split("### Forbidden APIs", 1)[1].split(
            "### Cross-Cutting Constraints", 1
        )[0]
        engine_warning = skills["create-architecture"].split(
            "If an API is post-cutoff, flag it:", 1
        )[1].split("Get user approval", 1)[0]
        godot_workflow = skills["test-setup"].split(
            "Create `.github/workflows/tests.yml`:", 1
        )[1].split("### Unity", 1)[0]
        infrastructure_audit = skills["adopt"].split(
            "### 2e: Infrastructure Audit", 1
        )[1].split("### 2f: Technical Preferences Audit", 1)[0]
        generated_contexts = {
            "ADR engine compatibility": adr_example,
            "control manifest forbidden APIs": source_example,
            "architecture engine warning": engine_warning,
            "Godot test workflow": godot_workflow,
            "adoption infrastructure audit": infrastructure_audit,
        }

        # Assert
        for context, output in generated_contexts.items():
            with self.subTest(context=context):
                self.assertNotIn("../../../", output)
        self.assertIn("Codex Game Studios bundled engine reference:", adr_example)
        self.assertIn("Codex Game Studios bundled engine reference:", source_example)
        self.assertIn("Codex Game Studios bundled engine reference:", engine_warning)
        self.assertIn("[CONFIGURED GODOT VERSION]", godot_workflow)
        self.assertIn(
            "Codex Game Studios bundled engine reference:", infrastructure_audit
        )

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

    def test_resource_validator_rejects_placeholder_and_wildcard_traversal(self):
        cases = (
            "../../../docs/engine-reference/[engine]/../../../../outside",
            "../../../docs/engine-reference/<engine>/../outside.md",
            "../../../.codex/docs/templates/*/../outside.md",
            "../../../Codex Studio Testing Framework/skills/[category]/../../outside.md",
        )
        for reference in cases:
            with self.subTest(reference=reference), tempfile.TemporaryDirectory() as directory:
                # Arrange
                root, plugin = _copy_catalog_fixture(directory)
                path = root / ".agents/skills/bug-report/SKILL.md"
                text = path.read_text(encoding="utf-8") + f"\nTraversal: `{reference}`\n"
                _write_fixture_skill(root, plugin, "bug-report", text)

                # Act
                issues = validate_plugin_skill_catalog(root, plugin)

                # Assert
                self.assertTrue(
                    any(
                        "resource path is not lexically contained" in issue.message
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
