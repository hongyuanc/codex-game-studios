"""Contract tests for read-only, digest-bound lifecycle planning."""

from __future__ import annotations

import dataclasses
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"
sys.path.insert(0, str(PLUGIN / "scripts"))

from tests.plugin.helpers import (  # noqa: E402
    init_git_repo,
    run_manager,
    snapshot_tree,
    write_installed_fixture,
)
from tools.codex_studio.engine_pack import apply_activation, plan_activation  # noqa: E402
from models import canonical_json  # noqa: E402
from studio_manager import (  # noqa: E402
    ApprovalContext,
    ManagerError,
    load_installation_state,
    new_approval_context,
    plan_operation,
    state_with_checksum,
    write_state_document,
)
from transaction import apply_transaction  # noqa: E402


class ManagerPlanningTests(unittest.TestCase):
    """Verify deterministic classification without target-repository writes."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "repo"
        init_git_repo(self.repo)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _handcrafted_state(self, mutate) -> dict[str, object]:
        """Write manually checksummed canonical state without production serializers."""

        state_path = self.repo / ".codex/codex-game-studios/installation.json"
        document = json.loads(state_path.read_text(encoding="utf-8"))
        mutate(document)
        body = dict(document)
        body.pop("checksum", None)
        document["checksum"] = hashlib.sha256(canonical_json(body)).hexdigest()
        state_path.write_bytes(canonical_json(document))
        return document

    def _activate_godot_fixture(self) -> None:
        """Create the same valid installed activation baseline for each adversary."""

        write_installed_fixture(self.repo, PLUGIN)
        apply_activation(
            self.repo,
            plan_activation(
                self.repo, "godot", version="4.6", language="gdscript"
            ),
        )

    def _assert_update_and_repair_block_invalid_activation(self) -> None:
        """Require both planning APIs to reject an invalid activation authority."""

        for operation in ("update", "repair"):
            with self.subTest(operation=operation):
                plan = plan_operation(operation, self.repo, PLUGIN)
                self.assertEqual(
                    ["CUSTOMIZED_MANAGED_FILE"],
                    sorted({conflict.code for conflict in plan.conflicts}),
                )
                completed = run_manager(operation, self.repo)
                self.assertEqual(1, completed.returncode, completed.stderr)
                document = json.loads(completed.stdout)
                self.assertEqual("CUSTOMIZED_MANAGED_FILE", document["status"])
                self.assertFalse(document["wrote"])

    def _assert_install_projection_race_is_stale(
        self,
        mutate,
        *,
        boundary: str,
        expected_detail: str | None = None,
    ) -> None:
        """Exercise manager replanning and transaction scaffold capture together."""

        config = self.repo / ".codex/config.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_bytes(b'[user]\nfixture = "unchanged"\n')
        context = new_approval_context("install")
        approved = plan_operation("install", self.repo, PLUGIN, context)
        calls = 0
        payload_called = False

        if boundary == "lock":
            mutate()

        def replan():
            nonlocal calls
            calls += 1
            current = plan_operation("install", self.repo, PLUGIN, context)
            if (boundary == "replan" and calls == 1) or (
                boundary == "snapshot" and calls == 2
            ):
                mutate()
            return current

        def apply_payload(_action, _mutation):
            nonlocal payload_called
            payload_called = True

        def failpoint(phase: str) -> None:
            if boundary == "action" and phase == "journal-written":
                mutate()

        with self.assertRaisesRegex(ManagerError, "STALE_PLAN") as caught:
            apply_transaction(
                approved,
                self.repo,
                replan,
                apply_payload,
                lambda _root: [],
                persist_state=lambda _action, _mutation: None,
                failpoint=failpoint,
                transaction_id=context.transaction_id,
            )
        if expected_detail is not None:
            self.assertIn(expected_detail, caught.exception.detail)
        self.assertFalse(payload_called)
        self.assertEqual(
            b'[user]\nfixture = "unchanged"\n',
            config.read_bytes(),
        )

    def test_install_plan_classifies_create_adopt_and_collision(self):
        # Arrange / Act
        plan = plan_operation("install", self.repo, PLUGIN)

        # Assert
        kinds = {(action.path, action.kind) for action in plan.actions}
        self.assertIn((".agents/skills/start/SKILL.md", "create"), kinds)
        self.assertEqual([], list(plan.conflicts))

        identical = self.repo / ".agents/skills/start/SKILL.md"
        identical.parent.mkdir(parents=True)
        shutil.copyfile(
            PLUGIN / "assets/studio/.agents/skills/start/SKILL.md", identical
        )
        adopted = plan_operation("install", self.repo, PLUGIN)
        adopted_kinds = {(action.path, action.kind) for action in adopted.actions}
        self.assertIn((".agents/skills/start/SKILL.md", "adopt"), adopted_kinds)

        identical.write_text("project-owned\n", encoding="utf-8")
        collided = plan_operation("install", self.repo, PLUGIN)
        self.assertIn(
            "UNMANAGED_COLLISION", {conflict.code for conflict in collided.conflicts}
        )

    def test_uninstall_plan_digest_binds_exact_approval_context(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        first = ApprovalContext(
            "uninstall", "11111111-1111-4111-8111-111111111111",
            "2026-07-13T01:02:03Z",
        )
        changed_uuid = dataclasses.replace(
            first, transaction_id="22222222-2222-4222-8222-222222222222"
        )
        changed_time = dataclasses.replace(first, installed_at="2026-07-13T01:02:04Z")

        # Act
        plans = [
            plan_operation("uninstall", self.repo, PLUGIN, context)
            for context in (first, changed_uuid, changed_time)
        ]

        # Assert
        self.assertEqual(3, len({plan.approval_context_digest for plan in plans}))
        self.assertEqual(3, len({plan.digest for plan in plans}))

    def test_install_missing_shared_targets_are_creates(self):
        # Arrange / Act
        plan = plan_operation("install", self.repo, PLUGIN)

        # Assert
        kinds = {(action.path, action.kind) for action in plan.actions}
        for path in ("AGENTS.md", ".codex/config.toml", ".gitignore"):
            self.assertIn((path, "create"), kinds)

    def test_cli_exact_skill_command_emits_canonical_json_without_mutation(self):
        # Arrange
        command = [
            sys.executable,
            str(PLUGIN / "scripts/studio_manager.py"),
            "install",
            "--root",
            str(self.repo),
            "--format",
            "json",
        ]
        before = snapshot_tree(self.repo)

        # Act
        completed = subprocess.run(command, capture_output=True, text=True)

        # Assert
        self.assertEqual(2, completed.returncode, completed.stderr)
        document = json.loads(completed.stdout)
        self.assertEqual("install", document["operation"])
        self.assertEqual("awaiting-approval", document["status"])
        self.assertEqual(canonical_json(document).decode("utf-8"), completed.stdout)
        self.assertEqual(before, snapshot_tree(self.repo))

    def test_cli_default_and_explicit_json_formats_and_conflict_exit(self):
        # Arrange
        import studio_manager

        outputs = []
        before = snapshot_tree(self.repo)

        # Act
        for extra in ([], ["--format", "json"]):
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = studio_manager.main(
                    ["install", "--root", str(self.repo), *extra]
                )
            outputs.append((code, stream.getvalue()))

        collision = self.repo / ".agents/skills/start/SKILL.md"
        collision.parent.mkdir(parents=True)
        collision.write_text("project-owned\n", encoding="utf-8")
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            conflict_code = studio_manager.main(
                ["install", "--root", str(self.repo), "--format", "json"]
            )

        # Assert
        self.assertEqual(2, outputs[0][0])
        self.assertEqual(2, outputs[1][0])
        first_document = json.loads(outputs[0][1])
        second_document = json.loads(outputs[1][1])
        self.assertNotEqual(
            first_document["approval_context"], second_document["approval_context"]
        )
        self.assertNotEqual(first_document["digest"], second_document["digest"])
        self.assertEqual(canonical_json(first_document).decode("utf-8"), outputs[0][1])
        self.assertEqual(canonical_json(second_document).decode("utf-8"), outputs[1][1])
        self.assertEqual(1, conflict_code)
        self.assertTrue(json.loads(stream.getvalue())["conflicts"])
        self.assertEqual(before, {k: v for k, v in snapshot_tree(self.repo).items() if not k.startswith(".agents")})
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                studio_manager.main(
                    ["install", "--root", str(self.repo), "--format", "yaml"]
                )
        self.assertEqual(2, caught.exception.code)

    def test_plugin_manifest_swap_after_load_is_rejected_without_target_write(self):
        # Arrange
        import payload

        plugin = Path(self.temporary.name) / "plugin"
        shutil.copytree(PLUGIN, plugin)
        original = payload.load_manifest

        def swap_after_load(path):
            manifest = original(path)
            Path(path).write_bytes(b"{}\n")
            return manifest

        before = snapshot_tree(self.repo)

        # Act / Assert
        with mock.patch("payload.load_manifest", side_effect=swap_after_load):
            with self.assertRaisesRegex(ManagerError, "INVALID_PAYLOAD"):
                plan_operation("install", self.repo, plugin)
        self.assertEqual(before, snapshot_tree(self.repo))

    def test_shared_payload_file_swap_is_rejected_before_merge(self):
        # Arrange
        import studio_manager

        plugin = Path(self.temporary.name) / "plugin"
        shutil.copytree(PLUGIN, plugin)
        shared = plugin / "assets/studio/AGENTS.md"
        original_read = studio_manager.read_file_secure
        swapped = False

        def swap_shared(root, relative):
            nonlocal swapped
            if Path(root) == plugin / "assets/studio" and relative == "AGENTS.md" and not swapped:
                shared.write_bytes(b"swapped\n")
                swapped = True
            return original_read(root, relative)

        before = snapshot_tree(self.repo)

        # Act / Assert
        with mock.patch("studio_manager.read_file_secure", side_effect=swap_shared):
            with self.assertRaisesRegex(ManagerError, "INVALID_PAYLOAD"):
                plan_operation("install", self.repo, plugin)
        self.assertEqual(before, snapshot_tree(self.repo))

    def test_update_stops_on_customized_managed_file(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        target = self.repo / ".agents/skills/start/SKILL.md"
        target.write_text("custom", encoding="utf-8")

        # Act
        plan = plan_operation("update", self.repo, PLUGIN)

        # Assert
        conflict = next(
            item for item in plan.conflicts if item.path == ".agents/skills/start/SKILL.md"
        )
        self.assertEqual("CUSTOMIZED_MANAGED_FILE", conflict.code)
        self.assertIn(
            (".agents/skills/start/SKILL.md", "conflict"),
            {(action.path, action.kind) for action in plan.actions},
        )

    def test_update_clean_installation_preserves_owned_content(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)

        # Act
        plan = plan_operation("update", self.repo, PLUGIN)

        # Assert
        self.assertEqual([], list(plan.conflicts))
        kinds = {(action.path, action.kind) for action in plan.actions}
        self.assertIn((".agents/skills/start/SKILL.md", "preserve"), kinds)
        self.assertIn(("AGENTS.md", "preserve"), kinds)

    def test_repair_only_recreates_missing_content_for_matching_payload(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        target = self.repo / ".agents/skills/start/SKILL.md"
        target.unlink()

        # Act
        plan = plan_operation("repair", self.repo, PLUGIN)

        # Assert
        self.assertEqual([], list(plan.conflicts))
        self.assertIn(
            (".agents/skills/start/SKILL.md", "create"),
            {(action.path, action.kind) for action in plan.actions},
        )

        state_path = self.repo / ".codex/codex-game-studios/installation.json"
        state = load_installation_state(state_path)
        stale = state_with_checksum(
            dataclasses.replace(state, payload_digest="0" * 64, checksum="")
        )
        state_path.write_bytes(write_state_document(stale))
        stale_plan = plan_operation("repair", self.repo, PLUGIN)
        self.assertEqual("REPAIR_PAYLOAD_MISMATCH", stale_plan.conflicts[0].code)

    def test_uninstall_removes_only_owned_paths_and_preserves_user_content(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        user_file = self.repo / "src/player-owned.txt"
        user_file.write_text("mine\n", encoding="utf-8")

        # Act
        plan = plan_operation("uninstall", self.repo, PLUGIN)

        # Assert
        kinds = {(action.path, action.kind) for action in plan.actions}
        self.assertIn((".agents/skills/start/SKILL.md", "backup"), kinds)
        self.assertIn((".agents/skills/start/SKILL.md", "remove"), kinds)
        self.assertNotIn("src/player-owned.txt", {action.path for action in plan.actions})
        self.assertEqual(b"mine\n", user_file.read_bytes())
        self.assertNotIn(("src", "remove"), kinds)
        self.assertNotIn(("src", "backup"), kinds)

    def test_uninstall_preserves_nested_managed_directory_with_user_child(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        user_file = self.repo / ".agents/skills/start/user-notes.md"
        user_file.write_text("mine\n", encoding="utf-8")

        # Act
        plan = plan_operation("uninstall", self.repo, PLUGIN)

        # Assert
        kinds = {(action.path, action.kind) for action in plan.actions}
        self.assertIn((".agents/skills/start/SKILL.md", "remove"), kinds)
        self.assertNotIn((".agents/skills/start", "remove"), kinds)
        self.assertNotIn((".agents/skills/start", "backup"), kinds)
        self.assertEqual(b"mine\n", user_file.read_bytes())

    def test_uninstall_preserves_customized_managed_file(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        target = self.repo / ".agents/skills/start/SKILL.md"
        target.write_text("customized\n", encoding="utf-8")

        # Act
        plan = plan_operation("uninstall", self.repo, PLUGIN)

        # Assert
        self.assertIn(
            (".agents/skills/start/SKILL.md", "preserve"),
            {(action.path, action.kind) for action in plan.actions},
        )
        self.assertFalse(plan.conflicts)

    def test_uninstall_shared_toml_result_uses_changing_merge_digest(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        target = self.repo / ".codex/config.toml"
        target.write_bytes(target.read_bytes() + b"\n[project]\nname = \"mine\"\n")

        # Act
        plan = plan_operation("uninstall", self.repo, PLUGIN)

        # Assert
        merge = next(
            action for action in plan.actions
            if action.path == ".codex/config.toml" and action.kind == "merge"
        )
        result = next(
            item for item in plan.target_results if item.path == ".codex/config.toml"
        )
        self.assertEqual(merge.after_hash, result.digest)
        self.assertNotEqual(merge.before_hash, result.digest)

    def test_uninstall_managed_block_result_uses_changing_merge_digest(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        target = self.repo / "AGENTS.md"
        target.write_bytes(b"# Project instructions\n\n" + target.read_bytes())

        # Act
        plan = plan_operation("uninstall", self.repo, PLUGIN)

        # Assert
        merge = next(
            action for action in plan.actions
            if action.path == "AGENTS.md" and action.kind == "merge"
        )
        result = next(item for item in plan.target_results if item.path == "AGENTS.md")
        self.assertEqual(merge.after_hash, result.digest)
        self.assertNotEqual(merge.before_hash, result.digest)

    def test_plan_digest_changes_when_target_changes(self):
        # Arrange
        first = plan_operation("install", self.repo, PLUGIN)
        (self.repo / "AGENTS.md").write_text("changed\n", encoding="utf-8")

        # Act
        second = plan_operation("install", self.repo, PLUGIN)

        # Assert
        self.assertNotEqual(first.digest, second.digest)

    def test_fresh_install_replan_projects_only_transaction_control_paths(self):
        # Arrange
        approved = plan_operation("install", self.repo, PLUGIN)
        from transaction import RepositoryLock

        # Act
        with RepositoryLock(self.repo, timeout=0.1):
            replanned = plan_operation("install", self.repo, PLUGIN)

        # Assert
        self.assertEqual(approved, replanned)

    def test_fresh_install_replan_keeps_unknown_control_sibling_digest_bound(self):
        # Arrange
        approved = plan_operation("install", self.repo, PLUGIN)
        control = self.repo / ".codex/codex-game-studios"
        control.mkdir(parents=True)
        (control / "manager.lock").write_bytes(b"\0")

        # Act
        internal_only = plan_operation("install", self.repo, PLUGIN)
        (control / "unexpected.txt").write_bytes(b"user-owned\n")
        with_unknown = plan_operation("install", self.repo, PLUGIN)

        # Assert
        self.assertEqual(approved, internal_only)
        self.assertNotEqual(approved.digest, with_unknown.digest)

    def test_fresh_install_replan_keeps_nested_recovery_content_digest_bound(self):
        # Arrange
        approved = plan_operation("install", self.repo, PLUGIN)
        control = self.repo / ".codex/codex-game-studios"
        control.mkdir(parents=True)
        (control / "manager.lock").write_bytes(b"\0")
        internal_only = plan_operation("install", self.repo, PLUGIN)

        # Act
        recovery = control / "recovery/current/snapshots"
        recovery.mkdir(parents=True)
        (recovery / "000000.bin").write_bytes(b"unknown-or-prior")
        with_recovery = plan_operation("install", self.repo, PLUGIN)
        (recovery / "000000.bin").write_bytes(b"changed-prior")
        changed_nested = plan_operation("install", self.repo, PLUGIN)

        # Assert
        self.assertEqual(approved, internal_only)
        self.assertNotEqual(approved.digest, with_recovery.digest)
        self.assertNotEqual(with_recovery.digest, changed_nested.digest)

    def test_fresh_install_replan_does_not_project_malformed_internal_types(self):
        # Arrange
        approved = plan_operation("install", self.repo, PLUGIN)
        control = self.repo / ".codex/codex-game-studios"
        control.mkdir(parents=True)
        (control / "manager.lock").mkdir()

        # Act
        malformed = plan_operation("install", self.repo, PLUGIN)

        # Assert
        self.assertNotEqual(approved.digest, malformed.digest)

    def test_install_projection_rejects_unknown_control_sibling_at_lock_boundary(self):
        # Arrange
        sibling = self.repo / ".codex/codex-game-studios/unexpected.txt"

        def mutate() -> None:
            sibling.parent.mkdir(parents=True, exist_ok=True)
            sibling.write_bytes(b"unknown\n")

        # Act / Assert
        self._assert_install_projection_race_is_stale(mutate, boundary="lock")

    def test_install_projection_rejects_wrong_typed_internal_at_replan_boundary(self):
        # Arrange
        recovery = self.repo / ".codex/codex-game-studios/recovery"

        def mutate() -> None:
            recovery.write_bytes(b"not-a-directory\n")

        # Act / Assert
        self._assert_install_projection_race_is_stale(mutate, boundary="replan")

    def test_install_projection_rejects_prior_recovery_byte_race_at_snapshot_boundary(self):
        # Arrange
        nested = self.repo / ".codex/codex-game-studios/recovery/prior/snapshots/000000.bin"
        nested.parent.mkdir(parents=True)
        nested.write_bytes(b"approved\n")

        # Act / Assert
        self._assert_install_projection_race_is_stale(
            lambda: nested.write_bytes(b"raced\n"), boundary="snapshot"
        )

    def test_install_projection_rejects_prior_recovery_type_race_at_snapshot_boundary(self):
        # Arrange
        nested = self.repo / ".codex/codex-game-studios/recovery/prior/snapshots/000000.bin"
        nested.parent.mkdir(parents=True)
        nested.write_bytes(b"approved\n")

        def mutate() -> None:
            nested.unlink()
            nested.mkdir()

        # Act / Assert
        self._assert_install_projection_race_is_stale(mutate, boundary="snapshot")

    def test_install_projection_rejects_prior_recovery_type_race_at_action_boundary(self):
        # Arrange
        nested = self.repo / ".codex/codex-game-studios/recovery/prior/snapshots/000000.bin"
        nested.parent.mkdir(parents=True)
        nested.write_bytes(b"approved\n")

        def mutate() -> None:
            nested.unlink()
            nested.mkdir()

        # Act / Assert
        self._assert_install_projection_race_is_stale(mutate, boundary="action")

    def test_install_projection_rejects_whole_control_replacement_at_action_boundary(self):
        # Arrange
        control = self.repo / ".codex/codex-game-studios"

        def mutate() -> None:
            replacement = self.repo / ".codex/replacement-control"
            shutil.copytree(control, replacement)
            displaced = self.repo / "displaced-control"
            control.rename(displaced)
            replacement.rename(control)

        # Act / Assert
        self._assert_install_projection_race_is_stale(
            mutate,
            boundary="action",
            expected_detail="manager directory identity changed",
        )

    def test_install_projection_rejects_whole_recovery_replacement_at_action_boundary(self):
        # Arrange
        recovery = self.repo / ".codex/codex-game-studios/recovery"

        def mutate() -> None:
            replacement = recovery.with_name("replacement-recovery")
            shutil.copytree(recovery, replacement)
            displaced = self.repo / "displaced-recovery"
            recovery.rename(displaced)
            replacement.rename(recovery)

        # Act / Assert
        self._assert_install_projection_race_is_stale(
            mutate,
            boundary="action",
            expected_detail="recovery directory identity changed",
        )

    def test_installed_control_directory_with_state_and_legal_is_not_projected_away(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        before = plan_operation("update", self.repo, PLUGIN)
        control = self.repo / ".codex/codex-game-studios"
        (control / "manager.lock").write_bytes(b"\0")

        # Act
        after = plan_operation("update", self.repo, PLUGIN)

        # Assert
        self.assertEqual(before, after)
        self.assertIn(
            (".codex/codex-game-studios/legal", "preserve"),
            {(action.path, action.kind) for action in after.actions},
        )

    def test_update_and_repair_reject_activated_studio_non_engine_authority_change(self):
        # Arrange
        self._activate_godot_fixture()
        studio = self.repo / ".codex/studio.toml"
        studio.write_text(
            studio.read_text(encoding="utf-8").replace(
                'review_mode = "phase-gated"', 'review_mode = "solo"'
            ),
            encoding="utf-8",
        )

        # Act / Assert
        self._assert_update_and_repair_block_invalid_activation()

    def test_update_and_repair_reject_altered_active_profile(self):
        # Arrange
        self._activate_godot_fixture()
        profile = self.repo / ".codex/agents/godot-specialist.toml"
        profile.write_bytes(profile.read_bytes() + b"# forged\n")

        # Act / Assert
        self._assert_update_and_repair_block_invalid_activation()

    def test_update_and_repair_reject_missing_active_profile(self):
        # Arrange
        self._activate_godot_fixture()
        (self.repo / ".codex/agents/godot-specialist.toml").unlink()

        # Act / Assert
        self._assert_update_and_repair_block_invalid_activation()

    def test_update_and_repair_reject_forged_active_manifest(self):
        # Arrange
        self._activate_godot_fixture()
        manifest = self.repo / ".codex/active-engine.json"
        document = json.loads(manifest.read_text(encoding="utf-8"))
        document["generated"]["godot-specialist.toml"] = "f" * 64
        manifest.write_bytes(canonical_json(document))

        # Act / Assert
        self._assert_update_and_repair_block_invalid_activation()

    def test_update_and_repair_reject_damaged_inactive_source_pack(self):
        # Arrange
        self._activate_godot_fixture()
        source = self.repo / ".codex/agent-packs/unity/unity-specialist.toml"
        source.write_bytes(source.read_bytes() + b"# damaged\n")

        # Act / Assert
        self._assert_update_and_repair_block_invalid_activation()

    def test_plan_digest_changes_when_user_child_is_added_to_managed_directory(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        first = plan_operation("update", self.repo, PLUGIN)
        user_file = self.repo / "src/player-owned.txt"
        user_file.write_text("mine\n", encoding="utf-8")

        # Act
        second = plan_operation("update", self.repo, PLUGIN)

        # Assert
        self.assertNotEqual(first.digest, second.digest)

    def test_directory_observation_is_immediate_and_rejects_immediate_links(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        deep = self.repo / "src/user/deep"
        deep.mkdir(parents=True)
        (deep / "outside-link").symlink_to(Path(self.temporary.name) / "outside")

        # Act
        first = plan_operation("update", self.repo, PLUGIN)
        (self.repo / "src/immediate.txt").write_text("one\n", encoding="utf-8")
        second = plan_operation("update", self.repo, PLUGIN)

        # Assert
        self.assertNotEqual(first.digest, second.digest)
        (self.repo / "src/immediate-link").symlink_to(Path(self.temporary.name) / "outside")
        with self.assertRaisesRegex(ManagerError, "UNSAFE_PATH"):
            plan_operation("update", self.repo, PLUGIN)

    @unittest.skipUnless(
        os.name == "posix" and hasattr(os, "mkfifo"),
        "POSIX FIFO support is required",
    )
    def test_directory_observation_rejects_fifo_without_blocking_or_writes(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        fifo = self.repo / "src/immediate-fifo"
        os.mkfifo(fifo)
        before = snapshot_tree(self.repo)
        command = [
            sys.executable,
            str(PLUGIN / "scripts/studio_manager.py"),
            "update",
            "--root",
            str(self.repo),
            "--format",
            "json",
        ]

        # Act
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=2.5,
        )

        # Assert
        self.assertEqual(1, completed.returncode)
        self.assertEqual("UNSAFE_PATH", json.loads(completed.stdout)["status"])
        self.assertEqual(before, snapshot_tree(self.repo))

    def test_plan_is_deterministic_and_binds_ordered_actions(self):
        # Arrange / Act
        first = plan_operation("install", self.repo, PLUGIN)
        second = plan_operation("install", self.repo, PLUGIN)

        # Assert
        self.assertEqual(first, second)
        self.assertRegex(first.digest, r"^[0-9a-f]{64}$")

    def test_uninstall_removes_owned_files_and_empty_directory_containers(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)

        # Act
        plan = plan_operation("uninstall", self.repo, PLUGIN)

        # Assert
        kinds = {(action.path, action.kind) for action in plan.actions}
        self.assertIn((".agents/skills/start/SKILL.md", "remove"), kinds)
        self.assertIn((".agents/skills/start", "remove"), kinds)

    def test_uninstall_preserves_directory_with_unrelated_child(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        unrelated = self.repo / ".agents/skills/start/project.txt"
        unrelated.write_text("mine\n", encoding="utf-8")

        # Act
        plan = plan_operation("uninstall", self.repo, PLUGIN)

        # Assert
        kinds = {(action.path, action.kind) for action in plan.actions}
        self.assertIn((".agents/skills/start", "preserve"), kinds)
        self.assertNotIn((".agents/skills/start", "remove"), kinds)

    def test_uninstall_customized_toml_is_nonblocking_and_malformed_bytes_are_stable(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        target = self.repo / ".codex/config.toml"
        target.write_bytes(b"\xff\n")

        # Act
        plan = plan_operation("uninstall", self.repo, PLUGIN)

        # Assert
        self.assertFalse(plan.conflicts)
        action = next(item for item in plan.actions if item.path == ".codex/config.toml")
        self.assertEqual("preserve", action.kind)

    def test_uninstall_customized_legal_notice_retains_complete_legal_pair(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        attribution = self.repo / ".codex/codex-game-studios/legal/ATTRIBUTION.md"
        attribution.write_bytes(attribution.read_bytes() + b"\ncustom note\n")

        # Act
        plan = plan_operation("uninstall", self.repo, PLUGIN)

        # Assert
        legal_actions = {
            item.path: item.kind for item in plan.actions
            if item.path.startswith(".codex/codex-game-studios/legal/")
            and item.kind != "backup"
        }
        self.assertEqual("preserve", legal_actions[attribution.relative_to(self.repo).as_posix()])
        self.assertEqual(
            "preserve", legal_actions[".codex/codex-game-studios/legal/LICENSE"]
        )
        self.assertFalse(plan.conflicts)

    def test_verify_reports_embedded_payload_staleness(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        state_path = self.repo / ".codex/codex-game-studios/installation.json"
        state = load_installation_state(state_path)
        stale = state_with_checksum(
            dataclasses.replace(state, payload_digest="0" * 64, checksum="")
        )
        state_path.write_bytes(write_state_document(stale))

        # Act
        plan = plan_operation("verify", self.repo, PLUGIN)

        # Assert
        self.assertIn("STALE_INSTALLATION", {item.code for item in plan.conflicts})

    def test_version_only_mismatch_with_current_digest_is_invalid_state(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        self._handcrafted_state(
            lambda document: document.__setitem__("plugin_version", "9.9.9")
        )

        # Act / Assert
        for operation in ("update", "verify", "uninstall"):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(ManagerError, "INVALID_INSTALLATION_STATE"):
                    plan_operation(operation, self.repo, PLUGIN)

    def test_historical_mixed_state_never_mutates_state_only_paths(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        forged = self.repo / "zz-historical-remnant.txt"
        forged.write_text("historical\n", encoding="utf-8")

        def historical(document):
            document["payload_digest"] = "1" * 64
            document["managed_paths"].append(
                {
                    "path": "zz-historical-remnant.txt",
                    "installed_hash": hashlib.sha256(b"historical\n").hexdigest(),
                    "ownership": "dedicated",
                    "merge": None,
                    "block_hash": None,
                }
            )

        self._handcrafted_state(historical)

        # Act / Assert
        for operation in ("update", "verify", "uninstall"):
            with self.subTest(operation=operation):
                plan = plan_operation(operation, self.repo, PLUGIN)
                remnant_actions = [
                    action
                    for action in plan.actions
                    if action.path == "zz-historical-remnant.txt"
                ]
                self.assertEqual(["preserve"], [item.kind for item in remnant_actions])
                self.assertIn(
                    "STALE_MANUAL_REMNANT", {item.code for item in plan.conflicts}
                )
                self.assertEqual(b"historical\n", forged.read_bytes())

    def test_shared_classifier_cannot_remove_without_current_manifest_entry(self):
        # Arrange
        import studio_manager

        write_installed_fixture(self.repo, PLUGIN)
        state = load_installation_state(
            self.repo / ".codex/codex-game-studios/installation.json"
        )
        record = next(item for item in state.managed_paths if item.path == "AGENTS.md")
        content = (self.repo / "AGENTS.md").read_bytes()
        observed = studio_manager._Observed(
            "file", hashlib.sha256(content).hexdigest(), content
        )

        # Act
        actions, conflicts = studio_manager._classify_shared(
            "uninstall", None, record, observed, None, state
        )

        # Assert
        self.assertEqual(["preserve"], [item.kind for item in actions])
        self.assertIn("STALE_MANUAL_REMNANT", {item.code for item in conflicts})

    def test_digest_only_mismatch_can_classify_current_manifest_paths(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        self._handcrafted_state(
            lambda document: document.__setitem__("payload_digest", "2" * 64)
        )

        # Act
        for operation in ("update", "verify", "uninstall"):
            with self.subTest(operation=operation):
                plan = plan_operation(operation, self.repo, PLUGIN)
                self.assertIn(
                    ".agents/skills/start/SKILL.md",
                    {action.path for action in plan.actions},
                )

    def test_historical_mixed_ownership_cannot_reclassify_current_shared_path(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)

        def mixed(document):
            document["payload_digest"] = "4" * 64
            record = next(
                item for item in document["managed_paths"] if item["path"] == "AGENTS.md"
            )
            record["ownership"] = "dedicated"
            record["merge"] = None
            record["block_hash"] = None
            document["decisions"] = [
                decision
                for decision in document["decisions"]
                if decision["path"] != "AGENTS.md"
            ]

        self._handcrafted_state(mixed)

        # Act / Assert
        for operation in ("update", "verify", "uninstall"):
            with self.subTest(operation=operation):
                plan = plan_operation(operation, self.repo, PLUGIN)
                agents_actions = [
                    action for action in plan.actions if action.path == "AGENTS.md"
                ]
                self.assertEqual(["preserve"], [item.kind for item in agents_actions])
                self.assertIn(
                    "STALE_MANUAL_REMNANT", {item.code for item in plan.conflicts}
                )

    def test_current_digest_forged_extra_path_is_invalid_for_all_operations(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        self._handcrafted_state(
            lambda document: document["managed_paths"].append(
                {
                    "path": "zz-forged.txt",
                    "installed_hash": "0" * 64,
                    "ownership": "dedicated",
                    "merge": None,
                    "block_hash": None,
                }
            )
        )

        # Act / Assert
        for operation in ("update", "verify", "uninstall"):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(ManagerError, "INVALID_INSTALLATION_STATE"):
                    plan_operation(operation, self.repo, PLUGIN)

    def test_verify_historical_state_has_no_mutating_actions(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        self._handcrafted_state(
            lambda document: document.__setitem__("payload_digest", "3" * 64)
        )

        # Act
        plan = plan_operation("verify", self.repo, PLUGIN)

        # Assert
        self.assertTrue(
            {action.kind for action in plan.actions}.issubset(
                {"preserve", "adopt", "diagnostic"}
            )
        )

    def test_planning_all_operations_is_byte_for_byte_read_only(self):
        # Arrange
        before = snapshot_tree(self.repo)

        # Act / Assert
        plan_operation("install", self.repo, PLUGIN)
        self.assertEqual(before, snapshot_tree(self.repo))
        self.assertFalse((self.repo / ".codex/codex-game-studios").exists())

        write_installed_fixture(self.repo, PLUGIN)
        for operation in ("update", "verify", "repair", "uninstall"):
            with self.subTest(operation=operation):
                installed_before = snapshot_tree(self.repo)
                plan_operation(operation, self.repo, PLUGIN)
                self.assertEqual(installed_before, snapshot_tree(self.repo))
                self.assertFalse(
                    (self.repo / ".codex/codex-game-studios/manager.lock").exists()
                )

    def test_invalid_installation_state_is_rejected_before_classification(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        state_path = self.repo / ".codex/codex-game-studios/installation.json"
        valid = json.loads(state_path.read_text(encoding="utf-8"))
        mutations = {
            "extra": lambda value: value.__setitem__("future", True),
            "future": lambda value: value.__setitem__("schema_version", 2),
            "checksum": lambda value: value.__setitem__("checksum", "0" * 64),
            "malformed path": lambda value: value["managed_paths"][0].__setitem__("path", "../bad"),
            "forged ownership path": lambda value: value["managed_paths"].append(
                {
                    "path": "zz-forged.txt",
                    "installed_hash": "0" * 64,
                    "ownership": "dedicated",
                    "merge": None,
                    "block_hash": None,
                }
            ),
        }

        # Act / Assert
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                value = json.loads(json.dumps(valid))
                mutate(value)
                if label in {"future", "malformed path", "forged ownership path"}:
                    body = dict(value)
                    body.pop("checksum", None)
                    value["checksum"] = hashlib.sha256(canonical_json(body)).hexdigest()
                state_path.write_bytes(canonical_json(value))
                before = snapshot_tree(self.repo)
                with self.assertRaisesRegex(ManagerError, "INVALID_INSTALLATION_STATE"):
                    plan_operation("update", self.repo, PLUGIN)
                self.assertEqual(before, snapshot_tree(self.repo))

        state_path.write_bytes(b"not json\n")
        with self.assertRaisesRegex(ManagerError, "INVALID_INSTALLATION_STATE"):
            plan_operation("update", self.repo, PLUGIN)

    def test_handcrafted_state_rejects_aliases_controls_and_duplicate_decisions(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        state_path = self.repo / ".codex/codex-game-studios/installation.json"
        original = state_path.read_bytes()

        def add_path(document, path):
            document["managed_paths"].append(
                {
                    "path": path,
                    "installed_hash": "0" * 64,
                    "ownership": "dedicated",
                    "merge": None,
                    "block_hash": None,
                }
            )
            document["managed_paths"].sort(key=lambda item: item["path"])

        def add_decisions(document, decisions):
            document["decisions"].extend(decisions)
            document["decisions"].sort(key=canonical_json)

        mutations = {
            "casefold managed alias": lambda document: add_path(document, "SRC"),
            "control character": lambda document: add_path(document, "bad/\u0001name"),
            "C1 control character": lambda document: add_path(
                document, "bad/\u0085name"
            ),
            "unicode normalization alias": lambda document: add_path(
                document, "cafe\u0301.txt"
            ),
            "Windows reserved alias": lambda document: add_path(document, "aux.txt"),
            "Windows trailing dot alias": lambda document: add_path(
                document, "trailing."
            ),
            "Windows colon alias": lambda document: add_path(document, "stream:name"),
            "duplicate decision": lambda document: document["decisions"].append(
                dict(document["decisions"][0])
            ),
            "casefold decision alias": lambda document: add_decisions(
                document,
                (
                    {
                        "kind": "preserved-collision",
                        "path": "manual-remnant.txt",
                        "reason": "historical-remnant",
                        "target_hash": None,
                    },
                    {
                        "kind": "preserved-collision",
                        "path": "MANUAL-REMNANT.TXT",
                        "reason": "historical-remnant",
                        "target_hash": None,
                    },
                ),
            ),
        }

        # Act / Assert
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                state_path.write_bytes(original)
                self._handcrafted_state(mutate)
                with self.assertRaisesRegex(ManagerError, "INVALID_INSTALLATION_STATE"):
                    load_installation_state(state_path)

    def test_handcrafted_decision_schema_accepts_only_exact_v1_contracts(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        state_path = self.repo / ".codex/codex-game-studios/installation.json"
        original = json.loads(state_path.read_text(encoding="utf-8"))

        valid_collision = {
            "kind": "preserved-collision",
            "path": "manual-remnant.txt",
            "reason": "historical-remnant",
            "target_hash": None,
        }
        invalid = {
            "unknown kind": {"kind": "future", "path": "future.txt", "detail": "x"},
            "missing field": {"kind": "preserved-collision", "path": "missing.txt"},
            "extra field": {**valid_collision, "detail": {"arbitrary": [1, 2]}},
            "bad reason": {**valid_collision, "reason": "overwrite"},
        }

        # Act / Assert
        accepted = json.loads(json.dumps(original))
        accepted["decisions"].append(valid_collision)
        accepted["decisions"].sort(key=canonical_json)
        body = dict(accepted)
        body.pop("checksum")
        accepted["checksum"] = hashlib.sha256(canonical_json(body)).hexdigest()
        state_path.write_bytes(canonical_json(accepted))
        load_installation_state(state_path)

        for label, decision in invalid.items():
            with self.subTest(label=label):
                document = json.loads(json.dumps(original))
                document["decisions"].append(decision)
                document["decisions"].sort(key=canonical_json)
                body = dict(document)
                body.pop("checksum")
                document["checksum"] = hashlib.sha256(canonical_json(body)).hexdigest()
                state_path.write_bytes(canonical_json(document))
                with self.assertRaisesRegex(ManagerError, "INVALID_INSTALLATION_STATE"):
                    load_installation_state(state_path)

    def test_root_replacement_during_observation_is_rejected(self):
        # Arrange
        original_observe = sys.modules["studio_manager"]._observe
        renamed = self.repo.with_name("repo-original")
        replaced = False

        def replace_root(root, relative):
            nonlocal replaced
            result = original_observe(root, relative)
            if not replaced:
                self.repo.rename(renamed)
                self.repo.mkdir()
                replaced = True
            return result

        # Act / Assert
        with mock.patch("studio_manager._observe", side_effect=replace_root):
            with self.assertRaisesRegex(ManagerError, "UNSAFE_PATH"):
                plan_operation("install", self.repo, PLUGIN)

    def test_pinned_root_windows_contract_denies_delete_share(self):
        # Arrange
        import safe_fs

        class FakeApi:
            def __init__(self):
                self.calls = []
                self.closed = []

            def create_file(self, path, access, share, disposition, flags):
                self.calls.append((path, access, share, disposition, flags))
                return len(self.calls)

            def attributes(self, handle):
                return safe_fs.FILE_ATTRIBUTE_DIRECTORY, 0

            def final_path(self, handle):
                return r"C:\repo"

            def close(self, handle):
                self.closed.append(handle)

        api = FakeApi()
        windows_root = Path(r"C:\repo")

        # Act
        with mock.patch("safe_fs._is_windows", return_value=True), mock.patch(
            "safe_fs._WindowsApi", return_value=api
        ):
            from safe_fs import pin_root

            with pin_root(windows_root) as pinned:
                pinned.verify()

        # Assert
        self.assertGreaterEqual(len(api.calls), 2)
        self.assertTrue(
            all(call[2] & safe_fs.FILE_SHARE_DELETE == 0 for call in api.calls)
        )

    def test_git_root_must_exactly_match_requested_root(self):
        # Arrange
        child = self.repo / "child"
        child.mkdir()
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()

        # Act / Assert
        with self.assertRaisesRegex(ManagerError, "UNSAFE_PATH"):
            plan_operation("install", child, PLUGIN)
        with self.assertRaisesRegex(ManagerError, "UNSUPPORTED_ENVIRONMENT"):
            plan_operation("install", outside, PLUGIN)

    def test_unknown_operation_is_rejected(self):
        # Arrange / Act / Assert
        with self.assertRaisesRegex(ManagerError, "UNSUPPORTED_ENVIRONMENT"):
            plan_operation("upgrade", self.repo, PLUGIN)


if __name__ == "__main__":
    unittest.main()
