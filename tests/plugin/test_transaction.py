"""Recovery transaction, locking, rollback, and journal contract tests."""

from __future__ import annotations

import dataclasses
import contextlib
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
import types
import unittest
from unittest import mock
import uuid
import shutil


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"
sys.path.insert(0, str(PLUGIN / "scripts"))

from models import (  # noqa: E402
    Action,
    OperationPlan,
    PayloadError,
    TargetObservation,
    plan_with_digest,
    validate_operation_plan_digest,
)
from studio_manager import ManagerError  # noqa: E402
from tests.plugin.helpers import init_git_repo, snapshot_tree  # noqa: E402
from transaction import (  # noqa: E402
    RecoveryAuthority,
    RecoveryJournal,
    RepositoryLock,
    apply_transaction,
    secure_root_identity,
)


class InjectedFailure(RuntimeError):
    """Deterministic test-only transaction interruption."""


class TransactionTests(unittest.TestCase):
    """Verify every transaction exit is committed or exactly recovered."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "repo"
        init_git_repo(self.repo)
        (self.repo / "managed.txt").write_bytes(b"before\n")
        control = self.repo / ".codex/codex-game-studios"
        control.mkdir(parents=True)
        (control / "manager.lock").write_bytes(b"\0")
        self._approved = self._plan()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _plan(self) -> OperationPlan:
        return plan_with_digest(OperationPlan(
            operation="update",
            plugin_version="1.0.0",
            payload_digest="b" * 64,
            state_digest=None,
            actions=(
                Action(
                    "update",
                    "managed.txt",
                    hashlib.sha256(b"before\n").hexdigest(),
                    hashlib.sha256(b"after\n").hexdigest(),
                    "replace managed fixture",
                ),
                Action(
                    "create",
                    "nested",
                    None,
                    None,
                    "create managed fixture directory",
                ),
                Action(
                    "create",
                    "nested/created.txt",
                    None,
                    hashlib.sha256(b"created\n").hexdigest(),
                    "create managed fixture",
                ),
            ),
            conflicts=(),
            digest="",
            target_observations=(
                TargetObservation(
                    "managed.txt",
                    "file",
                    0o644,
                    hashlib.sha256(b"before\n").hexdigest(),
                ),
                TargetObservation("nested", "missing", None, None),
                TargetObservation("nested/created.txt", "missing", None, None),
            ),
            target_results=(
                TargetObservation(
                    "managed.txt",
                    "file",
                    0o640,
                    hashlib.sha256(b"after\n").hexdigest(),
                ),
                TargetObservation(
                    "nested",
                    "directory",
                    0o755,
                    hashlib.sha256(b'{"entries":[]}\n').hexdigest(),
                ),
                TargetObservation(
                    "nested/created.txt",
                    "file",
                    0o600,
                    hashlib.sha256(b"created\n").hexdigest(),
                ),
            ),
        ))

    def _replan(self) -> OperationPlan:
        return self._approved

    def _plan_with_actions(self, actions: tuple[Action, ...]) -> OperationPlan:
        base = {item.path: item for item in self._approved.target_observations}
        observations: list[TargetObservation] = []
        results: list[TargetObservation] = []
        for action in sorted(actions, key=lambda item: item.path):
            if action.kind not in {"create", "merge", "update", "remove", "state-write"}:
                continue
            if action.path in base:
                observations.append(base[action.path])
            else:
                path = self.repo / action.path
                if not path.exists():
                    observations.append(TargetObservation(action.path, "missing", None, None))
                elif path.is_dir():
                    import safe_fs

                    observed = safe_fs.observe_secure(self.repo, action.path)
                    observations.append(
                        TargetObservation(action.path, "directory", observed.mode, observed.digest)
                    )
                else:
                    content = path.read_bytes()
                    observations.append(
                        TargetObservation(
                            action.path,
                            "file",
                            path.stat().st_mode & 0o7777,
                            hashlib.sha256(content).hexdigest(),
                        )
                    )
            if action.kind == "remove" or (
                action.kind == "state-write" and action.after_hash is None
            ):
                results.append(TargetObservation(action.path, "missing", None, None))
            elif action.after_hash is None:
                import safe_fs

                mode = 0o750 if action.path == "only-directory" else 0o755
                results.append(
                    TargetObservation(
                        action.path,
                        "directory",
                        mode,
                        safe_fs.digest_document({"entries": []}),
                    )
                )
            else:
                mode = 0o640 if action.path == "managed.txt" else 0o600
                results.append(
                    TargetObservation(
                        action.path,
                        "file",
                        mode,
                        action.after_hash,
                    )
                )
        return plan_with_digest(
            dataclasses.replace(
                self._approved,
                actions=actions,
                target_observations=tuple(observations),
                target_results=tuple(results),
            )
        )

    def _apply_action(self, action: Action, mutation) -> None:
        if action.path == "managed.txt":
            mutation.replace_file(action.path, b"after\n", 0o640)
        elif action.path == "nested":
            mutation.make_directory(action.path, 0o755)
        elif action.path == "nested/created.txt":
            mutation.replace_file(action.path, b"created\n", 0o600)

    @staticmethod
    def _validate(_root: Path) -> list[str]:
        return []

    def _recovery_entries(self) -> list[Path]:
        recovery = self.repo / ".codex/codex-game-studios/recovery"
        return [] if not recovery.exists() else list(recovery.iterdir())

    def _payload_snapshot(self) -> dict[str, tuple[str, int, str | None]]:
        return {
            path: value
            for path, value in snapshot_tree(self.repo).items()
            if not path.startswith(".codex/codex-game-studios/recovery")
        }

    def _terminal_phases(self) -> list[str]:
        return sorted(
            json.loads((generation / "journal.json").read_text(encoding="utf-8"))["phase"]
            for generation in self._recovery_entries()
        )

    def _load_authority(
        self, generation: Path, plan: OperationPlan | None = None
    ) -> RecoveryAuthority:
        approved = self._approved if plan is None else plan
        changing = tuple(
            action
            for action in approved.actions
            if action.kind in {"create", "merge", "update", "remove"}
        ) + tuple(action for action in approved.actions if action.kind == "state-write")
        return RecoveryAuthority.load(
            generation / "authority.json",
            expected_root_identity=secure_root_identity(self.repo),
            expected_transaction_id=generation.name,
            approved_plan=approved,
        )

    def test_transaction_target_change_after_approval_rejects_stale_plan(self):
        # Arrange
        plan = self._approved
        (self.repo / "managed.txt").write_bytes(b"raced\n")

        # Act / Assert
        with self.assertRaisesRegex(ManagerError, "STALE_PLAN"):
            apply_transaction(
                plan,
                self.repo,
                lambda: dataclasses.replace(plan, digest="c" * 64),
                self._apply_action,
                self._validate,
            )
        self.assertEqual([], self._recovery_entries())

    def test_transaction_rejects_stale_public_state_digest_before_lock(self):
        forged = dataclasses.replace(self._approved, state_digest="f" * 64)

        with self.assertRaisesRegex(ManagerError, "STALE_PLAN"):
            apply_transaction(
                forged, self.repo, lambda: forged, self._apply_action, self._validate
            )

        self.assertEqual([], self._recovery_entries())

    def test_plan_projection_rejects_duplicate_and_unicode_alias_paths(self):
        duplicate_different = dataclasses.replace(
            self._approved,
            target_hashes=(("a", None), ("a", "f" * 64)),
        )
        duplicate_same = dataclasses.replace(
            self._approved,
            target_hashes=(("a", None), ("a", None)),
        )
        alias = dataclasses.replace(
            self._approved,
            target_hashes=(("A", None), ("a", None)),
        )
        unsorted = dataclasses.replace(
            self._approved,
            target_hashes=(("b", None), ("a", None)),
        )
        non_normalized = dataclasses.replace(
            self._approved,
            target_hashes=(("cafe\u0301", None),),
        )

        for forged in (
            duplicate_different,
            duplicate_same,
            alias,
            unsorted,
            non_normalized,
        ):
            with self.subTest(forged=forged.target_hashes):
                with self.assertRaisesRegex(PayloadError, "projection"):
                    validate_operation_plan_digest(forged)

    def test_transaction_rejects_unknown_transaction_created_control_sibling(self):
        injected = False

        def inject(phase: str) -> None:
            nonlocal injected
            if phase == "journal-written" and not injected:
                injected = True
                (self.repo / ".codex/unapproved").write_bytes(b"race\n")

        with self.assertRaisesRegex(ManagerError, "STALE_PLAN"):
            apply_transaction(
                self._approved,
                self.repo,
                self._replan,
                self._apply_action,
                self._validate,
                failpoint=inject,
            )

        self.assertEqual(b"before\n", (self.repo / "managed.txt").read_bytes())

    def test_transaction_rejects_raced_nested_byte_in_approved_prior_generation(self):
        apply_transaction(
            self._approved, self.repo, self._replan, self._apply_action, self._validate
        )
        prior = self._recovery_entries()[0]
        (self.repo / "managed.txt").write_bytes(b"before\n")
        os.chmod(self.repo / "managed.txt", 0o644)
        import shutil

        shutil.rmtree(self.repo / "nested")
        injected = False

        def inject(phase: str) -> None:
            nonlocal injected
            if phase == "journal-written" and not injected:
                injected = True
                (prior / "unexpected.bin").write_bytes(b"race\n")

        with self.assertRaisesRegex(ManagerError, "STALE_PLAN"):
            apply_transaction(
                self._approved,
                self.repo,
                self._replan,
                self._apply_action,
                self._validate,
                failpoint=inject,
            )

        self.assertTrue(injected)

    def test_transaction_rejects_existing_control_sibling_byte_change_after_replan(self):
        sibling = self.repo / ".codex/codex-game-studios/ordinary.txt"
        sibling.write_bytes(b"approved\n")
        injected = False

        def inject(phase: str) -> None:
            nonlocal injected
            if phase == "journal-written" and not injected:
                injected = True
                sibling.write_bytes(b"changed-after-replan\n")

        with self.assertRaisesRegex(ManagerError, "STALE_PLAN"):
            apply_transaction(
                self._approved,
                self.repo,
                self._replan,
                self._apply_action,
                self._validate,
                failpoint=inject,
            )

        self.assertTrue(injected)

    def _assert_action_started_directory_replacement_is_stale(
        self, target: str
    ) -> None:
        """Replace an identity-bound transaction directory after action-started."""

        import transaction

        original_write = transaction._write_journal_anchored
        replaced = False
        payload_called = False

        def replace_after_write(filesystem, relative, journal):
            nonlocal replaced
            written = original_write(filesystem, relative, journal)
            if journal.phase == "action-started" and not replaced:
                replaced = True
                generation = self.repo / ".codex/codex-game-studios/recovery" / written.transaction_id
                victim = generation if target == "generation" else generation.parent
                replacement = self.repo / f"replacement-{target}"
                displaced = self.repo / f"displaced-{target}"
                shutil.copytree(victim, replacement)
                victim.rename(displaced)
                replacement.rename(victim)
            return written

        def apply_payload(_action, _mutation):
            nonlocal payload_called
            payload_called = True

        with mock.patch.object(
            transaction, "_write_journal_anchored", side_effect=replace_after_write
        ):
            with self.assertRaisesRegex(ManagerError, "STALE_PLAN"):
                apply_transaction(
                    self._approved,
                    self.repo,
                    self._replan,
                    apply_payload,
                    self._validate,
                )
        self.assertTrue(replaced)
        self.assertFalse(payload_called)
        self.assertEqual(b"before\n", (self.repo / "managed.txt").read_bytes())

    def test_transaction_rejects_generation_replacement_after_action_started(self):
        # Arrange / Act / Assert
        self._assert_action_started_directory_replacement_is_stale("generation")

    def test_transaction_rejects_recovery_replacement_after_action_started(self):
        # Arrange / Act / Assert
        self._assert_action_started_directory_replacement_is_stale("recovery")

    def test_transaction_validation_failure_rolls_back_every_byte_and_mode(self):
        # Arrange
        before = self._payload_snapshot()

        # Act
        with self.assertRaisesRegex(ManagerError, "VALIDATION_FAILED") as caught:
            apply_transaction(
                self._approved,
                self.repo,
                self._replan,
                self._apply_action,
                lambda _root: ["bad"],
            )

        # Assert
        self.assertEqual(before, self._payload_snapshot())
        self.assertEqual(["rolled-back"], self._terminal_phases())
        self.assertTrue(caught.exception.wrote)

    def test_transaction_prewrite_failure_reports_wrote_false(self):
        # Arrange
        (self.repo / "managed.txt").write_bytes(b"raced\n")

        # Act / Assert
        with self.assertRaises(ManagerError) as caught:
            apply_transaction(
                self._approved, self.repo, lambda: self._approved,
                self._apply_action, self._validate,
            )
        self.assertFalse(caught.exception.wrote)

    def test_transaction_uses_approved_uuid_and_rejects_generation_collision(self):
        # Arrange
        approved_id = "12345678-1234-4234-8234-123456789abc"

        # Act
        result = apply_transaction(
            self._approved, self.repo, self._replan, self._apply_action,
            self._validate, transaction_id=approved_id,
        )

        # Assert
        self.assertEqual(approved_id, result.transaction_id)
        self.assertTrue((self.repo / f".codex/codex-game-studios/recovery/{approved_id}").is_dir())
        (self.repo / "managed.txt").write_bytes(b"before\n")
        os.chmod(self.repo / "managed.txt", 0o644)
        import shutil
        shutil.rmtree(self.repo / "nested")
        with self.assertRaises(ManagerError) as caught:
            apply_transaction(
                self._approved, self.repo, self._replan, self._apply_action,
                self._validate, transaction_id=approved_id,
            )
        self.assertFalse(caught.exception.wrote)

    def test_lock_failure_releases_operating_system_lock(self):
        # Arrange / Act
        with self.assertRaises(InjectedFailure):
            with RepositoryLock(self.repo, timeout=0.1):
                raise InjectedFailure()

        # Assert
        with RepositoryLock(self.repo, timeout=0.1):
            pass

    def test_lock_second_holder_times_out_with_stable_category(self):
        # Arrange / Act / Assert
        with RepositoryLock(self.repo, timeout=0.1):
            with self.assertRaisesRegex(ManagerError, "LOCKED"):
                with RepositoryLock(self.repo, timeout=0.02):
                    pass

    def test_lock_inode_replacement_is_detected_before_release(self):
        # Arrange
        lock_path = self.repo / ".codex/codex-game-studios/manager.lock"

        # Act / Assert
        if os.name == "nt":
            with RepositoryLock(self.repo, timeout=0.1) as repository_lock:
                try:
                    lock_path.unlink()
                except PermissionError as error:
                    self.assertEqual(32, getattr(error, "winerror", None))
                    repository_lock.verify()
                    self.assertTrue(lock_path.is_file())
                else:
                    lock_path.write_bytes(b"replacement")
                    with self.assertRaisesRegex(ManagerError, "LOCKED"):
                        repository_lock.verify()
        else:
            with self.assertRaisesRegex(ManagerError, "LOCKED"):
                with RepositoryLock(self.repo, timeout=0.1) as repository_lock:
                    lock_path.unlink()
                    lock_path.write_bytes(b"replacement")
                    repository_lock.verify()

    @unittest.skipUnless(os.name == "posix", "POSIX root-directory flock")
    def test_root_flock_blocks_second_lock_after_manager_lock_replacement(self):
        # Arrange
        lock_path = self.repo / ".codex/codex-game-studios/manager.lock"

        # Act / Assert
        with self.assertRaisesRegex(ManagerError, "LOCKED"):
            with RepositoryLock(self.repo, timeout=0.1):
                lock_path.unlink()
                lock_path.write_bytes(b"new-lock-inode")
                with self.assertRaisesRegex(ManagerError, "LOCKED"):
                    with RepositoryLock(self.repo, timeout=0.02):
                        pass

    def test_transaction_success_retains_complete_committed_recovery(self):
        # Arrange / Act
        result = apply_transaction(
            self._approved,
            self.repo,
            self._replan,
            self._apply_action,
            self._validate,
        )

        # Assert
        self.assertEqual("committed", result.status)
        self.assertEqual(3, result.actions_applied)
        self.assertEqual(b"after\n", (self.repo / "managed.txt").read_bytes())
        self.assertEqual(b"created\n", (self.repo / "nested/created.txt").read_bytes())
        self.assertEqual(["committed"], self._terminal_phases())

    def test_nonchanging_actions_never_leak_active_action_into_committed_journal(self):
        for label, actions in (
            ("trailing", (*self._approved.actions, Action("preserve", "notes.txt", None, None, "preserve"))),
            ("only", (Action("diagnostic", "notes.txt", None, None, "diagnostic"),)),
        ):
            with self.subTest(label=label):
                before_generations = set(self._recovery_entries())
                if label == "trailing":
                    plan = plan_with_digest(dataclasses.replace(self._approved, actions=actions))
                else:
                    plan = plan_with_digest(
                        dataclasses.replace(
                            self._approved,
                            actions=actions,
                            target_observations=(),
                            target_results=(),
                        )
                    )
                apply_transaction(
                    plan, self.repo, lambda: plan, self._apply_action, self._validate
                )
                generation = (set(self._recovery_entries()) - before_generations).pop()
                authority = self._load_authority(generation, plan)
                journal = RecoveryJournal.load(
                    generation / "journal.json",
                    authority=authority,
                    allowed_phases=frozenset({"committed"}),
                )
                self.assertIsNone(journal.active_action)
                if label == "trailing":
                    (self.repo / "managed.txt").write_bytes(b"before\n")
                    os.chmod(self.repo / "managed.txt", 0o644)
                    import shutil
                    shutil.rmtree(self.repo / "nested")

    def test_transaction_directory_only_plan_has_durable_empty_snapshot_generation(self):
        # Arrange
        directory_plan = self._plan_with_actions(
            (Action("create", "only-directory", None, None, "create directory"),)
        )

        # Act
        with self.assertRaisesRegex(ManagerError, "VALIDATION_FAILED"):
            apply_transaction(
                directory_plan,
                self.repo,
                lambda: directory_plan,
                lambda action, mutation: mutation.make_directory(action.path, 0o750),
                lambda _root: ["bad"],
            )

        # Assert
        self.assertFalse((self.repo / "only-directory").exists())
        self.assertEqual(["rolled-back"], self._terminal_phases())

    def test_transaction_callback_cannot_mutate_snapshotted_ancestor_without_action(self):
        # Arrange
        before = self._payload_snapshot()

        def mutate_ancestor(_action: Action, mutation) -> None:
            mutation.make_directory("nested", 0o755)

        # Act
        with self.assertRaisesRegex(ManagerError, "UNSAFE_PATH"):
            apply_transaction(
                self._approved,
                self.repo,
                self._replan,
                mutate_ancestor,
                self._validate,
            )

        # Assert
        self.assertEqual(before, self._payload_snapshot())

    def test_transaction_retained_capability_is_revoked_after_callback(self):
        # Arrange
        retained = []
        one_action = self._plan_with_actions((self._approved.actions[0],))

        def apply_and_retain(action: Action, mutation) -> None:
            retained.append(mutation)
            mutation.replace_file(action.path, b"after\n", 0o640)

        # Act
        apply_transaction(
            one_action,
            self.repo,
            lambda: one_action,
            apply_and_retain,
            self._validate,
        )

        # Assert
        with self.assertRaisesRegex(ManagerError, "revoked"):
            retained[0].replace_file("managed.txt", b"late\n", 0o600)
        self.assertEqual(b"after\n", (self.repo / "managed.txt").read_bytes())

    def test_transaction_post_replan_race_is_stale_before_recovery(self):
        # Arrange
        plan = self._approved

        def race_then_return_approved() -> OperationPlan:
            (self.repo / "managed.txt").write_bytes(b"raced\n")
            return plan

        # Act / Assert
        with self.assertRaisesRegex(ManagerError, "STALE_PLAN"):
            apply_transaction(
                plan,
                self.repo,
                race_then_return_approved,
                self._apply_action,
                self._validate,
            )
        self.assertEqual(b"raced\n", (self.repo / "managed.txt").read_bytes())
        self.assertEqual([], self._recovery_entries())

    def test_transaction_after_snapshot_before_action_race_is_not_overwritten(self):
        # Arrange
        calls = 0

        def race_on_second_replan() -> OperationPlan:
            nonlocal calls
            calls += 1
            if calls == 2:
                (self.repo / "managed.txt").write_bytes(b"raced-after-snapshot\n")
            return self._approved

        # Act / Assert
        with self.assertRaisesRegex(ManagerError, "STALE_PLAN"):
            apply_transaction(
                self._approved,
                self.repo,
                race_on_second_replan,
                self._apply_action,
                self._validate,
            )
        self.assertEqual(
            b"raced-after-snapshot\n", (self.repo / "managed.txt").read_bytes()
        )
        self.assertEqual(["rolled-back"], self._terminal_phases())

    def test_transaction_during_snapshot_race_is_never_overwritten(self):
        # Arrange
        import safe_fs

        original = safe_fs.AnchoredFilesystem.read_file
        raced = False

        def read_then_race(filesystem, relative, expected=None):
            nonlocal raced
            content = original(filesystem, relative, expected)
            if relative == "managed.txt" and not raced:
                raced = True
                (self.repo / "managed.txt").write_bytes(b"raced-during-snapshot\n")
            return content

        # Act
        with mock.patch.object(safe_fs.AnchoredFilesystem, "read_file", read_then_race):
            with self.assertRaisesRegex(ManagerError, "STALE_PLAN"):
                apply_transaction(
                    self._approved,
                    self.repo,
                    self._replan,
                    self._apply_action,
                    self._validate,
                )

        # Assert
        self.assertEqual(
            b"raced-during-snapshot\n", (self.repo / "managed.txt").read_bytes()
        )
        self.assertEqual(["rolled-back"], self._terminal_phases())

    def test_transaction_action_boundary_rejects_root_replacement(self):
        # Arrange
        one_action = self._plan_with_actions((self._approved.actions[0],))
        moved = self.repo.with_name("moved-repository")
        replacement_attempted = False

        def replace_root_then_mutate(action: Action, mutation) -> None:
            nonlocal replacement_attempted
            replacement_attempted = True
            self.repo.rename(moved)
            self.repo.mkdir()
            (self.repo / "managed.txt").write_bytes(b"replacement-root\n")
            mutation.replace_file(action.path, b"after\n", 0o640)

        # Act / Assert
        with self.assertRaises((ManagerError, PermissionError)) as caught:
            apply_transaction(
                one_action,
                self.repo,
                lambda: one_action,
                replace_root_then_mutate,
                self._validate,
            )
        self.assertTrue(replacement_attempted)
        if isinstance(caught.exception, PermissionError):
            self.assertEqual("nt", os.name)
            self.assertEqual(32, getattr(caught.exception, "winerror", None))
            self.assertFalse(moved.exists())
            self.assertEqual(
                b"before\n", (self.repo / "managed.txt").read_bytes()
            )
        else:
            self.assertRegex(str(caught.exception), "ROLLBACK_FAILED")
            self.assertEqual(
                b"replacement-root\n", (self.repo / "managed.txt").read_bytes()
            )
            self.repo = moved

    def test_transaction_existing_uuid_generation_fails_without_reuse(self):
        # Arrange
        import transaction

        fixed = uuid.UUID("00000000-0000-4000-8000-000000000099")
        generation = self.repo / f".codex/codex-game-studios/recovery/{fixed}"
        generation.mkdir(parents=True)
        sentinel = generation / "sentinel.txt"
        sentinel.write_bytes(b"keep\n")

        # Act / Assert
        with mock.patch.object(transaction.uuid, "uuid4", return_value=fixed):
            with self.assertRaisesRegex(Exception, "already exists"):
                apply_transaction(
                    self._approved,
                    self.repo,
                    self._replan,
                    self._apply_action,
                    self._validate,
                )
        self.assertEqual(b"keep\n", sentinel.read_bytes())

    @unittest.skipUnless(os.name == "posix", "POSIX anchored replace regression")
    def test_transaction_temp_replace_failure_cleans_exact_temp(self):
        # Arrange
        import safe_fs

        one_action = self._plan_with_actions((self._approved.actions[0],))
        original_rename = safe_fs._rename_no_replace_posix
        failed = False

        def fail_payload_replace(source_fd, source, destination_fd, destination):
            nonlocal failed
            if destination == "managed.txt" and source.startswith(".managed.txt") and not failed:
                failed = True
                raise OSError("injected replace failure")
            return original_rename(source_fd, source, destination_fd, destination)

        # Act
        with mock.patch.object(
            safe_fs, "_rename_no_replace_posix", side_effect=fail_payload_replace
        ):
            with self.assertRaisesRegex(OSError, "injected replace failure"):
                apply_transaction(
                    one_action,
                    self.repo,
                    lambda: one_action,
                    lambda action, mutation: mutation.replace_file(
                        action.path, b"after\n", 0o640
                    ),
                    self._validate,
                )

        # Assert
        self.assertEqual(b"before\n", (self.repo / "managed.txt").read_bytes())
        self.assertEqual([], list(self.repo.glob(".managed.txt.*.tmp")))

    @unittest.skipUnless(os.name == "posix", "POSIX concurrent inode regression")
    def test_transaction_concurrent_new_inode_is_preserved_and_rollback_fails_closed(self):
        # Arrange
        import safe_fs

        one_action = self._plan_with_actions((self._approved.actions[0],))
        original_rename = safe_fs._rename_no_replace_posix
        injected = False

        def replace_with_race(source_fd, source, destination_fd, destination):
            nonlocal injected
            if source == "managed.txt" and not injected:
                injected = True
                (self.repo / "managed.txt").unlink()
                (self.repo / "managed.txt").write_bytes(b"concurrent-new-inode\n")
            return original_rename(source_fd, source, destination_fd, destination)

        # Act
        with mock.patch.object(
            safe_fs, "_rename_no_replace_posix", side_effect=replace_with_race
        ):
            with self.assertRaisesRegex(ManagerError, "STALE_PLAN|ROLLBACK_FAILED"):
                apply_transaction(
                    one_action,
                    self.repo,
                    lambda: one_action,
                    lambda action, mutation: mutation.replace_file(
                        action.path, b"after\n", 0o640
                    ),
                    self._validate,
                )

        # Assert
        self.assertEqual(
            b"concurrent-new-inode\n", (self.repo / "managed.txt").read_bytes()
        )
        self.assertEqual(["ROLLBACK_FAILED"], self._terminal_phases())

    def test_transaction_state_write_runs_after_validation_and_rolls_back_on_commit_fail(self):
        # Arrange
        state_bytes = b'{"state":"committed"}\n'
        state_action = Action(
            "state-write",
            "state.json",
            None,
            hashlib.sha256(state_bytes).hexdigest(),
            "persist installation state",
        )
        plan = self._plan_with_actions((self._approved.actions[0], state_action))
        order: list[str] = []

        def apply_action(action: Action, mutation) -> None:
            order.append("action")
            mutation.replace_file(action.path, b"after\n", 0o640)

        def validate(_root: Path) -> list[str]:
            order.append("validate")
            self.assertFalse((self.repo / "state.json").exists())
            return []

        def persist(action: Action, mutation) -> None:
            order.append("state")
            mutation.replace_file(action.path, state_bytes, 0o600)

        def fail_after_commit(phase: str) -> None:
            if phase == "journal-committed":
                raise InjectedFailure(phase)

        # Act
        with self.assertRaisesRegex(InjectedFailure, "journal-committed"):
            apply_transaction(
                plan,
                self.repo,
                lambda: plan,
                apply_action,
                validate,
                persist_state=persist,
                failpoint=fail_after_commit,
            )

        # Assert
        self.assertEqual(["action", "validate", "state"], order)
        self.assertEqual(b"before\n", (self.repo / "managed.txt").read_bytes())
        self.assertFalse((self.repo / "state.json").exists())
        self.assertEqual(["rolled-back"], self._terminal_phases())

    def test_transaction_validation_failure_never_invokes_state_callback(self):
        # Arrange
        state_action = Action(
            "state-write",
            "state.json",
            None,
            hashlib.sha256(b"state").hexdigest(),
            "persist installation state",
        )
        plan = self._plan_with_actions((state_action,))
        called = False

        def persist(_action: Action, _mutation) -> None:
            nonlocal called
            called = True

        # Act
        with self.assertRaisesRegex(ManagerError, "VALIDATION_FAILED"):
            apply_transaction(
                plan,
                self.repo,
                lambda: plan,
                lambda _action, _mutation: None,
                lambda _root: ["bad"],
                persist_state=persist,
            )

        # Assert
        self.assertFalse(called)
        self.assertFalse((self.repo / "state.json").exists())

    def test_transaction_state_write_can_remove_exact_file_after_validation(self):
        # Arrange
        state = self.repo / "state.json"
        state.write_bytes(b"owned state\n")
        state.chmod(0o640)
        state_action = Action(
            "state-write",
            "state.json",
            hashlib.sha256(state.read_bytes()).hexdigest(),
            None,
            "remove installation state",
        )
        plan = self._plan_with_actions((state_action,))
        order: list[str] = []

        # Act
        result = apply_transaction(
            plan,
            self.repo,
            lambda: plan,
            lambda _action, _mutation: None,
            lambda _root: order.append("validate") or [],
            persist_state=lambda action, mutation: (
                order.append("state"), mutation.remove_state_file(action.path)
            ),
        )

        # Assert
        self.assertEqual("committed", result.status)
        self.assertEqual(["validate", "state"], order)
        self.assertFalse(state.exists())

    def test_transaction_validation_failure_never_invokes_state_removal(self):
        # Arrange
        state = self.repo / "state.json"
        state.write_bytes(b"owned state\n")
        state_action = Action(
            "state-write", "state.json", hashlib.sha256(state.read_bytes()).hexdigest(), None,
            "remove installation state",
        )
        plan = self._plan_with_actions((state_action,))
        called = False

        def remove(_action, _mutation):
            nonlocal called
            called = True

        # Act / Assert
        with self.assertRaisesRegex(ManagerError, "VALIDATION_FAILED"):
            apply_transaction(
                plan, self.repo, lambda: plan, lambda _action, _mutation: None,
                lambda _root: ["bad"], persist_state=remove,
            )
        self.assertFalse(called)
        self.assertEqual(b"owned state\n", state.read_bytes())

    def test_transaction_state_removal_rolls_back_bytes_and_mode_after_state_written_failure(self):
        # Arrange
        state = self.repo / "state.json"
        state.write_bytes(b"owned state\n")
        state.chmod(0o640)
        state_action = Action(
            "state-write", "state.json", hashlib.sha256(state.read_bytes()).hexdigest(), None,
            "remove installation state",
        )
        plan = self._plan_with_actions((state_action,))

        # Act
        with self.assertRaisesRegex(InjectedFailure, "state-written"):
            apply_transaction(
                plan, self.repo, lambda: plan, lambda _action, _mutation: None,
                self._validate,
                persist_state=lambda action, mutation: mutation.remove_state_file(action.path),
                failpoint=lambda phase: (_ for _ in ()).throw(InjectedFailure(phase))
                if phase == "state-written" else None,
            )

        # Assert
        self.assertEqual(b"owned state\n", state.read_bytes())
        self.assertEqual(0o640, state.stat().st_mode & 0o777)
        self.assertEqual(["rolled-back"], self._terminal_phases())

    def test_transaction_state_removal_capability_is_revoked_and_path_bound(self):
        # Arrange
        state = self.repo / "state.json"
        state.write_bytes(b"owned state\n")
        state_action = Action(
            "state-write", "state.json", hashlib.sha256(state.read_bytes()).hexdigest(), None,
            "remove installation state",
        )
        plan = self._plan_with_actions((state_action,))
        retained = []

        def persist(action, mutation):
            retained.append(mutation)
            with self.assertRaisesRegex(ManagerError, "UNSAFE_PATH"):
                mutation.remove_state_file("other.json")
            mutation.remove_state_file(action.path)

        # Act
        apply_transaction(
            plan, self.repo, lambda: plan, lambda _action, _mutation: None,
            self._validate, persist_state=persist,
        )

        # Assert
        with self.assertRaisesRegex(ManagerError, "UNSAFE_PATH"):
            retained[0].remove_state_file("state.json")

    def test_transaction_state_removal_rejects_nonmissing_approved_result(self):
        # Arrange
        state = self.repo / "state.json"
        state.write_bytes(b"owned state\n")
        replacement = b"replacement\n"
        state_action = Action(
            "state-write", "state.json", hashlib.sha256(state.read_bytes()).hexdigest(),
            hashlib.sha256(replacement).hexdigest(), "replace installation state",
        )
        plan = self._plan_with_actions((state_action,))

        # Act / Assert
        with self.assertRaisesRegex(ManagerError, "UNSAFE_PATH"):
            apply_transaction(
                plan, self.repo, lambda: plan, lambda _action, _mutation: None,
                self._validate,
                persist_state=lambda action, mutation: mutation.remove_state_file(action.path),
            )
        self.assertEqual(b"owned state\n", state.read_bytes())

    def test_transaction_nested_scaffold_bytes_change_rejects_stale_plan(self):
        # Arrange
        nested = self.repo / ".codex/ordinary/nested/value.txt"
        nested.parent.mkdir(parents=True)
        nested.write_bytes(b"approved\n")
        called = False

        def failpoint(phase: str) -> None:
            if phase == "journal-written":
                nested.write_bytes(b"raced\n")

        def apply(_action: Action, _mutation) -> None:
            nonlocal called
            called = True

        # Act / Assert
        with self.assertRaisesRegex(ManagerError, "STALE_PLAN"):
            apply_transaction(
                self._approved,
                self.repo,
                lambda: self._approved,
                apply,
                self._validate,
                failpoint=failpoint,
            )
        self.assertFalse(called)

    def test_transaction_nested_scaffold_dirent_type_race_rejects_stale_plan(self):
        # Arrange
        nested = self.repo / ".codex/ordinary/nested"
        inner = nested / "inner"
        inner.mkdir(parents=True)
        (inner / "value.txt").write_bytes(b"approved\n")
        called = False

        def failpoint(phase: str) -> None:
            if phase == "journal-written":
                (inner / "value.txt").unlink()
                inner.rmdir()
                inner.write_bytes(b"raced type\n")

        def apply(_action: Action, _mutation) -> None:
            nonlocal called
            called = True

        # Act / Assert
        with self.assertRaisesRegex(ManagerError, "STALE_PLAN"):
            apply_transaction(
                self._approved,
                self.repo,
                lambda: self._approved,
                apply,
                self._validate,
                failpoint=failpoint,
            )
        self.assertFalse(called)

    @unittest.skipUnless(os.name == "posix", "POSIX inode identity")
    def test_transaction_same_content_scaffold_file_inode_change_rejects_stale_plan(self):
        # Arrange
        ordinary = self.repo / ".codex/ordinary.txt"
        ordinary.write_bytes(b"same bytes\n")
        called = False

        def failpoint(phase: str) -> None:
            if phase == "journal-written":
                replacement = ordinary.with_suffix(".replacement")
                replacement.write_bytes(b"same bytes\n")
                os.chmod(replacement, ordinary.stat().st_mode & 0o777)
                os.replace(replacement, ordinary)

        def apply(_action: Action, _mutation) -> None:
            nonlocal called
            called = True

        # Act / Assert
        with self.assertRaisesRegex(ManagerError, "STALE_PLAN"):
            apply_transaction(
                self._approved,
                self.repo,
                lambda: self._approved,
                apply,
                self._validate,
                failpoint=failpoint,
            )
        self.assertFalse(called)

    @unittest.skipUnless(os.name == "posix", "POSIX inode identity")
    def test_transaction_same_content_nested_directory_inode_change_rejects_stale_plan(self):
        # Arrange
        nested = self.repo / ".codex/ordinary/nested"
        nested.mkdir(parents=True)
        (nested / "value.txt").write_bytes(b"same bytes\n")
        called = False

        def failpoint(phase: str) -> None:
            if phase == "journal-written":
                replacement = nested.with_name("replacement")
                replacement.mkdir()
                (replacement / "value.txt").write_bytes(b"same bytes\n")
                os.chmod(replacement, nested.stat().st_mode & 0o777)
                displaced = self.repo / "displaced-nested"
                os.rename(nested, displaced)
                os.rename(replacement, nested)

        def apply(_action: Action, _mutation) -> None:
            nonlocal called
            called = True

        # Act / Assert
        with self.assertRaisesRegex(ManagerError, "STALE_PLAN"):
            apply_transaction(
                self._approved,
                self.repo,
                lambda: self._approved,
                apply,
                self._validate,
                failpoint=failpoint,
            )
        self.assertFalse(called)

    @unittest.skipUnless(os.name == "posix", "POSIX atomic replacement")
    def test_posix_general_atomic_write_zero_progress_prevents_installation(self):
        # Arrange
        import safe_fs

        target = "zero-progress.txt"
        with safe_fs.pin_root(self.repo) as pinned:
            filesystem = safe_fs.AnchoredFilesystem(pinned)
            expected = filesystem.observe(target)

            # Act / Assert
            with mock.patch.object(safe_fs.os, "write", return_value=0), mock.patch.object(
                safe_fs, "_rename_no_replace_posix"
            ) as install:
                with self.assertRaisesRegex(PayloadError, "short write"):
                    filesystem.atomic_replace(target, b"payload", 0o600, expected, "zero")
            install.assert_not_called()
        self.assertFalse((self.repo / target).exists())

    def test_windows_general_atomic_write_zero_progress_prevents_installation(self):
        # Arrange
        import safe_fs

        expected = safe_fs.SecureEntry("missing", None, None, None)
        pinned = types.SimpleNamespace(root=self.repo, verify=lambda: None, _descriptor=None)
        filesystem = safe_fs.AnchoredFilesystem(pinned)
        filesystem.observe = mock.Mock(return_value=expected)
        api = mock.Mock()
        opened = safe_fs._WindowsOpenedHandles(api, 41, (), False)

        # Act / Assert
        with mock.patch.object(safe_fs.os, "name", "nt"), mock.patch.object(
            safe_fs, "_windows_open_verified", return_value=opened
        ), mock.patch.object(
            safe_fs, "_windows_descriptor_from_verified", return_value=55
        ), mock.patch.object(safe_fs.os, "write", return_value=0), mock.patch.object(
            safe_fs.os, "close"
        ):
            with self.assertRaisesRegex(PayloadError, "short write"):
                filesystem.atomic_replace("zero-progress.txt", b"payload", 0o600, expected, "zero")
        api.rename_no_replace.assert_not_called()

    def test_transaction_state_written_failpoint_rolls_back_state_bytes(self):
        # Arrange
        state_bytes = b"state\n"
        state_action = Action(
            "state-write",
            "state.json",
            None,
            hashlib.sha256(state_bytes).hexdigest(),
            "persist installation state",
        )
        plan = self._plan_with_actions((state_action,))

        def failpoint(phase: str) -> None:
            if phase == "state-written":
                raise InjectedFailure(phase)

        # Act
        with self.assertRaisesRegex(InjectedFailure, "state-written"):
            apply_transaction(
                plan,
                self.repo,
                lambda: plan,
                lambda _action, _mutation: None,
                self._validate,
                persist_state=lambda action, mutation: mutation.replace_file(
                    action.path, state_bytes, 0o600
                ),
                failpoint=failpoint,
            )

        # Assert
        self.assertFalse((self.repo / "state.json").exists())
        self.assertEqual(["rolled-back"], self._terminal_phases())

    def test_windows_handle_mutations_use_disposition_and_no_replace_rename(self):
        # Arrange
        import safe_fs

        api = object.__new__(safe_fs._WindowsApi)
        calls: list[tuple[int, bytes]] = []

        def set_information(_handle, information_class, pointer, size):
            calls.append((information_class, ctypes.string_at(pointer, size)))
            return True

        api._set_file_information = set_information

        # Act
        api.mark_delete(101)
        api.rename_no_replace(202, r"C:\repo\managed.txt")

        # Assert
        self.assertEqual(4, calls[0][0])
        self.assertEqual(b"\x01", calls[0][1])
        self.assertEqual(3, calls[1][0])
        self.assertEqual(0, calls[1][1][0], "ReplaceIfExists must be FALSE")

    def test_windows_api_constructor_binds_ex_and_basic_identity_abis_separately(self):
        # Arrange
        import safe_fs

        class FakeFunction:
            def __init__(self, name):
                self.name = name
                self.calls = []
                self.argtypes = None
                self.restype = None

            def __call__(self, *args):
                self.calls.append(args)
                return 1

        kernel32 = types.SimpleNamespace(
            CreateFileW=FakeFunction("CreateFileW"),
            GetFileInformationByHandleEx=FakeFunction("GetFileInformationByHandleEx"),
            SetFileInformationByHandle=FakeFunction("SetFileInformationByHandle"),
            GetFinalPathNameByHandleW=FakeFunction("GetFinalPathNameByHandleW"),
            CloseHandle=FakeFunction("CloseHandle"),
            CreateDirectoryW=FakeFunction("CreateDirectoryW"),
            GetFileInformationByHandle=FakeFunction("GetFileInformationByHandle"),
        )

        # Act
        with mock.patch.object(safe_fs.ctypes, "WinDLL", return_value=kernel32, create=True):
            api = safe_fs._WindowsApi()
        api.attributes(11)
        api.basic_info(12)
        api.identity(13)

        # Assert
        self.assertEqual(2, len(kernel32.GetFileInformationByHandleEx.calls))
        self.assertEqual(1, len(kernel32.GetFileInformationByHandle.calls))
        self.assertEqual(11, kernel32.GetFileInformationByHandleEx.calls[0][0])
        self.assertEqual(12, kernel32.GetFileInformationByHandleEx.calls[1][0])
        self.assertEqual(13, kernel32.GetFileInformationByHandle.calls[0][0])

    def test_windows_create_directory_propagates_already_exists(self):
        # Arrange
        import safe_fs

        api = object.__new__(safe_fs._WindowsApi)
        api._create_directory = mock.Mock(return_value=False)

        # Act / Assert
        with mock.patch.object(
            safe_fs.ctypes, "get_last_error", return_value=183, create=True
        ), mock.patch.object(
            safe_fs.ctypes,
            "WinError",
            side_effect=lambda code: OSError(code, "already exists"),
            create=True,
        ):
            with self.assertRaises(OSError):
                api.create_directory(r"C:\repo\raced")

    def test_windows_directory_creation_pins_parent_and_verifies_exclusive_leaf(self):
        # Arrange
        import safe_fs

        pinned = types.SimpleNamespace(root=self.repo, verify=lambda: None, _descriptor=None)
        filesystem = safe_fs.AnchoredFilesystem(pinned)
        filesystem.observe = mock.Mock(
            side_effect=(
                safe_fs.SecureEntry("missing", None, None, None),
                safe_fs.SecureEntry("directory", "d" * 64, 0o755, "created-id"),
            )
        )
        api = mock.Mock()
        api.basic_info.return_value = safe_fs._FileBasicInfo(
            0, 0, 0, 0, safe_fs.FILE_ATTRIBUTE_DIRECTORY
        )
        parent = mock.MagicMock()
        parent.__enter__.return_value = types.SimpleNamespace(api=api)
        created = mock.MagicMock()
        api.create_directory.return_value = None

        # Act
        with mock.patch.object(safe_fs.os, "name", "nt"), mock.patch.object(
            safe_fs, "_windows_open_verified", side_effect=(parent, created)
        ) as opened:
            result = filesystem.create_directory_exclusive("new-directory", 0o755)

        # Assert
        self.assertEqual("created-id", result.identity)
        self.assertEqual(2, opened.call_count)
        self.assertFalse(opened.call_args_list[0].kwargs["create_parents"])
        self.assertTrue(opened.call_args_list[1].kwargs["final_directory"])
        self.assertEqual(
            safe_fs.GENERIC_READ | safe_fs.FILE_WRITE_ATTRIBUTES,
            opened.call_args_list[1].kwargs["access"],
        )
        api.create_directory.assert_called_once()

    def test_windows_directory_creation_rejects_create_time_already_exists_race(self):
        import safe_fs

        pinned = types.SimpleNamespace(root=self.repo, verify=lambda: None, _descriptor=None)
        filesystem = safe_fs.AnchoredFilesystem(pinned)
        filesystem.observe = mock.Mock(
            return_value=safe_fs.SecureEntry("missing", None, None, None)
        )
        api = mock.Mock()
        api.create_directory.side_effect = OSError(183, "already exists")
        parent = mock.MagicMock()
        parent.__enter__.return_value = types.SimpleNamespace(api=api)

        with mock.patch.object(safe_fs.os, "name", "nt"), mock.patch.object(
            safe_fs, "_windows_open_verified", return_value=parent
        ) as opened:
            with self.assertRaisesRegex(OSError, "already exists"):
                filesystem.create_directory_exclusive("raced-directory", 0o755)

        opened.assert_called_once()

    def test_windows_verified_snapshot_keeps_native_handle_open_through_post_read_checks(self):
        import safe_fs

        closed = False

        class Api:
            def identity(self, handle):
                if closed:
                    raise OSError("identity after close")
                return (7, handle)

            def basic_info(self, _handle):
                if closed:
                    raise OSError("basic info after close")
                return safe_fs._FileBasicInfo(0, 0, 0, 0, safe_fs.FILE_ATTRIBUTE_NORMAL)

            def close(self, _handle):
                raise AssertionError("detached final handle must not be closed twice")

        opened = safe_fs._WindowsOpenedHandles(Api(), 41, (), False)
        fake_msvcrt = types.SimpleNamespace(
            open_osfhandle=lambda handle, _flags: 55,
            get_osfhandle=lambda descriptor: 41,
        )
        pinned = types.SimpleNamespace(root=self.repo, verify=lambda: None, _descriptor=None)
        filesystem = safe_fs.AnchoredFilesystem(pinned)

        def close(_descriptor):
            nonlocal closed
            closed = True

        with mock.patch.object(safe_fs.os, "name", "nt"), mock.patch.object(
            safe_fs, "_windows_open_verified", return_value=opened
        ), mock.patch.dict(sys.modules, {"msvcrt": fake_msvcrt}), mock.patch.object(
            safe_fs.os, "read", side_effect=(b"snapshot\n", b"")
        ), mock.patch.object(safe_fs.os, "close", side_effect=close) as closed_call:
            content = filesystem.read_file_verified(
                "snapshot.bin",
                expected_digest=hashlib.sha256(b"snapshot\n").hexdigest(),
                expected_mode=0o600,
            )

        self.assertEqual(b"snapshot\n", content)
        closed_call.assert_called_once_with(55)

    def test_windows_verified_snapshot_compares_logical_writable_mode(self):
        # Arrange
        import safe_fs

        content = b"snapshot\n"
        digest = hashlib.sha256(content).hexdigest()
        cases = (
            (safe_fs.FILE_ATTRIBUTE_NORMAL, 0o644, True),
            (safe_fs.FILE_ATTRIBUTE_READONLY, 0o444, True),
            (safe_fs.FILE_ATTRIBUTE_NORMAL, 0o444, False),
            (safe_fs.FILE_ATTRIBUTE_READONLY, 0o644, False),
        )

        # Act / Assert
        for attributes, expected_mode, accepted in cases:
            with self.subTest(
                attributes=attributes,
                expected_mode=oct(expected_mode),
            ):
                api = mock.Mock()
                api.identity.return_value = (7, 41)
                api.basic_info.return_value = safe_fs._FileBasicInfo(
                    0, 0, 0, 0, attributes
                )
                opened = safe_fs._WindowsOpenedHandles(api, 41, (), False)
                fake_msvcrt = types.SimpleNamespace(
                    open_osfhandle=lambda _handle, _flags: 55,
                    get_osfhandle=lambda _descriptor: 41,
                )
                pinned = types.SimpleNamespace(
                    root=self.repo,
                    verify=lambda: None,
                    _descriptor=None,
                )
                filesystem = safe_fs.AnchoredFilesystem(pinned)
                patches = (
                    mock.patch.object(safe_fs.os, "name", "nt"),
                    mock.patch.object(
                        safe_fs, "_windows_open_verified", return_value=opened
                    ),
                    mock.patch.dict(sys.modules, {"msvcrt": fake_msvcrt}),
                    mock.patch.object(
                        safe_fs.os, "read", side_effect=(content, b"")
                    ),
                    mock.patch.object(safe_fs.os, "close"),
                )
                with contextlib.ExitStack() as stack:
                    for patcher in patches:
                        stack.enter_context(patcher)
                    if accepted:
                        self.assertEqual(
                            content,
                            filesystem.read_file_verified(
                                "snapshot.bin",
                                expected_digest=digest,
                                expected_mode=expected_mode,
                            ),
                        )
                    else:
                        with self.assertRaisesRegex(PayloadError, "mode"):
                            filesystem.read_file_verified(
                                "snapshot.bin",
                                expected_digest=digest,
                                expected_mode=expected_mode,
                            )

    def test_windows_live_state_matching_uses_logical_writable_mode(self):
        # Arrange
        import safe_fs

        digest = "a" * 64
        writable = safe_fs.SecureEntry("file", digest, 0o600, "identity")
        writable_authority = safe_fs.SecureEntry(
            "file", digest, 0o644, "identity"
        )
        readonly = safe_fs.SecureEntry("file", digest, 0o400, "identity")
        readonly_authority = safe_fs.SecureEntry(
            "file", digest, 0o444, "identity"
        )

        # Act / Assert
        with mock.patch.object(safe_fs.os, "name", "nt"):
            self.assertTrue(
                safe_fs.AnchoredFilesystem.matches(
                    writable, writable_authority
                )
            )
            self.assertTrue(
                safe_fs.AnchoredFilesystem.matches(
                    readonly, readonly_authority
                )
            )
            self.assertFalse(
                safe_fs.AnchoredFilesystem.matches(
                    writable, readonly_authority
                )
            )
        with mock.patch.object(safe_fs.os, "name", "posix"):
            self.assertFalse(
                safe_fs.AnchoredFilesystem.matches(
                    writable, writable_authority
                )
            )

    def test_windows_internal_journal_write_loops_on_short_writes_and_rejects_zero(self):
        import safe_fs

        relative = ".codex/codex-game-studios/recovery/manual/journal.json"
        expected = safe_fs.SecureEntry("file", hashlib.sha256(b"old").hexdigest(), 0o600, "old-id")
        result = safe_fs.SecureEntry("file", hashlib.sha256(b"hello").hexdigest(), 0o600, "new-id")
        pinned = types.SimpleNamespace(root=self.repo, verify=lambda: None, _descriptor=None)
        filesystem = safe_fs.AnchoredFilesystem(pinned)
        filesystem.observe = mock.Mock(side_effect=(expected, expected, result))
        api = mock.Mock()
        api.basic_info.return_value = safe_fs._FileBasicInfo(
            0, 0, 0, 0, safe_fs.FILE_ATTRIBUTE_NORMAL
        )
        opened = safe_fs._WindowsOpenedHandles(api, 41, (), False)
        fake_msvcrt = types.SimpleNamespace(get_osfhandle=lambda _descriptor: 41)
        writes: list[bytes] = []

        def short_write(_descriptor, data):
            chunk = bytes(data)
            writes.append(chunk)
            return 2 if len(chunk) > 2 else len(chunk)

        with mock.patch.object(safe_fs.os, "name", "nt"), mock.patch.object(
            safe_fs, "_windows_open_verified", return_value=opened
        ), mock.patch.object(
            safe_fs, "_windows_descriptor_from_verified", return_value=55
        ), mock.patch.dict(sys.modules, {"msvcrt": fake_msvcrt}), mock.patch.object(
            safe_fs.os, "write", side_effect=short_write
        ), mock.patch.object(safe_fs.os, "fsync"), mock.patch.object(safe_fs.os, "close"):
            filesystem.atomic_replace_internal(relative, b"hello", 0o600, "token")

        self.assertEqual([b"hello", b"llo", b"o"], writes)
        api.rename_replace.assert_called_once()

        filesystem.observe = mock.Mock(return_value=expected)
        api.reset_mock()
        opened = safe_fs._WindowsOpenedHandles(api, 42, (), False)
        with mock.patch.object(safe_fs.os, "name", "nt"), mock.patch.object(
            safe_fs, "_windows_open_verified", return_value=opened
        ), mock.patch.object(
            safe_fs, "_windows_descriptor_from_verified", return_value=56
        ), mock.patch.dict(sys.modules, {"msvcrt": fake_msvcrt}), mock.patch.object(
            safe_fs.os, "write", return_value=0
        ), mock.patch.object(safe_fs.os, "close"):
            with self.assertRaisesRegex(PayloadError, "short write"):
                filesystem.atomic_replace_internal(relative, b"hello", 0o600, "token2")
        api.rename_replace.assert_not_called()

    @unittest.skipUnless(os.name == "posix", "POSIX internal journal replacement")
    def test_posix_internal_journal_zero_progress_preserves_old_journal(self):
        # Arrange
        import safe_fs

        relative = ".codex/codex-game-studios/recovery/manual/journal.json"
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        old = b'{"version":"old"}\n'
        path.write_bytes(old)

        # Act / Assert
        with safe_fs.pin_root(self.repo) as pinned:
            filesystem = safe_fs.AnchoredFilesystem(pinned)
            with mock.patch.object(
                safe_fs.os,
                "write",
                side_effect=(0, AssertionError("zero-progress write loop repeated")),
            ), mock.patch.object(safe_fs.os, "rename") as install:
                with self.assertRaisesRegex(PayloadError, "short write"):
                    filesystem.atomic_replace_internal(relative, b"new", 0o600, "zero")
            install.assert_not_called()
        self.assertEqual(old, path.read_bytes())

    @unittest.skipUnless(os.name == "posix", "POSIX child-dirent identity")
    def test_anchored_directory_observation_rejects_child_dirent_swap(self):
        # Arrange
        import safe_fs

        directory = self.repo / "observed"
        directory.mkdir()
        child = directory / "child.txt"
        child.write_bytes(b"before\n")
        original_hash = safe_fs._hash_descriptor
        swapped = False

        def hash_then_swap(descriptor, before):
            nonlocal swapped
            digest = original_hash(descriptor, before)
            if not swapped:
                swapped = True
                child.unlink()
                child.write_bytes(b"replacement\n")
            return digest

        # Act / Assert
        with safe_fs.pin_root(self.repo) as pinned:
            filesystem = safe_fs.AnchoredFilesystem(pinned)
            with mock.patch.object(safe_fs, "_hash_descriptor", hash_then_swap):
                with self.assertRaisesRegex(PayloadError, "child changed"):
                    filesystem.observe("observed")

    @unittest.skipUnless(os.name == "posix", "descriptor identity test")
    def test_verified_snapshot_read_rejects_dirent_swap_during_consumption(self):
        import safe_fs

        path = self.repo / "snapshot.bin"
        content = b"verified snapshot bytes\n"
        path.write_bytes(content)
        os.chmod(path, 0o600)
        original_read = safe_fs.os.read
        swapped = False

        def read_then_swap(descriptor, count):
            nonlocal swapped
            chunk = original_read(descriptor, count)
            if chunk and not swapped:
                swapped = True
                path.unlink()
                path.write_bytes(content)
                os.chmod(path, 0o600)
            return chunk

        with safe_fs.pin_root(self.repo) as pinned:
            filesystem = safe_fs.AnchoredFilesystem(pinned)
            with mock.patch.object(safe_fs.os, "read", side_effect=read_then_swap):
                with self.assertRaisesRegex(PayloadError, "identity changed"):
                    filesystem.read_file_verified(
                        "snapshot.bin",
                        expected_digest=hashlib.sha256(content).hexdigest(),
                        expected_mode=0o600,
                    )

    def test_transaction_snapshot_setup_adversary_preserves_unproven_generation(self):
        # Arrange
        import safe_fs

        original = safe_fs.AnchoredFilesystem.atomic_replace

        def inject_unknown(filesystem, relative, data, mode, expected, token):
            if "/snapshots/" in relative:
                unknown = self.repo / PurePosixPath(relative).parent / "unknown.bin"
                unknown.write_bytes(b"adversary")
                raise InjectedFailure("snapshot setup")
            return original(filesystem, relative, data, mode, expected, token)

        # Act
        with mock.patch.object(safe_fs.AnchoredFilesystem, "atomic_replace", inject_unknown):
            with self.assertRaisesRegex(ManagerError, "ROLLBACK_FAILED"):
                apply_transaction(
                    self._approved,
                    self.repo,
                    self._replan,
                    self._apply_action,
                    self._validate,
                )

        # Assert
        generations = self._recovery_entries()
        self.assertEqual(1, len(generations))
        self.assertEqual(b"adversary", (generations[0] / "snapshots/unknown.bin").read_bytes())

    def test_transaction_snapshot_setup_failure_cleans_after_quarantine_configuration(self):
        import safe_fs

        def fail_snapshot(*_args, **_kwargs):
            raise InjectedFailure("snapshot setup")

        with mock.patch.object(
            safe_fs.AnchoredFilesystem, "atomic_replace", side_effect=fail_snapshot
        ):
            with self.assertRaisesRegex(InjectedFailure, "snapshot setup"):
                apply_transaction(
                    self._approved,
                    self.repo,
                    self._replan,
                    self._apply_action,
                    self._validate,
                )

        self.assertEqual([], self._recovery_entries())

    def test_transaction_action_callback_must_realize_digest_bound_result(self):
        # Arrange
        before = self._payload_snapshot()

        # Act
        with self.assertRaisesRegex(ManagerError, "VALIDATION_FAILED"):
            apply_transaction(
                self._approved,
                self.repo,
                self._replan,
                lambda _action, _mutation: None,
                self._validate,
            )

        # Assert
        self.assertEqual(before, self._payload_snapshot())

    def test_crash_after_quarantine_move_before_marker_recovers_exactly(self):
        import transaction

        original = transaction._write_journal_anchored
        injected = False

        def crash_before_marker(filesystem, relative, journal):
            nonlocal injected
            if journal.active_quarantined and not injected:
                injected = True
                raise InjectedFailure("post-quarantine pre-marker crash")
            return original(filesystem, relative, journal)

        with mock.patch.object(
            transaction, "_write_journal_anchored", side_effect=crash_before_marker
        ):
            with self.assertRaisesRegex(InjectedFailure, "pre-marker"):
                apply_transaction(
                    self._approved,
                    self.repo,
                    self._replan,
                    self._apply_action,
                    self._validate,
                )

        self.assertTrue(injected)
        self.assertEqual(b"before\n", (self.repo / "managed.txt").read_bytes())
        generation = self._recovery_entries()[0]
        authority = self._load_authority(generation)
        journal = RecoveryJournal.load(
            generation / "journal.json",
            authority=authority,
            allowed_phases=frozenset({"rolled-back"}),
        )
        self.assertTrue(journal.active_quarantined)

    def test_pre_marker_crash_state_loads_only_when_target_quarantine_pair_is_unambiguous(self):
        import transaction

        original = transaction._write_journal_anchored

        def preserve_crash_state(filesystem, relative, journal):
            if journal.active_quarantined or journal.phase == "ROLLBACK_FAILED":
                raise InjectedFailure("preserve pre-marker crash")
            return original(filesystem, relative, journal)

        with mock.patch.object(
            transaction, "_write_journal_anchored", side_effect=preserve_crash_state
        ):
            with self.assertRaisesRegex(ManagerError, "ROLLBACK_FAILED"):
                apply_transaction(
                    self._approved,
                    self.repo,
                    self._replan,
                    self._apply_action,
                    self._validate,
                )

        generation = self._recovery_entries()[0]
        authority = self._load_authority(generation)
        journal = RecoveryJournal.load(
            generation / "journal.json",
            authority=authority,
            allowed_phases=frozenset({"action-started"}),
        )
        self.assertFalse(journal.active_quarantined)
        self.assertFalse((self.repo / "managed.txt").exists())

        (self.repo / "managed.txt").write_bytes(b"ambiguous concurrent target\n")
        os.chmod(self.repo / "managed.txt", 0o644)
        with self.assertRaisesRegex(ManagerError, "ambiguous"):
            RecoveryJournal.load(
                generation / "journal.json",
                authority=authority,
                allowed_phases=frozenset({"action-started"}),
            )

    def test_transaction_each_journal_failpoint_restores_preoperation_tree(self):
        phases = (
            "snapshot-created",
            "journal-written",
            "action-applied",
            "validation-started",
            "journal-committed",
        )
        for phase in phases:
            with self.subTest(phase=phase):
                # Arrange
                (self.repo / "managed.txt").write_bytes(b"before\n")
                try:
                    (self.repo / "nested/created.txt").unlink()
                    (self.repo / "nested").rmdir()
                except FileNotFoundError:
                    pass
                before = self._payload_snapshot()
                generations_before = len(self._recovery_entries())

                def failpoint(current: str) -> None:
                    if current == phase:
                        raise InjectedFailure(current)

                # Act
                with self.assertRaisesRegex(InjectedFailure, phase):
                    apply_transaction(
                        self._approved,
                        self.repo,
                        self._replan,
                        self._apply_action,
                        self._validate,
                        failpoint=failpoint,
                    )

                # Assert
                self.assertEqual(before, self._payload_snapshot())
                self.assertEqual(generations_before + 1, len(self._recovery_entries()))
                self.assertEqual("rolled-back", self._terminal_phases()[-1])

    def test_transaction_rollback_failure_preserves_checksummed_recovery(self):
        # Arrange
        import transaction

        before = snapshot_tree(self.repo)

        # Act
        with mock.patch.object(
            transaction,
            "_restore_acquired_snapshot",
            side_effect=OSError("injected restore failure"),
        ):
            with self.assertRaisesRegex(ManagerError, "ROLLBACK_FAILED") as caught:
                apply_transaction(
                    self._approved,
                    self.repo,
                    self._replan,
                    self._apply_action,
                    lambda _root: ["bad"],
                )

        # Assert
        self.assertNotEqual(before, snapshot_tree(self.repo))
        generations = self._recovery_entries()
        self.assertEqual(1, len(generations))
        journal_path = generations[0] / "journal.json"
        authority = self._load_authority(generations[0])
        journal = RecoveryJournal.load(
            journal_path,
            authority=authority,
            allowed_phases=frozenset({"ROLLBACK_FAILED"}),
        )
        self.assertEqual("ROLLBACK_FAILED", journal.phase)
        self.assertTrue((generations[0] / "snapshots").is_dir())
        relative_generation = generations[0].relative_to(self.repo).as_posix()
        self.assertEqual({
            "generation": relative_generation,
            "journal": f"{relative_generation}/journal.json",
            "snapshots": f"{relative_generation}/snapshots",
            "phase": "ROLLBACK_FAILED",
            "status": "retained",
        }, caught.exception.recovery)

    def test_transaction_rejects_link_target_before_snapshot_or_action(self):
        # Arrange
        outside = Path(self.temporary.name) / "outside.txt"
        outside.write_bytes(b"outside\n")
        (self.repo / "managed.txt").unlink()
        (self.repo / "managed.txt").symlink_to(outside)
        approved = self._approved

        # Act / Assert
        with self.assertRaisesRegex(ManagerError, "UNSAFE_PATH"):
            apply_transaction(
                approved,
                self.repo,
                lambda: approved,
                self._apply_action,
                self._validate,
            )
        self.assertEqual(b"outside\n", outside.read_bytes())

    def test_recovery_journal_checksum_or_extra_fields_are_rejected(self):
        # Arrange
        generation = self.repo / ".codex/codex-game-studios/recovery/manual"
        generation.mkdir(parents=True)
        path = generation / "journal.json"
        path.write_text('{"checksum":"' + "0" * 64 + '"}\n', encoding="utf-8")

        # Act / Assert
        with self.assertRaisesRegex(ManagerError, "INVALID_INSTALLATION_STATE"):
            RecoveryJournal._parse(path.read_bytes())

    def test_internal_journal_atomic_replace_preserves_old_or_new_at_failpoints(self):
        import safe_fs

        relative = ".codex/codex-game-studios/recovery/manual/journal.json"
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        old = b'{"version":"old"}\n'
        new = b'{"version":"new"}\n'
        for phase in ("before-rename", "at-rename", "after-rename"):
            path.write_bytes(old)
            with self.subTest(phase=phase), safe_fs.pin_root(self.repo) as pinned:
                filesystem = safe_fs.AnchoredFilesystem(pinned)

                def failpoint(current: str) -> None:
                    if current == phase:
                        raise InjectedFailure(current)

                with self.assertRaisesRegex(InjectedFailure, phase):
                    filesystem.atomic_replace_internal(
                        relative, new, 0o600, "token", failpoint=failpoint
                    )
                self.assertIn(path.read_bytes(), {old, new})

    def test_recovery_journal_rejects_self_checksummed_forged_plan_authority(self):
        # Arrange
        apply_transaction(
            self._approved,
            self.repo,
            self._replan,
            self._apply_action,
            self._validate,
        )
        generation = self._recovery_entries()[0]
        journal_path = generation / "journal.json"
        document = json.loads(journal_path.read_text(encoding="utf-8"))
        authority = self._load_authority(generation)
        document["plan_digest"] = "f" * 64
        body = dict(document)
        body.pop("checksum")
        from models import canonical_json

        document["checksum"] = hashlib.sha256(canonical_json(body)).hexdigest()
        journal_path.write_bytes(canonical_json(document))
        # Act / Assert
        with self.assertRaisesRegex(ManagerError, "unauthorized"):
            RecoveryJournal.load(
                journal_path,
                authority=authority,
                allowed_phases=frozenset({"committed"}),
            )

    def test_recovery_journal_rejects_self_checksummed_forged_snapshot_target(self):
        # Arrange
        apply_transaction(
            self._approved,
            self.repo,
            self._replan,
            self._apply_action,
            self._validate,
        )
        generation = self._recovery_entries()[0]
        journal_path = generation / "journal.json"
        authority = self._load_authority(generation)
        document = json.loads(journal_path.read_text(encoding="utf-8"))
        document["snapshots"][0]["path"] = "aaa-forged.txt"
        body = dict(document)
        body.pop("checksum")
        from models import canonical_json

        document["checksum"] = hashlib.sha256(canonical_json(body)).hexdigest()
        journal_path.write_bytes(canonical_json(document))
        # Act / Assert
        with self.assertRaisesRegex(ManagerError, "unauthorized"):
            RecoveryJournal.load(
                journal_path,
                authority=authority,
                allowed_phases=frozenset({"committed"}),
            )

    def test_recovery_authority_rejects_self_checksummed_forged_action(self):
        apply_transaction(
            self._approved, self.repo, self._replan, self._apply_action, self._validate
        )
        generation = self._recovery_entries()[0]
        path = generation / "authority.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["changing_actions"][0]["path"] = "forged.txt"
        body = dict(document)
        body.pop("checksum")
        from models import canonical_json

        document["checksum"] = hashlib.sha256(canonical_json(body)).hexdigest()
        path.write_bytes(canonical_json(document))

        with self.assertRaisesRegex(ManagerError, "approval"):
            self._load_authority(generation)

    def test_recovery_authority_rejects_self_checksummed_forged_snapshot(self):
        apply_transaction(
            self._approved, self.repo, self._replan, self._apply_action, self._validate
        )
        generation = self._recovery_entries()[0]
        path = generation / "authority.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["snapshots"][0]["path"] = "forged.txt"
        body = dict(document)
        body.pop("checksum")
        from models import canonical_json

        document["checksum"] = hashlib.sha256(canonical_json(body)).hexdigest()
        path.write_bytes(canonical_json(document))

        with self.assertRaisesRegex(ManagerError, "snapshots"):
            self._load_authority(generation)

    def test_recovery_authority_rejects_coordinated_snapshot_bytes_hash_mode_forgery(self):
        apply_transaction(
            self._approved, self.repo, self._replan, self._apply_action, self._validate
        )
        generation = self._recovery_entries()[0]
        authority_path = generation / "authority.json"
        document = json.loads(authority_path.read_text(encoding="utf-8"))
        forged = b"coordinated-forgery\n"
        snapshot_record = next(
            item for item in document["snapshots"] if item["snapshot_path"] is not None
        )
        (self.repo / snapshot_record["snapshot_path"]).write_bytes(forged)
        snapshot_record["sha256"] = hashlib.sha256(forged).hexdigest()
        snapshot_record["mode"] = 0o777
        body = dict(document)
        body.pop("checksum")
        from models import canonical_json

        document["checksum"] = hashlib.sha256(canonical_json(body)).hexdigest()
        authority_path.write_bytes(canonical_json(document))

        with self.assertRaisesRegex(ManagerError, "approved plan observation"):
            self._load_authority(generation)

    def test_recovery_journal_rejects_self_checksummed_impossible_committed_prefix(self):
        apply_transaction(
            self._approved, self.repo, self._replan, self._apply_action, self._validate
        )
        generation = self._recovery_entries()[0]
        authority = self._load_authority(generation)
        path = generation / "journal.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["execution_index"] = 0
        document["applied_paths"] = []
        body = dict(document)
        body.pop("checksum")
        from models import canonical_json

        document["checksum"] = hashlib.sha256(canonical_json(body)).hexdigest()
        path.write_bytes(canonical_json(document))

        with self.assertRaisesRegex(ManagerError, "phase history"):
            RecoveryJournal.load(
                path, authority=authority, allowed_phases=frozenset({"committed"})
            )

    def test_recovery_load_rejects_extra_generation_inventory(self):
        apply_transaction(
            self._approved, self.repo, self._replan, self._apply_action, self._validate
        )
        generation = self._recovery_entries()[0]
        authority = self._load_authority(generation)
        (generation / "extra").write_bytes(b"unauthorized\n")

        with self.assertRaisesRegex(ManagerError, "inventory"):
            RecoveryJournal.load(
                generation / "journal.json",
                authority=authority,
                allowed_phases=frozenset({"committed"}),
            )

    def test_recovery_load_rejects_wrong_content_in_required_quarantine(self):
        apply_transaction(
            self._approved, self.repo, self._replan, self._apply_action, self._validate
        )
        generation = self._recovery_entries()[0]
        authority = self._load_authority(generation)
        required = next(
            record for record in authority.quarantine_records if record.role == "approved-before"
        )
        (self.repo / required.path).write_bytes(b"wrong quarantine bytes\n")

        with self.assertRaisesRegex(ManagerError, "quarantine content"):
            RecoveryJournal.load(
                generation / "journal.json",
                authority=authority,
                allowed_phases=frozenset({"committed"}),
            )

    def test_recovery_load_rejects_missing_required_quarantine(self):
        apply_transaction(
            self._approved, self.repo, self._replan, self._apply_action, self._validate
        )
        generation = self._recovery_entries()[0]
        authority = self._load_authority(generation)
        required = next(
            record for record in authority.quarantine_records if record.role == "approved-before"
        )
        (self.repo / required.path).unlink()

        with self.assertRaisesRegex(ManagerError, "quarantine inventory"):
            RecoveryJournal.load(
                generation / "journal.json",
                authority=authority,
                allowed_phases=frozenset({"committed"}),
            )

    def test_recovery_load_rejects_future_quarantine_occupancy_in_committed_phase(self):
        apply_transaction(
            self._approved, self.repo, self._replan, self._apply_action, self._validate
        )
        generation = self._recovery_entries()[0]
        authority = self._load_authority(generation)
        future = next(
            record for record in authority.quarantine_records if record.role == "rollback-after"
        )
        path = self.repo / future.path
        if future.entry_type == "directory":
            path.mkdir()
            os.chmod(path, future.mode)
        else:
            path.write_bytes(b"future\n")
            os.chmod(path, future.mode)

        with self.assertRaisesRegex(ManagerError, "quarantine inventory"):
            RecoveryJournal.load(
                generation / "journal.json",
                authority=authority,
                allowed_phases=frozenset({"committed"}),
            )

    def test_rolled_back_terminal_quarantine_inventory_loads_exactly(self):
        with self.assertRaisesRegex(ManagerError, "VALIDATION_FAILED"):
            apply_transaction(
                self._approved,
                self.repo,
                self._replan,
                self._apply_action,
                lambda _root: ["rollback"],
            )
        generation = self._recovery_entries()[0]
        authority = self._load_authority(generation)

        journal = RecoveryJournal.load(
            generation / "journal.json",
            authority=authority,
            allowed_phases=frozenset({"rolled-back"}),
        )

        self.assertEqual("rolled-back", journal.phase)

    def test_corrupt_recovery_snapshot_prevents_restore_and_terminal_claim(self):
        def corrupt_then_fail(_root: Path) -> list[str]:
            generation = self._recovery_entries()[0]
            snapshot = next((generation / "snapshots").iterdir())
            snapshot.write_bytes(b"corrupt\n")
            return ["force rollback"]

        with self.assertRaisesRegex(ManagerError, "ROLLBACK_FAILED"):
            apply_transaction(
                self._approved,
                self.repo,
                self._replan,
                self._apply_action,
                corrupt_then_fail,
            )

        self.assertEqual(b"after\n", (self.repo / "managed.txt").read_bytes())
        self.assertEqual(["validation-started"], self._terminal_phases())

    def test_snapshot_tamper_after_generation_verification_prevents_restore_write(self):
        tampered = False

        def tamper(phase: str) -> None:
            nonlocal tampered
            if phase == "before-restore-read" and not tampered:
                tampered = True
                generation = self._recovery_entries()[0]
                next((generation / "snapshots").iterdir()).write_bytes(b"late-tamper\n")

        with self.assertRaisesRegex(ManagerError, "ROLLBACK_FAILED"):
            apply_transaction(
                self._approved,
                self.repo,
                self._replan,
                self._apply_action,
                lambda _root: ["force rollback"],
                failpoint=tamper,
            )

        self.assertTrue(tampered)
        self.assertEqual(b"after\n", (self.repo / "managed.txt").read_bytes())
        self.assertEqual(["validation-started"], self._terminal_phases())

    def test_corrupt_recovery_snapshot_prevents_commit(self):
        def corrupt_then_pass(_root: Path) -> list[str]:
            generation = self._recovery_entries()[0]
            snapshot = next((generation / "snapshots").iterdir())
            snapshot.write_bytes(b"corrupt\n")
            return []

        with self.assertRaisesRegex(ManagerError, "ROLLBACK_FAILED"):
            apply_transaction(
                self._approved,
                self.repo,
                self._replan,
                self._apply_action,
                corrupt_then_pass,
            )

        self.assertEqual(b"after\n", (self.repo / "managed.txt").read_bytes())
        self.assertEqual(["validation-started"], self._terminal_phases())

    @unittest.skipUnless(os.name == "posix", "POSIX mode semantics are exact")
    def test_transaction_rollback_restores_exact_posix_mode(self):
        # Arrange
        os.chmod(self.repo / "managed.txt", 0o751)
        observations = tuple(
            dataclasses.replace(item, mode=0o751)
            if item.path == "managed.txt"
            else item
            for item in self._approved.target_observations
        )
        results = tuple(
            dataclasses.replace(item, mode=0o600)
            if item.path == "managed.txt"
            else item
            for item in self._approved.target_results
        )
        approved = plan_with_digest(
            dataclasses.replace(
                self._approved,
                target_observations=observations,
                target_results=results,
            )
        )

        def apply_one(action: Action, mutation) -> None:
            if action.path == "managed.txt":
                mutation.replace_file(action.path, b"after\n", 0o600)

        before = self._payload_snapshot()

        # Act
        with self.assertRaisesRegex(ManagerError, "VALIDATION_FAILED"):
            apply_transaction(
                approved,
                self.repo,
                lambda: approved,
                apply_one,
                lambda _root: ["bad"],
            )

        # Assert
        self.assertEqual(before, self._payload_snapshot())


if __name__ == "__main__":
    unittest.main()
