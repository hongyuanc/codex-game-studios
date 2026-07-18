"""Digest-bound migration tests for authenticated 1.0.0 installations."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import venv
from unittest import mock

from tests.plugin.helpers import (
    PLUGIN,
    init_git_repo,
    run_manager,
    snapshot_tree,
    write_installed_fixture,
)

import legacy_payload
from models import MigrationState, canonical_json, digest_document
import studio_manager
import transaction


class LegacyMigrationTests(unittest.TestCase):
    """Require migration to preserve every target it cannot authenticate."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        )
        self.repo = Path(self.temporary.name) / "repo"
        init_git_repo(self.repo)
        self._write_legacy_fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_legacy_fixture(self) -> None:
        with legacy_payload.verified_legacy_snapshot(
            PLUGIN, "1.0.0"
        ) as (legacy_root, _manifest):
            write_installed_fixture(self.repo, legacy_root)

    def _approved(self):
        context = studio_manager.new_approval_context("migrate")
        plan = studio_manager.plan_operation("migrate", self.repo, PLUGIN, context)
        self.assertFalse(plan.conflicts)
        return context, plan

    def _payload_snapshot(self):
        return {
            path: value
            for path, value in snapshot_tree(self.repo).items()
            if path != ".codex/codex-game-studios/manager.lock"
            and not path.startswith(".codex/codex-game-studios/recovery/")
            and path != ".codex/codex-game-studios/recovery"
        }

    def test_migrate_plan_removes_only_unchanged_redundant_legacy_paths(self):
        # Arrange
        customized = self.repo / ".agents/skills/start/SKILL.md"
        customized.write_text("user customization\n", encoding="utf-8")

        # Act
        plan = studio_manager.plan_operation(
            "migrate",
            self.repo,
            PLUGIN,
            studio_manager.new_approval_context("migrate"),
        )

        # Assert
        removed = {action.path for action in plan.actions if action.kind == "remove"}
        preserved = {
            action.path for action in plan.actions if action.kind == "preserve"
        }
        self.assertNotIn(".agents/skills/start/SKILL.md", removed)
        self.assertIn(".agents/skills/start/SKILL.md", preserved)
        self.assertIn(".agents/skills/adopt/SKILL.md", removed)
        self.assertIn(".codex/studio.toml", preserved)
        self.assertIn("AGENTS.md", preserved)

    def test_migrate_plan_preserves_content_mode_type_and_child_customizations(self):
        # Arrange
        content = self.repo / ".agents/skills/start/SKILL.md"
        content.write_bytes(content.read_bytes() + b"custom\n")
        mode = self.repo / ".agents/skills/adopt/SKILL.md"
        os.chmod(mode, 0o600)
        wrong_type = self.repo / ".codex/agents/ai-programmer.toml"
        wrong_type.unlink()
        wrong_type.mkdir()
        child = self.repo / ".agents/skills/user-owned.txt"
        child.write_text("user\n", encoding="utf-8")

        # Act
        plan = studio_manager.plan_operation(
            "migrate",
            self.repo,
            PLUGIN,
            studio_manager.new_approval_context("migrate"),
        )

        # Assert
        removed = {action.path for action in plan.actions if action.kind == "remove"}
        preserved = {
            action.path for action in plan.actions if action.kind == "preserve"
        }
        for path in (
            ".agents/skills/start/SKILL.md",
            ".agents/skills/adopt/SKILL.md",
            ".codex/agents/ai-programmer.toml",
            ".agents/skills",
        ):
            self.assertNotIn(path, removed)
            self.assertIn(path, preserved)

    def test_migration_state_has_exact_canonical_schema_and_sorted_unique_paths(self):
        # Arrange
        state = MigrationState(
            schema_version=2,
            plugin_version="2.0.0",
            legacy_version="1.0.0",
            legacy_state_checksum="a" * 64,
            preserved_paths=("z/path", "a/path"),
            migrated_at="2026-07-18T01:02:03Z",
            checksum="",
        )

        # Act / Assert
        with self.assertRaises(studio_manager.ManagerError):
            studio_manager.migration_state_with_checksum(state)
        canonical = dataclasses.replace(state, preserved_paths=("a/path", "z/path"))
        canonical = studio_manager.migration_state_with_checksum(canonical)
        raw = studio_manager.write_migration_state_document(canonical)
        document = json.loads(raw)
        self.assertEqual(
            {
                "schema_version",
                "plugin_version",
                "legacy_version",
                "legacy_state_checksum",
                "preserved_paths",
                "migrated_at",
                "checksum",
            },
            set(document),
        )
        self.assertEqual(canonical_json(document), raw)

    def test_migrate_apply_writes_schema_two_state_after_legacy_removals(self):
        # Arrange
        context, plan = self._approved()
        observed_state_at_remove: list[int] = []
        original = studio_manager._apply_lifecycle_action

        def observe_state(action, *args, **kwargs):
            if action.kind == "remove":
                document = json.loads(
                    (self.repo / studio_manager.STATE_RELATIVE_PATH).read_text(
                        encoding="utf-8"
                    )
                )
                observed_state_at_remove.append(document["schema_version"])
            return original(action, *args, **kwargs)

        # Act
        with mock.patch(
            "studio_manager._apply_lifecycle_action", side_effect=observe_state
        ):
            result = studio_manager.apply_operation(
                plan, self.repo, PLUGIN, approval_context=context
            )

        # Assert
        self.assertEqual("committed", result.status)
        self.assertTrue(observed_state_at_remove)
        self.assertEqual({1}, set(observed_state_at_remove))
        state = studio_manager.load_installation_state(
            self.repo / studio_manager.STATE_RELATIVE_PATH
        )
        self.assertIsInstance(state, MigrationState)
        self.assertEqual(2, state.schema_version)
        self.assertEqual("1.0.0", state.legacy_version)
        self.assertEqual("2.0.0", state.plugin_version)

    def test_migrate_failure_after_first_remove_rolls_back_exactly(self):
        # Arrange
        context, plan = self._approved()
        before = self._payload_snapshot()
        real_apply = transaction.apply_transaction

        def injected(*args, **kwargs):
            kwargs["failpoint"] = lambda phase: (
                (_ for _ in ()).throw(RuntimeError("injected"))
                if phase == "after-first-remove"
                else None
            )
            return real_apply(*args, **kwargs)

        # Act / Assert
        with mock.patch("transaction.apply_transaction", side_effect=injected):
            with self.assertRaises(RuntimeError):
                studio_manager.apply_operation(
                    plan, self.repo, PLUGIN, approval_context=context
                )
        self.assertEqual(before, self._payload_snapshot())

    def test_migrate_rejects_stale_plan_and_tampered_legacy_authority_without_writes(self):
        # Arrange
        context, plan = self._approved()
        target = self.repo / ".agents/skills/adopt/SKILL.md"
        target.write_bytes(target.read_bytes() + b"raced\n")
        changed = self._payload_snapshot()

        # Act / Assert
        with self.assertRaises(studio_manager.ManagerError) as caught:
            studio_manager.apply_operation(
                plan, self.repo, PLUGIN, approval_context=context
            )
        self.assertEqual("STALE_PLAN", caught.exception.code)
        self.assertEqual(changed, self._payload_snapshot())

        state_path = self.repo / studio_manager.STATE_RELATIVE_PATH
        document = json.loads(state_path.read_text(encoding="utf-8"))
        document["checksum"] = "0" * 64
        state_path.write_bytes(canonical_json(document))
        tampered = self._payload_snapshot()
        with self.assertRaises(studio_manager.ManagerError) as caught:
            studio_manager.plan_operation("migrate", self.repo, PLUGIN)
        self.assertEqual("INVALID_INSTALLATION_STATE", caught.exception.code)
        self.assertEqual(tampered, self._payload_snapshot())

    def test_migrate_validation_rejects_concurrent_unapproved_sibling_addition(self):
        # Arrange
        context, plan = self._approved()
        real_apply = transaction.apply_transaction
        sibling = self.repo / ".agents/concurrent-user.txt"

        def injected(*args, **kwargs):
            def failpoint(phase):
                if phase == "validation-started":
                    sibling.write_text("concurrent\n", encoding="utf-8")

            kwargs["failpoint"] = failpoint
            return real_apply(*args, **kwargs)

        # Act / Assert
        with mock.patch("transaction.apply_transaction", side_effect=injected):
            with self.assertRaises(studio_manager.ManagerError) as caught:
                studio_manager.apply_operation(
                    plan, self.repo, PLUGIN, approval_context=context
                )
        self.assertEqual("VALIDATION_FAILED", caught.exception.code)
        self.assertEqual(b"concurrent\n", sibling.read_bytes())
        self.assertTrue((self.repo / ".agents/skills/adopt/SKILL.md").is_file())

    def test_migrate_validation_rejects_preserved_child_mutation_during_apply(self):
        # Arrange
        context, plan = self._approved()
        real_apply = transaction.apply_transaction
        preserved = self.repo / ".codex/studio.toml"

        def injected(*args, **kwargs):
            def failpoint(phase):
                if phase == "validation-started":
                    preserved.write_bytes(preserved.read_bytes() + b"# concurrent\n")

            kwargs["failpoint"] = failpoint
            return real_apply(*args, **kwargs)

        # Act / Assert
        with mock.patch("transaction.apply_transaction", side_effect=injected):
            with self.assertRaises(studio_manager.ManagerError) as caught:
                studio_manager.apply_operation(
                    plan, self.repo, PLUGIN, approval_context=context
                )
        self.assertEqual("VALIDATION_FAILED", caught.exception.code)
        self.assertTrue(preserved.read_bytes().endswith(b"# concurrent\n"))
        self.assertTrue((self.repo / ".agents/skills/adopt/SKILL.md").is_file())

    def test_migrate_rejects_tampered_authenticated_capsule_without_writes(self):
        # Arrange
        plugin = Path(self.temporary.name) / "plugin"
        from tests.plugin.helpers import copy_plugin_fixture

        copy_plugin_fixture(PLUGIN, plugin)
        archive = plugin / "assets/legacy/1.0.0/studio.zip"
        archive.write_bytes(archive.read_bytes() + b"tampered")
        before = snapshot_tree(self.repo)

        # Act / Assert
        with self.assertRaises(studio_manager.ManagerError) as caught:
            studio_manager.plan_operation("migrate", self.repo, plugin)
        self.assertEqual("INVALID_PAYLOAD", caught.exception.code)
        self.assertEqual(before, snapshot_tree(self.repo))

    def test_schema_routing_uses_legacy_snapshot_then_plugin_native_validation(self):
        # Arrange / Act / Assert
        with mock.patch(
            "studio_manager.verified_legacy_snapshot",
            wraps=legacy_payload.verified_legacy_snapshot,
        ) as verified:
            plan = studio_manager.plan_operation("verify", self.repo, PLUGIN)
        self.assertFalse(plan.conflicts)
        verified.assert_called()

        context, migration = self._approved()
        studio_manager.apply_operation(
            migration, self.repo, PLUGIN, approval_context=context
        )
        with mock.patch(
            "studio_manager.verified_legacy_snapshot",
            side_effect=AssertionError("schema-2 must not route through legacy"),
        ):
            findings = studio_manager.validate_installed_read_only(self.repo, PLUGIN)
        self.assertEqual([], findings)

    def test_isolated_legacy_validation_does_not_pollute_schema_two_process(self):
        # Arrange: emulate a long-lived manager process with no validator package
        # imported before the first authenticated legacy operation.
        prefix = "tools.codex_studio"
        saved = {
            name: module
            for name, module in tuple(sys.modules.items())
            if name == "tools" or name == prefix or name.startswith(prefix + ".")
        }
        for name in saved:
            sys.modules.pop(name, None)

        try:
            # Act: verify, repair, migrate, and verify schema 2 in one process.
            verify = studio_manager.plan_operation("verify", self.repo, PLUGIN)
            self.assertFalse(verify.conflicts)
            self.assertFalse(any(
                name == prefix or name.startswith(prefix + ".")
                for name in sys.modules
            ))

            damaged = self.repo / ".agents/skills/adopt/SKILL.md"
            damaged.unlink()
            repair_context = studio_manager.new_approval_context("repair")
            repair = studio_manager.plan_operation(
                "repair", self.repo, PLUGIN, repair_context
            )
            studio_manager.apply_operation(
                repair, self.repo, PLUGIN, approval_context=repair_context
            )

            migration_context, migration = self._approved()
            studio_manager.apply_operation(
                migration,
                self.repo,
                PLUGIN,
                approval_context=migration_context,
            )
            self.assertEqual(
                [], studio_manager.validate_installed_read_only(self.repo, PLUGIN)
            )
            self.assertFalse(any(
                name == prefix or name.startswith(prefix + ".")
                for name in sys.modules
            ))
        finally:
            for name in tuple(sys.modules):
                if name == "tools" or name == prefix or name.startswith(prefix + "."):
                    sys.modules.pop(name, None)
            sys.modules.update(saved)

    def test_legacy_validation_uses_snapshot_dependencies_without_touching_parent_modules(self):
        # Arrange: preload the current validator family and make its validation
        # dependency incomplete. Authenticated legacy validation must not import it.
        import tools.codex_studio.validate as current_validator
        import tools.codex_studio.engine_pack as current_engine_pack

        prefix = "tools.codex_studio"
        before = {
            name: module
            for name, module in sys.modules.items()
            if name == "tools" or name == prefix or name.startswith(prefix + ".")
        }
        before_path = tuple(sys.path)
        before_bytecode_policy = sys.dont_write_bytecode

        # Act
        loader = current_engine_pack.load_studio_config
        del current_engine_pack.load_studio_config
        try:
            findings = studio_manager.validate_installed_read_only(self.repo, PLUGIN)
        finally:
            current_engine_pack.load_studio_config = loader

        # Assert
        self.assertEqual([], findings)
        after = {
            name: module
            for name, module in sys.modules.items()
            if name == "tools" or name == prefix or name.startswith(prefix + ".")
        }
        self.assertEqual(set(before), set(after))
        for name, module in before.items():
            self.assertIs(module, after[name])
        self.assertEqual(before_path, tuple(sys.path))
        self.assertEqual(before_bytecode_policy, sys.dont_write_bytecode)

    def test_legacy_validator_child_disables_site_and_rejects_shadow_tools_package(self):
        # Arrange: give the selected interpreter a regular site-packages `tools`
        # package that would outrank the authenticated snapshot namespace package.
        venv_root = Path(self.temporary.name) / "hostile-python"
        venv.EnvBuilder(with_pip=False).create(venv_root)
        if os.name == "nt":
            executable = venv_root / "Scripts/python.exe"
            site_packages = venv_root / "Lib/site-packages"
        else:
            executable = venv_root / "bin/python"
            site_packages = next(venv_root.glob("lib/python*/site-packages"))
        marker = Path(self.temporary.name) / "shadow-tools-imported"
        shadow = site_packages / "tools"
        shadow.mkdir()
        shadow.joinpath("__init__.py").write_text(
            "import pathlib, sys\n"
            f"pathlib.Path({str(marker)!r}).write_text(str(sys.flags.no_site))\n"
            "raise RuntimeError('unauthenticated tools shadow imported')\n",
            encoding="utf-8",
        )
        observed_commands: list[tuple[str, ...]] = []
        real_run = subprocess.run

        def observe(command, *args, **kwargs):
            observed_commands.append(tuple(command))
            return real_run(command, *args, **kwargs)

        # Act
        validation_error = None
        with mock.patch(
            "studio_manager.subprocess.run", side_effect=observe
        ), mock.patch.object(studio_manager.sys, "executable", str(executable)):
            try:
                findings = studio_manager.validate_installed_read_only(
                    self.repo, PLUGIN
                )
            except studio_manager.ManagerError as error:
                validation_error = error
                findings = []

        # Assert
        self.assertIsNone(validation_error)
        self.assertEqual([], findings)
        self.assertEqual(1, len(observed_commands))
        self.assertEqual(("-I", "-S", "-B"), observed_commands[0][1:4])
        self.assertFalse(marker.exists())

    def test_legacy_repair_and_uninstall_apply_through_authenticated_snapshot(self):
        # Arrange: damage one authenticated legacy file, then repair it.
        target = self.repo / ".agents/skills/adopt/SKILL.md"
        expected = target.read_bytes()
        target.unlink()
        repair_context = studio_manager.new_approval_context("repair")
        repair = studio_manager.plan_operation(
            "repair", self.repo, PLUGIN, repair_context
        )

        # Act / Assert
        repaired = studio_manager.apply_operation(
            repair, self.repo, PLUGIN, approval_context=repair_context
        )
        self.assertEqual("committed", repaired.status)
        self.assertEqual(expected, target.read_bytes())
        self.assertEqual([], studio_manager.validate_installed_read_only(
            self.repo, PLUGIN
        ))

        # Arrange / Act: legacy uninstall uses the same authenticated capsule.
        uninstall_context = studio_manager.new_approval_context("uninstall")
        uninstall = studio_manager.plan_operation(
            "uninstall", self.repo, PLUGIN, uninstall_context
        )
        uninstalled = studio_manager.apply_operation(
            uninstall, self.repo, PLUGIN, approval_context=uninstall_context
        )

        # Assert
        self.assertEqual("committed", uninstalled.status)
        self.assertFalse((self.repo / studio_manager.STATE_RELATIVE_PATH).exists())
        self.assertFalse(target.exists())

    def test_repeated_migrate_is_read_only_and_reports_already_migrated(self):
        # Arrange
        context, plan = self._approved()
        studio_manager.apply_operation(
            plan, self.repo, PLUGIN, approval_context=context
        )
        before = snapshot_tree(self.repo)

        # Act
        repeated = studio_manager.plan_operation(
            "migrate",
            self.repo,
            PLUGIN,
            studio_manager.new_approval_context("migrate"),
        )

        # Assert
        self.assertEqual(["ALREADY_MIGRATED"], [item.code for item in repeated.conflicts])
        self.assertFalse(
            any(
                action.kind in {"create", "merge", "update", "remove", "state-write"}
                for action in repeated.actions
            )
        )
        self.assertEqual(before, snapshot_tree(self.repo))

    def test_schema_two_repair_is_a_validated_noop_and_uninstall_is_state_only(self):
        # Arrange
        context, migration = self._approved()
        studio_manager.apply_operation(
            migration, self.repo, PLUGIN, approval_context=context
        )
        state_path = self.repo / studio_manager.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        tree_before = self._payload_snapshot()

        # Act / Assert: healthy repair has no approval and no mutation.
        repair = studio_manager.plan_operation("repair", self.repo, PLUGIN)
        self.assertFalse(repair.conflicts)
        self.assertFalse(
            any(
                action.kind in {"create", "merge", "update", "remove", "state-write"}
                for action in repair.actions
            )
        )
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(tree_before, self._payload_snapshot())

        # Act / Assert: uninstall removes only state, preserving every remnant.
        uninstall_context = studio_manager.new_approval_context("uninstall")
        uninstall = studio_manager.plan_operation(
            "uninstall", self.repo, PLUGIN, uninstall_context
        )
        self.assertEqual(
            [("state-write", studio_manager.STATE_RELATIVE_PATH)],
            [
                (action.kind, action.path)
                for action in uninstall.actions
                if action.kind in {"create", "merge", "update", "remove", "state-write"}
            ],
        )
        result = studio_manager.apply_operation(
            uninstall, self.repo, PLUGIN, approval_context=uninstall_context
        )
        self.assertEqual("committed", result.status)
        after = self._payload_snapshot()
        expected = {
            path: value
            for path, value in tree_before.items()
            if path != studio_manager.STATE_RELATIVE_PATH
        }
        self.assertEqual(expected, after)

    def test_schema_two_tampering_blocks_verify_repair_and_uninstall_without_writes(self):
        # Arrange
        context, migration = self._approved()
        studio_manager.apply_operation(
            migration, self.repo, PLUGIN, approval_context=context
        )
        state_path = self.repo / studio_manager.STATE_RELATIVE_PATH
        document = json.loads(state_path.read_text(encoding="utf-8"))
        document["preserved_paths"].append("forged/path")
        state_path.write_bytes(canonical_json(document))
        before = snapshot_tree(self.repo)

        # Act / Assert
        for operation in ("verify", "repair", "uninstall"):
            with self.subTest(operation=operation):
                approval = (
                    studio_manager.new_approval_context(operation)
                    if operation == "uninstall"
                    else None
                )
                with self.assertRaises(studio_manager.ManagerError) as caught:
                    studio_manager.plan_operation(
                        operation, self.repo, PLUGIN, approval
                    )
                self.assertEqual(
                    "INVALID_INSTALLATION_STATE", caught.exception.code
                )
                self.assertEqual(before, snapshot_tree(self.repo))

    def test_cli_migrate_emits_complete_digest_bound_plan_without_writes(self):
        # Arrange
        before = snapshot_tree(self.repo)

        # Act
        completed = run_manager("migrate", self.repo)
        document = json.loads(completed.stdout)

        # Assert
        self.assertEqual(2, completed.returncode, completed.stderr)
        self.assertEqual(
            {
                "actions",
                "approval_context",
                "approval_context_digest",
                "conflicts",
                "digest",
                "failure_phase",
                "findings",
                "next_action",
                "operation",
                "payload_digest",
                "plugin_version",
                "preserved_paths",
                "recovery",
                "shared_hashes",
                "state_digest",
                "status",
                "target_hashes",
                "target_observations",
                "target_results",
                "warnings",
                "wrote",
            },
            set(document),
        )
        self.assertEqual("migrate", document["operation"])
        self.assertEqual("awaiting-approval", document["status"])
        self.assertRegex(document["digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(923, len(document["actions"]))
        self.assertTrue(document["approval_context"])
        self.assertEqual([], document["findings"])
        self.assertEqual([], document["warnings"])
        self.assertEqual(
            sorted(
                action["path"]
                for action in document["actions"]
                if action["kind"] == "preserve"
            ),
            document["preserved_paths"],
        )
        digest_body = {
            key: document[key]
            for key in (
                "operation",
                "plugin_version",
                "payload_digest",
                "state_digest",
                "target_observations",
                "target_results",
                "actions",
                "conflicts",
                "approval_context_digest",
            )
        }
        digest_body["target_hashes"] = sorted(document["target_hashes"].items())
        digest_body["shared_hashes"] = sorted(document["shared_hashes"].items())
        self.assertEqual(document["digest"], digest_document(digest_body))
        self.assertEqual(before, snapshot_tree(self.repo))


if __name__ == "__main__":
    unittest.main()
