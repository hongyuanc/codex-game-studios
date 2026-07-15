"""End-to-end installed-studio workflows across native engine fixtures."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tests.plugin.helpers import (
    PLUGIN,
    approved_install,
    copy_plugin_fixture,
    init_git_repo,
    run_manager,
)
from tools.codex_studio.engine_pack import apply_activation, plan_activation
from tools.codex_studio.validate import (
    EXPECTED_CORE_NAMES,
    EXPECTED_PACK_NAMES,
    expected_active_agents,
    validate_installed_repository,
)
from studio_manager import decode_approval_context


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/plugin/fixtures/repos"
ENGINE_TARGETS = {
    "godot": ("4.6", "gdscript"),
    "unity": ("6000.1", "csharp"),
    "unreal": ("5.7", "cpp"),
}


class InstalledEngineWorkflowTests(unittest.TestCase):
    """Exercise real manager and engine-pack APIs in isolated Git repositories."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        )
        self.plugin = (Path(self.temporary.name) / "plugin").resolve()
        copy_plugin_fixture(PLUGIN, self.plugin)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def copy_fixture(self, name: str) -> Path:
        destination = (Path(self.temporary.name) / name).resolve()
        shutil.copytree(FIXTURES / name, destination)
        init_git_repo(destination)
        return destination

    def approve_operation(self, operation: str, repo: Path) -> tuple[dict[str, object], dict[str, object]]:
        planned = run_manager(operation, repo, plugin_root=self.plugin)
        self.assertEqual(2, planned.returncode, planned.stdout + planned.stderr)
        plan = json.loads(planned.stdout)
        applied = run_manager(
            operation,
            repo,
            str(plan["digest"]),
            plugin_root=self.plugin,
            approval_context=str(plan["approval_context"]),
        )
        self.assertEqual(0, applied.returncode, applied.stdout + applied.stderr)
        return plan, json.loads(applied.stdout)

    def test_fresh_fixture_install_verifies_unconfigured_studio(self):
        # Arrange
        repo = self.copy_fixture("fresh")

        # Act
        installed = approved_install(repo, self.plugin)
        issues = validate_installed_repository(repo)

        # Assert
        self.assertEqual(0, installed.applied.returncode, installed.applied.stdout + installed.applied.stderr)
        self.assertEqual([], issues)
        self.assertEqual(
            {f"{name}.toml" for name in EXPECTED_CORE_NAMES},
            {path.name for path in (repo / ".codex/agents").glob("*.toml")},
        )

    def test_each_engine_fixture_installs_activates_and_verifies(self):
        # Arrange / Act / Assert
        for engine, (version, language) in ENGINE_TARGETS.items():
            with self.subTest(engine=engine):
                repo = self.copy_fixture(engine)
                installed = approved_install(repo, self.plugin)
                self.assertEqual(0, installed.applied.returncode, installed.applied.stdout + installed.applied.stderr)
                apply_activation(
                    repo,
                    plan_activation(repo, engine, version=version, language=language),
                )

                issues = validate_installed_repository(repo)
                expected = expected_active_agents(repo)
                actual = {path.stem for path in (repo / ".codex/agents").glob("*.toml")}

                self.assertEqual([], issues)
                self.assertEqual(expected, actual)
                self.assertTrue(all((repo / ".codex/agent-packs" / name).is_dir() for name in ENGINE_TARGETS))

    def test_activated_pack_survives_update_and_uninstall_preserves_user_content(self):
        # Arrange
        engine = "godot"
        version, language = ENGINE_TARGETS[engine]
        repo = self.copy_fixture(engine)
        user_paths = [
            path.relative_to(repo)
            for path in repo.rglob("*")
            if (
                path.is_file()
                and ".git" not in path.parts
                and path.relative_to(repo).as_posix() != ".codex/config.toml"
            )
        ]
        original = {path: (repo / path).read_bytes() for path in user_paths}
        installed = approved_install(repo, self.plugin)
        self.assertEqual(
            0,
            installed.applied.returncode,
            installed.applied.stdout + installed.applied.stderr,
        )
        installed_document = json.loads(installed.planned.stdout)
        apply_activation(
            repo,
            plan_activation(repo, engine, version=version, language=language),
        )
        active_before = {
            name: (repo / ".codex/agents" / f"{name}.toml").read_bytes()
            for name in EXPECTED_PACK_NAMES[engine]
        }
        studio_before = (repo / ".codex/studio.toml").read_bytes()
        manifest_before = (repo / ".codex/active-engine.json").read_bytes()
        retained_manager_before = {
            path.relative_to(repo): path.read_bytes()
            for path in (
                repo / ".codex/codex-game-studios/legal/ATTRIBUTION.md",
                repo / ".codex/codex-game-studios/legal/LICENSE",
                repo / ".codex/codex-game-studios/manager.lock",
            )
        }

        # Act
        update_plan, _update_result = self.approve_operation("update", repo)

        # Assert
        self.assertEqual([], validate_installed_repository(repo))
        self.assertEqual(
            active_before,
            {
                name: (repo / ".codex/agents" / f"{name}.toml").read_bytes()
                for name in EXPECTED_PACK_NAMES[engine]
            },
        )

        # Act
        uninstall_plan, _uninstall_result = self.approve_operation("uninstall", repo)

        # Assert
        self.assertFalse((repo / ".codex/codex-game-studios/installation.json").exists())
        self.assertEqual(
            {f"{name}.toml" for name in EXPECTED_PACK_NAMES[engine]},
            {path.name for path in (repo / ".codex/agents").glob("*.toml")},
        )
        self.assertEqual(
            active_before,
            {
                name: (repo / ".codex/agents" / f"{name}.toml").read_bytes()
                for name in EXPECTED_PACK_NAMES[engine]
            },
        )
        self.assertTrue((repo / ".codex/active-engine.json").is_file())
        self.assertTrue((repo / ".codex/studio.toml").is_file())
        self.assertEqual(studio_before, (repo / ".codex/studio.toml").read_bytes())
        self.assertEqual(manifest_before, (repo / ".codex/active-engine.json").read_bytes())
        self.assertFalse((repo / ".codex/agent-packs").exists())
        control = repo / ".codex/codex-game-studios"
        self.assertEqual(
            {"legal", "manager.lock", "recovery"},
            {path.name for path in control.iterdir()},
        )
        self.assertEqual(
            {"ATTRIBUTION.md", "LICENSE"},
            {path.name for path in (control / "legal").iterdir()},
        )
        self.assertTrue((control / "manager.lock").is_file())
        for path, content in retained_manager_before.items():
            self.assertEqual(content, (repo / path).read_bytes(), path.as_posix())
        expected_generations = {
            decode_approval_context(
                str(document["approval_context"]), operation
            ).transaction_id
            for document, operation in (
                (installed_document, "install"),
                (update_plan, "update"),
                (uninstall_plan, "uninstall"),
            )
        }
        recovery = control / "recovery"
        self.assertEqual(expected_generations, {path.name for path in recovery.iterdir()})
        for generation_name in expected_generations:
            generation = recovery / generation_name
            self.assertEqual(
                {"authority.json", "journal.json", "quarantine", "snapshots"},
                {path.name for path in generation.iterdir()},
            )
            journal = json.loads(
                (generation / "journal.json").read_text(encoding="utf-8")
            )
            self.assertEqual("committed", journal["phase"])
        for path, content in original.items():
            self.assertEqual(content, (repo / path).read_bytes(), path.as_posix())
        config = (repo / ".codex/config.toml").read_text(encoding="utf-8")
        self.assertIn('fixture_setting = "godot-user-value"', config)


if __name__ == "__main__":
    unittest.main()
