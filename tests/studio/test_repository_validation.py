from pathlib import Path
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tools.codex_studio.validate import (
    validate_repository,
    validate_repository_counts,
    validate_runtime_references,
    validate_coverage_manifest,
    validate_testing_framework_parity,
    validate_hooks,
    validate_agent,
    validate_skill,
)


ROOT = Path(__file__).resolve().parents[2]


class RepositoryValidationTests(unittest.TestCase):
    def test_coverage_contract_is_immutable_and_complete(self):
        self.assertEqual([], validate_coverage_manifest(ROOT, "final"))
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            target = temp / "production/migration"
            target.mkdir(parents=True)
            original = (ROOT / "production/migration/claude-to-codex-coverage.yaml").read_text(encoding="utf-8")
            lines = original.splitlines()
            (target / "claude-to-codex-coverage.yaml").write_text(
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

    def test_coverage_rejects_unsafe_paths(self):
        original = (ROOT / "production/migration/claude-to-codex-coverage.yaml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            target = temp / "production/migration"
            target.mkdir(parents=True)
            unsafe = original.replace("  - source: .claude/agent-memory", "  - source: ../agent-memory", 1)
            (target / "claude-to-codex-coverage.yaml").write_text(unsafe, encoding="utf-8")
            issues = validate_coverage_manifest(temp, "final")
        messages = "\n".join(issue.message for issue in issues)
        self.assertIn("safe repository-relative", messages)
        self.assertIn("contract digest", messages)

    def test_coverage_rejects_symlinked_destination(self):
        original = (ROOT / "production/migration/claude-to-codex-coverage.yaml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            manifest = temp / "production/migration/claude-to-codex-coverage.yaml"
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
        self.assertIn("approved core agent identities", messages)
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
            (temp / ".claude").mkdir()
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
                "# READ BY: /design-system\n", encoding="utf-8"
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
                "---\nname: bad\ndescription: bad\nagent: old\nmaxTurns: 4\n---\n",
                encoding="utf-8",
            )
            messages = {issue.message for issue in validate_skill(path)}
        self.assertIn("contains Claude agent metadata", messages)
        self.assertIn("contains Claude turn-limit metadata", messages)

    def test_repository_counts_are_exact(self):
        self.assertEqual([], validate_repository_counts(ROOT))

    def test_pre_cleanup_gate_accepts_covered_legacy_sources(self):
        legacy = [path for path in (ROOT / ".claude").rglob("*") if path.is_file()]
        legacy += list(ROOT.rglob("CLAUDE.md"))
        if not legacy:
            report = (ROOT / ".superpowers/sdd/final-cleanup-subsystem-report.md").read_text(encoding="utf-8")
            self.assertIn("Codex Studio validation: PASS", report)
            self.assertIn("200 tests, OK", report)
            return
        self.assertEqual([], validate_runtime_references(ROOT, "pre-cleanup"))
        self.assertEqual([], validate_repository(ROOT, "pre-cleanup"))

    def test_final_gate_rejects_any_remaining_legacy_sources(self):
        issues = validate_runtime_references(ROOT, "final")
        legacy = [path for path in (ROOT / ".claude").rglob("*") if path.is_file()]
        legacy += list(ROOT.rglob("CLAUDE.md"))
        if legacy:
            self.assertTrue(any("legacy source remains" in issue.message for issue in issues))
        else:
            self.assertEqual([], issues)

    def test_unknown_phase_is_rejected(self):
        issues = validate_repository(ROOT, "surprise")
        self.assertTrue(any("unsupported validation phase" in issue.message for issue in issues))


if __name__ == "__main__":
    unittest.main()
