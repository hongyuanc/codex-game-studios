from pathlib import Path
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import tools.codex_studio.validate as validate_module
from tools.codex_studio.engine_pack import apply_activation, plan_activation
from tools.codex_studio.validate import (
    validate_repository,
    validate_repository_counts,
    validate_runtime_references,
    validate_coverage_manifest,
    validate_testing_framework_parity,
    validate_hooks,
    validate_agent,
    validate_skill,
    main,
)


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"


def _minimal_runtime_tree(root: Path) -> None:
    for relative in (
        ".agents", ".codex", ".github", "Codex Studio Testing Framework",
        "assets", "design", "docs", "production", "prototypes", "src",
        "tests", "tools",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    for relative in (
        "AGENTS.md", "README.md", "CONTRIBUTING.md", "SECURITY.md",
        "UPGRADING.md", ".gitignore",
    ):
        (root / relative).write_text("Codex\n", encoding="utf-8")


class RepositoryValidationTests(unittest.TestCase):
    def _configured_plugin_native_target(self, directory: str) -> Path:
        target = Path(directory) / "target"
        shutil.copytree(ROOT / "tests/studio/fixtures/engine-project", target)
        apply_activation(
            target,
            plan_activation(
                target, "godot", version="4.6", language="gdscript",
                source_root=ROOT,
            ),
        )
        return target

    def test_plugin_skill_catalog_validator_accepts_canonical_catalog(self):
        # Arrange
        validator = getattr(validate_module, "validate_plugin_skill_catalog", None)

        # Act / Assert
        self.assertIsNotNone(validator)
        self.assertEqual([], validator(ROOT, PLUGIN))

    def test_final_repository_validation_enforces_plugin_skill_catalog(self):
        # Arrange
        expected = validate_module.ValidationIssue(
            "error", "plugins/codex-game-studios", "catalog sentinel"
        )

        # Act
        with mock.patch.object(
            validate_module,
            "validate_plugin_skill_catalog",
            create=True,
            return_value=[expected],
        ) as validator:
            issues = validate_repository(ROOT, "final")

        # Assert
        validator.assert_called_once_with(ROOT.resolve(), PLUGIN.resolve())
        self.assertIn(expected, issues)

    def test_source_mode_remains_default_and_backward_compatible(self):
        # Arrange / Act / Assert
        self.assertEqual([], validate_repository(ROOT, "final"))
        self.assertEqual(0, main(["--root", str(ROOT), "--phase", "final"]))
        self.assertEqual(0, main(["--root", str(ROOT), "--mode", "source", "--phase", "final"]))

    def test_plugin_native_validator_accepts_fresh_target_without_global_payload(self):
        # Arrange
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            shutil.copytree(ROOT / "tests/studio/fixtures/engine-project", target)
            apply_activation(
                target,
                plan_activation(
                    target, "godot", version="4.6", language="gdscript", source_root=ROOT,
                ),
            )

            # Act
            issues = validate_module.validate_plugin_native_project(target, source_root=ROOT)
            status = main([
                "--mode", "plugin-native", "--root", str(target), "--source-root", str(ROOT), "--phase", "final",
            ])

            # Assert
            self.assertEqual([], issues)
            self.assertEqual(0, status)
            self.assertFalse((target / ".codex/agent-packs").exists())
            self.assertFalse((target / ".agents/skills").exists())

    def test_plugin_native_validator_requires_distinct_trusted_source_root(self):
        # Arrange
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            shutil.copytree(ROOT / "tests/studio/fixtures/engine-project", target)

            # Act
            with self.assertRaises(SystemExit) as raised:
                main(["--mode", "plugin-native", "--root", str(target), "--phase", "final"])

            # Assert
            self.assertEqual(2, raised.exception.code)

    def test_plugin_native_validator_accepts_exact_unconfigured_authority_without_pack_read(self):
        # Arrange
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            shutil.copytree(ROOT / "tests/studio/fixtures/engine-project", target)

            # Act
            with mock.patch(
                "tools.codex_studio.engine_pack._validate_packs",
                side_effect=AssertionError("unconfigured validation read an engine pack"),
            ):
                issues = validate_module.validate_plugin_native_project(
                    target, source_root=ROOT
                )

            # Assert
            self.assertEqual([], issues)

    def test_plugin_native_validator_rejects_empty_engine_version(self):
        # Arrange
        with tempfile.TemporaryDirectory() as directory:
            target = self._configured_plugin_native_target(directory)
            studio = target / ".codex/studio.toml"
            studio.write_text(
                studio.read_text(encoding="utf-8").replace('engine_version = "4.6"', 'engine_version = ""'),
                encoding="utf-8",
            )
            # Act
            issues = validate_module.validate_plugin_native_project(target, source_root=ROOT)
            # Assert
            self.assertTrue(issues)

    def test_plugin_native_validator_rejects_empty_language(self):
        # Arrange
        with tempfile.TemporaryDirectory() as directory:
            target = self._configured_plugin_native_target(directory)
            studio = target / ".codex/studio.toml"
            studio.write_text(
                studio.read_text(encoding="utf-8").replace('language = "gdscript"', 'language = ""'),
                encoding="utf-8",
            )
            # Act
            issues = validate_module.validate_plugin_native_project(target, source_root=ROOT)
            # Assert
            self.assertTrue(issues)

    def test_plugin_native_validator_rejects_incompatible_language(self):
        # Arrange
        with tempfile.TemporaryDirectory() as directory:
            target = self._configured_plugin_native_target(directory)
            studio = target / ".codex/studio.toml"
            studio.write_text(
                studio.read_text(encoding="utf-8").replace('language = "gdscript"', 'language = "python"'),
                encoding="utf-8",
            )
            # Act
            issues = validate_module.validate_plugin_native_project(target, source_root=ROOT)
            # Assert
            self.assertTrue(issues)

    def test_plugin_native_validator_rejects_bogus_review_mode(self):
        # Arrange
        with tempfile.TemporaryDirectory() as directory:
            target = self._configured_plugin_native_target(directory)
            studio = target / ".codex/studio.toml"
            studio.write_text(
                studio.read_text(encoding="utf-8").replace('review_mode = "phase-gated"', 'review_mode = "bogus"'),
                encoding="utf-8",
            )
            # Act
            issues = validate_module.validate_plugin_native_project(target, source_root=ROOT)
            # Assert
            self.assertTrue(issues)

    def test_plugin_native_validator_rejects_bogus_model_policy(self):
        # Arrange
        with tempfile.TemporaryDirectory() as directory:
            target = self._configured_plugin_native_target(directory)
            studio = target / ".codex/studio.toml"
            studio.write_text(
                studio.read_text(encoding="utf-8").replace('model_policy = "balanced"', 'model_policy = "bogus"'),
                encoding="utf-8",
            )
            # Act
            issues = validate_module.validate_plugin_native_project(target, source_root=ROOT)
            # Assert
            self.assertTrue(issues)

    def test_plugin_native_validator_rejects_unconfigured_manifest_state(self):
        # Arrange
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            shutil.copytree(ROOT / "tests/studio/fixtures/engine-project", target)
            (target / ".codex/active-engine.json").write_text(
                '{"engine":"godot","generated":{}}\n', encoding="utf-8"
            )
            # Act
            issues = validate_module.validate_plugin_native_project(target, source_root=ROOT)
            # Assert
            self.assertTrue(issues)

    def test_plugin_native_validator_rejects_unconfigured_active_agents_state(self):
        # Arrange
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            shutil.copytree(ROOT / "tests/studio/fixtures/engine-project", target)
            (target / ".codex/agents").mkdir()
            # Act
            issues = validate_module.validate_plugin_native_project(target, source_root=ROOT)
            # Assert
            self.assertTrue(issues)

    def test_plugin_native_cli_rejects_non_final_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            shutil.copytree(ROOT / "tests/studio/fixtures/engine-project", target)
            with self.assertRaises(SystemExit):
                main(["--mode", "plugin-native", "--phase", "pre-cleanup", "--root", str(target), "--source-root", str(ROOT)])

    def test_source_cli_rejects_source_root(self):
        with self.assertRaises(SystemExit):
            main(["--mode", "source", "--root", str(ROOT), "--source-root", str(ROOT)])

    def test_installed_cli_rejects_source_root(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit):
                main(["--mode", "installed", "--root", directory, "--source-root", str(ROOT)])

    def test_skill_file_cli_rejects_installed_mode(self):
        skill = ROOT / ".agents/skills/start/SKILL.md"
        with self.assertRaises(SystemExit):
            main(["--skill-file", str(skill), "--mode", "installed"])

    def test_skill_file_cli_rejects_plugin_native_source_root_mode(self):
        skill = ROOT / ".agents/skills/start/SKILL.md"
        with self.assertRaises(SystemExit):
            main([
                "--skill-file", str(skill), "--mode", "plugin-native",
                "--source-root", str(ROOT),
            ])

    def test_final_repository_validation_accepts_each_configured_engine_pack(self):
        targets = {
            "godot": ("4.6", "gdscript"),
            "unity": ("6000.1", "csharp"),
            "unreal": ("5.7", "cpp"),
        }
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            shutil.copytree(
                ROOT,
                project,
                ignore=shutil.ignore_patterns(
                    ".git", ".superpowers", "superpowers", "__pycache__"
                ),
            )
            for engine, (version, language) in targets.items():
                with self.subTest(engine=engine):
                    apply_activation(
                        project,
                        plan_activation(
                            project,
                            engine,
                            version=version,
                            language=language,
                        ),
                    )
                    self.assertEqual([], validate_repository(project, "final"))

    def test_coverage_contract_is_immutable_and_complete(self):
        self.assertEqual([], validate_coverage_manifest(ROOT, "final"))
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            target = temp / "production/migration"
            target.mkdir(parents=True)
            original = (ROOT / "production/migration/claude-to-codex-coverage.yaml").read_text(encoding="utf-8")  # enforcement-literal
            lines = original.splitlines()
            (target / "claude-to-codex-coverage.yaml").write_text(  # enforcement-literal
                "\n".join(lines[:2] + lines[6:]) + "\n", encoding="utf-8"
            )
            issues = validate_coverage_manifest(temp, "final")
        messages = "\n".join(issue.message for issue in issues)
        self.assertIn("203", messages)
        self.assertIn("contract digest", messages)

    def test_framework_parity_evidence_is_durable(self):
        path = ROOT / "production/migration/testing-framework-parity.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(1, data["version"])
        self.assertEqual(127, data["source_file_count"])
        self.assertEqual(127, len(data["entries"]))
        self.assertEqual(
            ["Codex Studio Testing Framework/skills/utility/vertical-slice.md"],
            data["native_extensions"],
        )
        self.assertTrue(all(len(entry["source_sha256"]) == 64 for entry in data["entries"]))
        self.assertTrue(all((ROOT / entry["destination"]).is_file() for entry in data["entries"]))
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            target = temp / "production/migration"
            target.mkdir(parents=True)
            tampered = dict(data)
            tampered["entries"] = data["entries"][:-1]
            (target / "testing-framework-parity.json").write_text(json.dumps(tampered), encoding="utf-8")
            issues = validate_testing_framework_parity(temp)
        self.assertTrue(any("127" in issue.message or "digest" in issue.message for issue in issues))

    def test_framework_parity_pins_source_metadata_and_exact_native_tree(self):
        evidence = ROOT / "production/migration/testing-framework-parity.json"
        data = json.loads(evidence.read_text(encoding="utf-8"))
        self.assertEqual("7bad60b7e0e71723b4b745e36950492d714595a3", data["source_commit"])
        self.assertEqual("CCGS Skill Testing Framework", data["source_root"])
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            shutil.copytree(
                ROOT / "Codex Studio Testing Framework",
                temp / "Codex Studio Testing Framework",
            )
            target = temp / "production/migration"
            target.mkdir(parents=True)
            for key, value in (
                ("source_commit", "0" * 40),
                ("source_root", "other-framework"),
            ):
                tampered = dict(data)
                tampered[key] = value
                (target / "testing-framework-parity.json").write_text(
                    json.dumps(tampered), encoding="utf-8"
                )
                issues = validate_testing_framework_parity(temp)
                self.assertTrue(any("source" in issue.message or "digest" in issue.message for issue in issues))
            (target / "testing-framework-parity.json").write_text(
                json.dumps(data), encoding="utf-8"
            )
            extra = temp / "Codex Studio Testing Framework/extra.md"
            extra.write_text("unexpected", encoding="utf-8")
            issues = validate_testing_framework_parity(temp)
            self.assertTrue(any("exact native framework" in issue.message for issue in issues))
            extra.unlink()
            mapped = temp / data["entries"][0]["destination"]
            mapped.unlink()
            issues = validate_testing_framework_parity(temp)
            self.assertTrue(any("exact native framework" in issue.message for issue in issues))
            outside = temp / "outside.md"
            outside.write_text("not native", encoding="utf-8")
            mapped.symlink_to(outside)
            issues = validate_testing_framework_parity(temp)
            self.assertTrue(any(
                issue.path == str(mapped.relative_to(temp)) and "symlink" in issue.message
                for issue in issues
            ))

    # enforcement-literal-start
    def test_runtime_scan_is_case_insensitive_and_covers_omitted_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            _minimal_runtime_tree(temp)
            (temp / "assets/provider.txt").write_text("cLaUdE cOdE", encoding="utf-8")
            (temp / "prototypes/provider.txt").write_text("aNtHrOpIc", encoding="utf-8")
            target = temp / "outside.txt"
            target.write_text("clean", encoding="utf-8")
            (temp / "src/escape.txt").symlink_to(target)
            issues = validate_runtime_references(temp, "final")
        self.assertTrue(any(issue.path == "assets/provider.txt" for issue in issues))
        self.assertTrue(any(issue.path == "prototypes/provider.txt" for issue in issues))
        self.assertTrue(any(issue.path == "src/escape.txt" and "symlink" in issue.message for issue in issues))

    def test_unmarked_test_and_validator_literals_fail_but_marked_lines_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            _minimal_runtime_tree(temp)
            (temp / "tests/unmarked.py").write_text("provider = 'ANTHROPIC'\n", encoding="utf-8")
            (temp / "tools/codex_studio").mkdir(parents=True)
            (temp / "tools/codex_studio/validate.py").write_text(
                "provider = 'claude code'\n", encoding="utf-8"
            )
            (temp / "tests/marked.py").write_text(
                "provider = 'anthropic'  # enforcement-literal\n", encoding="utf-8"
            )
            issues = validate_runtime_references(temp, "final")
        paths = {issue.path for issue in issues if "legacy runtime" in issue.message}
        self.assertIn("tests/unmarked.py", paths)
        self.assertIn("tools/codex_studio/validate.py", paths)
        self.assertNotIn("tests/marked.py", paths)

        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            _minimal_runtime_tree(temp)
            (temp / "tests/malformed.py").write_text(
                "# enforcement-" "literal-start\n# enforcement-" "literal-start\n",
                encoding="utf-8",
            )
            issues = validate_runtime_references(temp, "final")
        self.assertTrue(any(
            issue.path == "tests/malformed.py" and "marker" in issue.message
            for issue in issues
        ))

    def test_upgrading_historical_markers_are_bounded_and_balanced(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            _minimal_runtime_tree(temp)
            upgrade = temp / "UPGRADING.md"
            upgrade.write_text("Claude Code\n", encoding="utf-8")
            issues = validate_runtime_references(temp, "final")
            self.assertTrue(any(issue.path == "UPGRADING.md" and "legacy runtime" in issue.message for issue in issues))
            upgrade.write_text(
                "<!-- historical-source-start -->\nClaude Code\n<!-- historical-source-end -->\n",
                encoding="utf-8",
            )
            issues = validate_runtime_references(temp, "final")
            self.assertFalse(any(issue.path == "UPGRADING.md" and "legacy runtime" in issue.message for issue in issues))
            upgrade.write_text(
                "<!-- historical-source-start -->\n<!-- historical-source-start -->\nClaude Code\n",
                encoding="utf-8",
            )
            issues = validate_runtime_references(temp, "final")
            self.assertTrue(any(issue.path == "UPGRADING.md" and "marker" in issue.message for issue in issues))

    def test_readme_unmarked_upstream_runtime_name_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            _minimal_runtime_tree(temp)
            (temp / "README.md").write_text("Claude Code\n", encoding="utf-8")

            issues = validate_runtime_references(temp, "final")

        self.assertTrue(any(
            issue.path == "README.md"
            and issue.message == "contains legacy runtime product name"
            for issue in issues
        ))

    def test_readme_single_balanced_upstream_attribution_is_exempt(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            _minimal_runtime_tree(temp)
            (temp / "README.md").write_text(
                "Codex\n"
                "<!-- upstream-attribution-start -->\n"
                "Claude Code and Anthropic\n"
                "<!-- upstream-attribution-end -->\n",
                encoding="utf-8",
            )

            issues = validate_runtime_references(temp, "final")

        self.assertFalse(any(issue.path == "README.md" for issue in issues))

    def test_readme_attribution_does_not_exempt_provider_names_outside_block(self):
        readmes = {
            "before": (
                "Claude Code before\n"
                "<!-- upstream-attribution-start -->\n"
                "Claude Code and Anthropic\n"
                "<!-- upstream-attribution-end -->\n"
            ),
            "after": (
                "<!-- upstream-attribution-start -->\n"
                "Claude Code and Anthropic\n"
                "<!-- upstream-attribution-end -->\n"
                "Anthropic after\n"
            ),
        }
        for position, readme_text in readmes.items():
            with self.subTest(position=position), tempfile.TemporaryDirectory() as directory:
                temp = Path(directory)
                _minimal_runtime_tree(temp)
                (temp / "README.md").write_text(readme_text, encoding="utf-8")

                issues = validate_runtime_references(temp, "final")

                self.assertTrue(any(
                    issue.path == "README.md"
                    and issue.message in {
                        "contains legacy runtime product name",
                        "contains legacy runtime routing",
                    }
                    for issue in issues
                ))

    def test_readme_attribution_does_not_exempt_other_runtime_rules(self):
        adversarial_content = {
            "runtime_path": (".claude/", "contains legacy runtime path"),
            "slash_skill": ("/start", "contains slash-style invocation for a known skill"),
            "machine_path": ("/Users/example/project", "contains machine-specific absolute path"),
        }
        for case, (content, expected_message) in adversarial_content.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                temp = Path(directory)
                _minimal_runtime_tree(temp)
                (temp / "README.md").write_text(
                    "<!-- upstream-attribution-start -->\n"
                    "Claude Code and Anthropic\n"
                    f"{content}\n"
                    "<!-- upstream-attribution-end -->\n",
                    encoding="utf-8",
                )

                issues = validate_runtime_references(temp, "final")

                self.assertTrue(any(
                    issue.path == "README.md" and issue.message == expected_message
                    for issue in issues
                ))

    def test_readme_malformed_nested_or_duplicate_attribution_markers_fail(self):
        invalid_readmes = {
            "unbalanced": (
                "<!-- upstream-attribution-start -->\n"
                "Claude Code\n"
            ),
            "nested": (
                "<!-- upstream-attribution-start -->\n"
                "<!-- upstream-attribution-start -->\n"
                "Claude Code\n"
                "<!-- upstream-attribution-end -->\n"
            ),
            "duplicate": (
                "<!-- upstream-attribution-start -->\n"
                "Claude Code\n"
                "<!-- upstream-attribution-end -->\n"
                "<!-- upstream-attribution-start -->\n"
                "Anthropic\n"
                "<!-- upstream-attribution-end -->\n"
            ),
            "prefixed_start": (
                "prefix <!-- upstream-attribution-start -->\n"
                "Claude Code\n"
                "<!-- upstream-attribution-end -->\n"
            ),
            "suffixed_start": (
                "<!-- upstream-attribution-start --> suffix\n"
                "Claude Code\n"
                "<!-- upstream-attribution-end -->\n"
            ),
            "prefixed_end": (
                "<!-- upstream-attribution-start -->\n"
                "Claude Code\n"
                "prefix <!-- upstream-attribution-end -->\n"
            ),
            "suffixed_end": (
                "<!-- upstream-attribution-start -->\n"
                "Claude Code\n"
                "<!-- upstream-attribution-end --> suffix\n"
            ),
            "inline": (
                "<!-- upstream-attribution-start --> Claude Code "
                "<!-- upstream-attribution-end -->\n"
            ),
        }
        for case, readme_text in invalid_readmes.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                temp = Path(directory)
                _minimal_runtime_tree(temp)
                (temp / "README.md").write_text(readme_text, encoding="utf-8")

                issues = validate_runtime_references(temp, "final")

                self.assertTrue(any(
                    issue.path == "README.md" and "marker" in issue.message
                    for issue in issues
                ))
                self.assertTrue(any(
                    issue.path == "README.md"
                    and issue.message == "contains legacy runtime product name"
                    for issue in issues
                ))

    def test_upstream_attribution_markers_outside_readme_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            _minimal_runtime_tree(temp)
            (temp / "CONTRIBUTING.md").write_text(
                "<!-- upstream-attribution-start -->\n"
                "Claude Code\n"
                "<!-- upstream-attribution-end -->\n",
                encoding="utf-8",
            )

            issues = validate_runtime_references(temp, "final")

        self.assertTrue(any(
            issue.path == "CONTRIBUTING.md"
            and issue.message == "upstream attribution markers are restricted to README.md"
            for issue in issues
        ))
    # enforcement-literal-end

    def test_walk_errors_are_validation_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            _minimal_runtime_tree(temp)

            def failed_walk(path, *, followlinks, onerror=None):
                if onerror is not None:
                    onerror(PermissionError(13, "denied", str(path / "unreadable")))
                return iter(())

            with mock.patch("tools.codex_studio.validate.os.walk", side_effect=failed_walk):
                issues = validate_runtime_references(temp, "final")
        self.assertTrue(any("cannot traverse runtime directory" in issue.message for issue in issues))

    def test_coverage_rejects_unsafe_paths(self):
        original = (ROOT / "production/migration/claude-to-codex-coverage.yaml").read_text(encoding="utf-8")  # enforcement-literal
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            target = temp / "production/migration"
            target.mkdir(parents=True)
            unsafe = original.replace("  - source: .claude/agent-memory", "  - source: ../agent-memory", 1)  # enforcement-literal
            (target / "claude-to-codex-coverage.yaml").write_text(unsafe, encoding="utf-8")  # enforcement-literal
            issues = validate_coverage_manifest(temp, "final")
        messages = "\n".join(issue.message for issue in issues)
        self.assertIn("safe repository-relative", messages)
        self.assertIn("contract digest", messages)

    def test_coverage_rejects_symlinked_destination(self):
        original = (ROOT / "production/migration/claude-to-codex-coverage.yaml").read_text(encoding="utf-8")  # enforcement-literal
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            manifest = temp / "production/migration/claude-to-codex-coverage.yaml"  # enforcement-literal
            manifest.parent.mkdir(parents=True)
            manifest.write_text(original, encoding="utf-8")
            target = temp / "real.toml"
            target.write_text("profile", encoding="utf-8")
            destination = temp / ".codex/agents/accessibility-specialist.toml"
            destination.parent.mkdir(parents=True)
            destination.symlink_to(target)
            issues = validate_coverage_manifest(temp, "final")
        self.assertTrue(any("symlink" in issue.message for issue in issues))

    def test_exact_inventory_rejects_identity_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            shutil.copytree(ROOT / ".codex", temp / ".codex")
            shutil.copytree(ROOT / ".agents", temp / ".agents")
            (temp / "AGENTS.md").write_text("root", encoding="utf-8")
            for relative in (
                "assets/data", "assets/shaders", "design/gdd", "design/narrative",
                "prototypes", "src/ai", "src/core", "src/gameplay",
                "src/networking", "src/ui", "tests",
            ):
                path = temp / relative / "AGENTS.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("scope", encoding="utf-8")
            original = temp / ".codex/agents/writer.toml"
            replacement = temp / ".codex/agents/impostor.toml"
            replacement.write_text(original.read_text(encoding="utf-8").replace('name = "writer"', 'name = "impostor"'), encoding="utf-8")
            original.unlink()
            packed = temp / ".codex/agent-packs/godot/godot-specialist.toml"
            packed.rename(temp / ".codex/agent-packs/godot/impostor-specialist.toml")
            skill = temp / ".agents/skills/help"
            skill.rename(temp / ".agents/skills/impostor-help")
            template = temp / ".codex/docs/templates/test-plan.md"
            template.rename(temp / ".codex/docs/templates/impostor-plan.md")
            issues = validate_repository_counts(temp)
        messages = "\n".join(issue.message for issue in issues)
        self.assertIn("approved active agent identities", messages)
        self.assertIn("approved packed identities", messages)
        self.assertIn("approved skill identities", messages)
        self.assertIn("approved templates", messages)

    def test_skill_frontmatter_is_exact_and_matches_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrong-name/SKILL.md"
            path.parent.mkdir()
            path.write_text(
                "---\nname: other\ndescription: Use when testing.\nextra: no\n---\nBody\n",
                encoding="utf-8",
            )
            messages = "\n".join(issue.message for issue in validate_skill(path))
        self.assertIn("frontmatter fields", messages)
        self.assertIn("directory name", messages)

    def test_read_decode_and_nul_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            binary = temp / "bad/SKILL.md"
            binary.parent.mkdir()
            binary.write_bytes(b"---\nname: bad\n\xff\x00")
            skill_issues = validate_skill(binary)
            readme = temp / "README.md"
            readme.write_bytes(b"Codex\x00hidden")
            runtime_issues = validate_runtime_references(temp, "final")
        self.assertTrue(any("UTF-8" in issue.message or "NUL" in issue.message for issue in skill_issues))
        self.assertTrue(any("NUL" in issue.message for issue in runtime_issues))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "skill/SKILL.md"
            path.parent.mkdir()
            path.write_text("---\nname: skill\ndescription: trigger\n---\n", encoding="utf-8")
            with mock.patch("pathlib.Path.read_bytes", side_effect=OSError("denied")):
                issues = validate_skill(path)
        self.assertTrue(any("cannot read" in issue.message for issue in issues))

    def test_symlinked_runtime_artifacts_fail_closed(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks unavailable")
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            target = temp / "target.toml"
            target.write_text((ROOT / ".codex/agents/writer.toml").read_text(encoding="utf-8"), encoding="utf-8")
            link = temp / "writer.toml"
            link.symlink_to(target)
            issues = validate_agent(link)
        self.assertTrue(any("symlink" in issue.message for issue in issues))

    def test_hook_contract_loads_from_supplied_root(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            hooks = temp / ".codex/hooks.json"
            hooks.parent.mkdir(parents=True)
            shutil.copy2(ROOT / ".codex/hooks.json", hooks)
            issues = validate_hooks(hooks, root=temp)
        self.assertTrue(any("hook runner" in issue.message for issue in issues))

        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            hooks = temp / ".codex/hooks.json"
            runner = temp / ".codex/hooks/hook_runner.py"
            runner.parent.mkdir(parents=True)
            shutil.copy2(ROOT / ".codex/hooks.json", hooks)
            runtime = (ROOT / ".codex/hooks/hook_runner.py").read_text(encoding="utf-8")
            runner.write_text(runtime.replace('    "session-stop",', '    "alternate-root-only",', 1), encoding="utf-8")
            issues = validate_hooks(hooks, root=temp)
        self.assertTrue(any("alternate-root-only" in issue.message for issue in issues))

    def test_final_phase_rejects_empty_legacy_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            (temp / ".claude").mkdir()  # enforcement-literal
            (temp / "CCGS Skill Testing Framework").mkdir()
            issues = validate_runtime_references(temp, "final")
        messages = "\n".join(issue.message for issue in issues)
        self.assertIn("legacy directory remains", messages)

    def test_final_gate_scans_design_runtime_references(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            for relative in (
                ".agents", ".codex", ".github", "Codex Studio Testing Framework",
                "docs", "tools", "tests", "production", "design",
            ):
                (temp / relative).mkdir(parents=True)
            for relative in (
                "AGENTS.md", "README.md", "CONTRIBUTING.md", "SECURITY.md",
                "UPGRADING.md", ".gitignore",
            ):
                (temp / relative).write_text("Codex\n", encoding="utf-8")
            (temp / "design/registry.yaml").write_text(
                "# READ BY: /design-system\n", encoding="utf-8"  # enforcement-literal
            )
            issues = validate_runtime_references(temp, "final")
        self.assertTrue(any(
            issue.path == "design/registry.yaml" and "slash-style" in issue.message
            for issue in issues
        ))

    def test_skill_rejects_legacy_agent_and_turn_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            path.write_text(
                "---\nname: bad\ndescription: bad\nAgEnT: old\nmAxTuRnS: 4\n---\n",
                encoding="utf-8",
            )
            messages = {issue.message for issue in validate_skill(path)}
        self.assertIn("contains Claude agent metadata", messages)  # enforcement-literal
        self.assertIn("contains Claude turn-limit metadata", messages)  # enforcement-literal

    def test_repository_counts_are_exact(self):
        self.assertEqual([], validate_repository_counts(ROOT))

    def test_source_counts_ignore_plugin_payload_instructions_but_require_root_instructions(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            shutil.copytree(
                ROOT,
                project,
                ignore=shutil.ignore_patterns(
                    ".git", ".superpowers", "superpowers", "__pycache__"
                ),
            )

            self.assertEqual([], validate_repository_counts(project))

            (project / "src/ui/AGENTS.md").unlink()
            issues = validate_repository_counts(project)

        self.assertTrue(
            any(
                issue.path == "AGENTS.md"
                and "src/ui/AGENTS.md" in issue.message
                and "plugins/codex-game-studios/assets/studio/src/ui/AGENTS.md"
                not in issue.message
                for issue in issues
            )
        )

    def test_source_counts_ignore_only_agents_below_tests_plugin_boundary(self):
        # Arrange
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            shutil.copytree(
                ROOT,
                project,
                ignore=shutil.ignore_patterns(
                    ".git", ".superpowers", "superpowers", "__pycache__"
                ),
            )
            ignored = project / "tests/plugin/adversarial/nested/AGENTS.md"
            ignored.parent.mkdir(parents=True)
            ignored.write_text("fixture-only instructions\n", encoding="utf-8")

            # Act / Assert
            self.assertEqual([], validate_repository_counts(project))

            outside = project / "tests/plugin-sibling/AGENTS.md"
            outside.parent.mkdir(parents=True)
            outside.write_text("unexpected instructions\n", encoding="utf-8")
            issues = validate_repository_counts(project)

        self.assertTrue(
            any(
                issue.path == "AGENTS.md"
                and "tests/plugin-sibling/AGENTS.md" in issue.message
                for issue in issues
            )
        )

    def test_pre_cleanup_gate_accepts_covered_legacy_sources(self):
        legacy = [path for path in (ROOT / ".claude").rglob("*") if path.is_file()]  # enforcement-literal
        legacy += list(ROOT.rglob("CLAUDE.md"))  # enforcement-literal
        if not legacy:
            report = (ROOT / ".superpowers/sdd/final-cleanup-subsystem-report.md").read_text(encoding="utf-8")
            self.assertIn("Codex Studio validation: PASS", report)
            self.assertIn("200 tests, OK", report)
            return
        self.assertEqual([], validate_runtime_references(ROOT, "pre-cleanup"))
        self.assertEqual([], validate_repository(ROOT, "pre-cleanup"))

    def test_final_gate_rejects_any_remaining_legacy_sources(self):
        issues = validate_runtime_references(ROOT, "final")
        legacy = [path for path in (ROOT / ".claude").rglob("*") if path.is_file()]  # enforcement-literal
        legacy += list(ROOT.rglob("CLAUDE.md"))  # enforcement-literal
        if legacy:
            self.assertTrue(any("legacy source remains" in issue.message for issue in issues))
        else:
            self.assertEqual([], issues)

    def test_unknown_phase_is_rejected(self):
        issues = validate_repository(ROOT, "surprise")
        self.assertTrue(any("unsupported validation phase" in issue.message for issue in issues))


if __name__ == "__main__":
    unittest.main()
