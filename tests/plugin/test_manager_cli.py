"""Public manager CLI contract tests."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from tests.plugin import helpers as plugin_helpers
from tests.plugin.helpers import (
    PLUGIN,
    init_git_repo,
    run_manager,
    snapshot_tree,
    write_installed_fixture,
)


class PluginFixtureTests(unittest.TestCase):
    def _create_symlink_or_skip(
        self,
        link: Path,
        target: str,
        *,
        target_is_directory: bool = False,
    ) -> None:
        try:
            link.symlink_to(target, target_is_directory=target_is_directory)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")

    def test_copy_plugin_fixture_excludes_only_transient_python_cache_artifacts(self):
        # Arrange
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            (source / "scripts/__pycache__").mkdir(parents=True)
            (source / "scripts/__pycache__/cached.pyc").write_bytes(b"cache")
            (source / "scripts/direct.pyc").write_bytes(b"cache")
            (source / "scripts/direct.pyo").write_bytes(b"cache")
            (source / "ordinary-unexpected.txt").write_bytes(b"preserve me")

            # Act
            plugin_helpers.copy_plugin_fixture(source, destination)

            # Assert
            self.assertFalse((destination / "scripts/__pycache__").exists())
            self.assertFalse((destination / "scripts/direct.pyc").exists())
            self.assertFalse((destination / "scripts/direct.pyo").exists())
            self.assertEqual(
                b"preserve me",
                (destination / "ordinary-unexpected.txt").read_bytes(),
            )

    def test_copy_plugin_fixture_preserves_symlinks_even_with_cache_names(self):
        # Arrange
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            (source / "scripts/cache-target").mkdir(parents=True)
            (source / "scripts/compiled-target.bin").write_bytes(b"compiled")
            (source / "ordinary-target.txt").write_bytes(b"ordinary")
            links = {
                source / "scripts/__pycache__": ("cache-target", True),
                source / "scripts/linked.pyc": ("compiled-target.bin", False),
                source / "ordinary-link": ("ordinary-target.txt", False),
            }
            for link, (target, is_directory) in links.items():
                self._create_symlink_or_skip(
                    link,
                    target,
                    target_is_directory=is_directory,
                )
            source_before = plugin_helpers.snapshot_tree(source)

            # Act
            plugin_helpers.copy_plugin_fixture(source, destination)

            # Assert
            for source_link, (target, _) in links.items():
                copied_link = destination / source_link.relative_to(source)
                self.assertTrue(copied_link.is_symlink())
                self.assertEqual(Path(target), copied_link.readlink())
            self.assertEqual(source_before, plugin_helpers.snapshot_tree(source))

    def test_manager_rejects_symlink_preserving_dirty_plugin_fixture(self):
        # Arrange
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            root = Path(temporary)
            source = root / "source"
            plugin = root / "plugin"
            plugin_helpers.copy_plugin_fixture(PLUGIN, source)
            (source / "fixture-targets/cache-target").mkdir(parents=True)
            (source / "fixture-targets/compiled-target.bin").write_bytes(b"compiled")
            (source / "fixture-targets/ordinary-target.txt").write_bytes(b"ordinary")
            links = {
                source / "assets/studio/__pycache__": (
                    "../../fixture-targets/cache-target",
                    True,
                ),
                source / "assets/studio/linked.pyc": (
                    "../../fixture-targets/compiled-target.bin",
                    False,
                ),
                source / "assets/studio/ordinary-link": (
                    "../../fixture-targets/ordinary-target.txt",
                    False,
                ),
            }
            for link, (target, is_directory) in links.items():
                self._create_symlink_or_skip(
                    link,
                    target,
                    target_is_directory=is_directory,
                )
            plugin_helpers.copy_plugin_fixture(source, plugin)
            repo = root / "repo"
            init_git_repo(repo)

            # Act
            result = run_manager("install", repo, plugin_root=plugin)
            document = json.loads(result.stdout)

            # Assert
            for source_link, (target, _) in links.items():
                copied_link = plugin / source_link.relative_to(source)
                self.assertTrue(copied_link.is_symlink())
                self.assertEqual(Path(target), copied_link.readlink())
            self.assertEqual(1, result.returncode)
            self.assertEqual("INVALID_PAYLOAD", document["status"])
            self.assertFalse(document["wrote"])
            self.assertEqual("", result.stderr)


class ManagerCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        )
        self.repo = Path(self.temporary.name)
        init_git_repo(self.repo)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_lifecycle_action_reuses_transaction_verified_payload_entries(self):
        # Arrange
        import studio_manager

        manifest = studio_manager.load_verified_manifest(PLUGIN)
        entries = {item.path: item for item in manifest.entries}
        entry = entries[".agents/skills/adopt/SKILL.md"]
        action = studio_manager.Action(
            "create",
            entry.path,
            None,
            entry.sha256,
            "create managed payload file",
        )
        mutation = mock.Mock()
        expected = studio_manager.read_file_secure(
            PLUGIN / "assets/studio", entry.path
        )

        # Act
        with mock.patch(
            "studio_manager.load_verified_manifest",
            side_effect=AssertionError("payload was reverified inside an action"),
        ):
            studio_manager._apply_lifecycle_action(
                action,
                mutation,
                self.repo,
                PLUGIN,
                None,
                entries,
            )

        # Assert
        mutation.replace_file.assert_called_once_with(
            entry.path, expected, entry.mode
        )

    def test_lifecycle_action_rejects_payload_changed_after_transaction_verification(self):
        # Arrange
        import studio_manager

        plugin = Path(self.temporary.name) / "plugin"
        plugin_helpers.copy_plugin_fixture(PLUGIN, plugin)
        manifest = studio_manager.load_verified_manifest(plugin)
        entries = {item.path: item for item in manifest.entries}
        entry = entries[".agents/skills/adopt/SKILL.md"]
        action = studio_manager.Action(
            "create",
            entry.path,
            None,
            entry.sha256,
            "create managed payload file",
        )
        source = plugin / "assets/studio" / entry.path
        source.write_bytes(source.read_bytes() + b"\ntampered\n")
        mutation = mock.Mock()

        # Act
        with self.assertRaises(studio_manager.ManagerError) as caught:
            studio_manager._apply_lifecycle_action(
                action,
                mutation,
                self.repo,
                plugin,
                None,
                entries,
            )

        # Assert
        self.assertEqual("INVALID_PAYLOAD", caught.exception.code)
        mutation.replace_file.assert_not_called()

    def test_apply_operation_materializes_one_manifest_bound_payload_snapshot(self):
        # Arrange
        import studio_manager

        planned = json.loads(run_manager("install", self.repo).stdout)
        context = studio_manager.decode_approval_context(
            planned["approval_context"], "install"
        )
        plan = studio_manager.plan_operation(
            "install", self.repo, PLUGIN, context
        )
        transaction_result = object()
        manifest_load = studio_manager.load_manifest
        verified_load = studio_manager.load_verified_manifest

        # Act
        with mock.patch(
            "studio_manager.load_manifest", wraps=manifest_load
        ) as load_manifest, mock.patch(
            "studio_manager.load_verified_manifest", wraps=verified_load
        ) as load_verified, mock.patch(
            "transaction.apply_transaction", return_value=transaction_result
        ):
            actual = studio_manager.apply_operation(
                plan,
                self.repo,
                PLUGIN,
                approval_context=context,
            )

        # Assert
        self.assertIs(transaction_result, actual)
        self.assertEqual(1, load_manifest.call_count)
        self.assertEqual(0, load_verified.call_count)

    def test_install_plan_is_read_only_then_approved_apply_succeeds(self):
        before = snapshot_tree(self.repo)

        planned = run_manager("install", self.repo)
        document = json.loads(planned.stdout)

        self.assertEqual(2, planned.returncode)
        self.assertEqual(before, snapshot_tree(self.repo))
        self.assertEqual("awaiting-approval", document["status"])
        self.assertFalse(document["wrote"])

        self.assertRegex(document["approval_context"], r"^[A-Za-z0-9_-]+$")
        applied = run_manager(
            "install", self.repo, document["digest"], approval_context=document["approval_context"]
        )
        result = json.loads(applied.stdout)

        self.assertEqual(0, applied.returncode, applied.stderr)
        self.assertEqual("success", result["status"])
        self.assertTrue(result["wrote"])
        self.assertIsNone(result["failure_phase"])
        self.assertEqual("$start", result["next_action"])
        self.assertTrue((self.repo / ".codex/codex-game-studios/installation.json").is_file())

    def test_approved_apply_when_source_payload_changes_mid_transaction_uses_verified_snapshot(self):
        # Arrange
        import studio_manager

        plugin_parent = Path(tempfile.mkdtemp(dir=Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(shutil.rmtree, plugin_parent, True)
        plugin = plugin_parent / "plugin"
        plugin_helpers.copy_plugin_fixture(PLUGIN, plugin)
        context = studio_manager.new_approval_context("install")
        plan = studio_manager.plan_operation("install", self.repo, plugin, context)
        source = plugin / "assets/studio/.agents/skills/start/SKILL.md"
        approved_content = source.read_bytes()
        original_apply = studio_manager._apply_lifecycle_action
        source_changed = False

        def apply_then_replace_source(action, mutation, root, active_plugin, state, entries):
            nonlocal source_changed
            original_apply(action, mutation, root, active_plugin, state, entries)
            if not source_changed:
                source.write_bytes(b"concurrent marketplace replacement\n")
                source_changed = True

        # Act
        with mock.patch(
            "studio_manager._apply_lifecycle_action",
            side_effect=apply_then_replace_source,
        ):
            result = studio_manager.apply_operation(
                plan,
                self.repo,
                plugin,
                approval_context=context,
            )

        # Assert
        self.assertEqual("committed", result.status)
        self.assertTrue(source_changed)
        self.assertEqual(
            approved_content,
            (self.repo / ".agents/skills/start/SKILL.md").read_bytes(),
        )

    def test_approved_apply_when_source_payload_changes_before_state_render_uses_verified_snapshot(self):
        # Arrange
        import studio_manager

        plugin_parent = Path(tempfile.mkdtemp(dir=Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(shutil.rmtree, plugin_parent, True)
        plugin = plugin_parent / "plugin"
        plugin_helpers.copy_plugin_fixture(PLUGIN, plugin)
        context = studio_manager.new_approval_context("install")
        plan = studio_manager.plan_operation("install", self.repo, plugin, context)
        source = plugin / "assets/studio/.agents/skills/start/SKILL.md"
        approved_content = source.read_bytes()
        original_render = studio_manager._prospective_state_bytes
        original_validate = studio_manager._validate_prospective
        source_changed = False
        validation_findings = []

        def replace_source_then_render(*args, **kwargs):
            nonlocal source_changed
            if not source_changed:
                source.write_bytes(b"concurrent pre-transaction replacement\n")
                source_changed = True
            return original_render(*args, **kwargs)

        def record_validation(*args, **kwargs):
            findings = original_validate(*args, **kwargs)
            validation_findings.extend(findings)
            return findings

        # Act
        with mock.patch(
            "studio_manager._prospective_state_bytes",
            side_effect=replace_source_then_render,
        ), mock.patch(
            "studio_manager._validate_prospective",
            side_effect=record_validation,
        ):
            try:
                result = studio_manager.apply_operation(
                    plan,
                    self.repo,
                    plugin,
                    approval_context=context,
                )
            except studio_manager.ManagerError as error:
                self.fail(
                    f"unexpected {error.code}; findings={validation_findings!r}"
                )

        # Assert
        self.assertEqual("committed", result.status)
        self.assertTrue(source_changed)
        self.assertEqual(
            approved_content,
            (self.repo / ".agents/skills/start/SKILL.md").read_bytes(),
        )

    def test_verify_is_single_phase_read_only_and_does_not_create_manager_directory(self):
        before = snapshot_tree(self.repo)

        result = run_manager("verify", self.repo)
        document = json.loads(result.stdout)

        self.assertEqual(1, result.returncode)
        self.assertEqual("INVALID_INSTALLATION_STATE", document["status"])
        self.assertFalse(document["wrote"])
        self.assertEqual(before, snapshot_tree(self.repo))
        self.assertFalse((self.repo / ".codex/codex-game-studios").exists())

    def test_verify_json_emits_all_findings_as_ordered_redacted_relative_paths(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)
        first = self.repo / ".agents/skills/start/SKILL.md"
        second = self.repo / ".codex/studio.toml"
        first.write_bytes(b"corrupt-one\n")
        second.write_bytes(b"corrupt-two\n")

        # Act
        result = run_manager("verify", self.repo)
        document = json.loads(result.stdout)

        # Assert
        self.assertEqual(1, result.returncode)
        self.assertEqual("VALIDATION_FAILED", document["status"])
        self.assertEqual([
            {"path": ".agents/skills/start/SKILL.md"},
            {"path": ".codex/studio.toml"},
            {"path": ".codex/studio.toml"},
        ], document["findings"])
        self.assertNotIn(str(self.repo), result.stdout)
        self.assertNotIn("corrupt-one", result.stdout)
        self.assertEqual("", result.stderr)

    def test_stale_digest_returns_stable_redacted_json_error(self):
        planned = json.loads(run_manager("install", self.repo).stdout)
        result = run_manager(
            "install", self.repo, "0" * 64,
            approval_context=planned["approval_context"],
        )
        document = json.loads(result.stdout)

        self.assertEqual(1, result.returncode)
        self.assertEqual("STALE_PLAN", document["status"])
        self.assertNotIn(str(self.repo), result.stdout)
        self.assertNotIn(str(PLUGIN), result.stdout)
        self.assertFalse(document["wrote"])

    def test_approval_context_binds_actual_state_and_transaction_identity(self):
        # Arrange
        planned = json.loads(run_manager("install", self.repo).stdout)

        # Act
        result = run_manager(
            "install", self.repo, planned["digest"],
            approval_context=planned["approval_context"],
        )

        # Assert
        self.assertEqual(0, result.returncode, result.stderr)
        state = json.loads(
            (self.repo / ".codex/codex-game-studios/installation.json").read_text()
        )
        recovery = self.repo / ".codex/codex-game-studios/recovery"
        self.assertEqual(state["transaction_id"], next(recovery.iterdir()).name)
        self.assertRegex(state["installed_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_missing_malformed_tampered_and_replayed_context_fail_without_traceback(self):
        # Arrange
        planned = json.loads(run_manager("install", self.repo).stdout)
        before = snapshot_tree(self.repo)

        # Act / Assert
        for context in (None, "not+shell+safe", planned["approval_context"][:-1] + "A"):
            with self.subTest(context=context):
                result = run_manager(
                    "install", self.repo, planned["digest"], approval_context=context
                )
                self.assertEqual(1, result.returncode)
                self.assertEqual("STALE_PLAN", json.loads(result.stdout)["status"])
                self.assertEqual("", result.stderr)
                self.assertEqual(before, snapshot_tree(self.repo))

        applied = run_manager(
            "install", self.repo, planned["digest"],
            approval_context=planned["approval_context"],
        )
        self.assertEqual(0, applied.returncode, applied.stderr)
        replayed = run_manager(
            "install", self.repo, planned["digest"],
            approval_context=planned["approval_context"],
        )
        self.assertEqual(1, replayed.returncode)
        self.assertEqual("INVALID_INSTALLATION_STATE", json.loads(replayed.stdout)["status"])

    def test_uninstall_rejects_valid_context_with_only_uuid_or_timestamp_swapped(self):
        # Arrange
        import studio_manager
        write_installed_fixture(self.repo, PLUGIN)
        first = json.loads(run_manager("uninstall", self.repo).stdout)
        second = json.loads(run_manager("uninstall", self.repo).stdout)
        first_context = studio_manager.decode_approval_context(
            first["approval_context"], "uninstall"
        )
        second_context = studio_manager.decode_approval_context(
            second["approval_context"], "uninstall"
        )
        variants = (
            studio_manager.dataclasses.replace(
                first_context, transaction_id=second_context.transaction_id
            ),
            studio_manager.dataclasses.replace(
                first_context, installed_at="2026-07-13T23:59:59Z"
            ),
        )

        # Act / Assert
        for context in variants:
            result = run_manager(
                "uninstall", self.repo, first["digest"],
                approval_context=studio_manager.encode_approval_context(context),
            )
            self.assertEqual(1, result.returncode)
            self.assertEqual("STALE_PLAN", json.loads(result.stdout)["status"])
            self.assertEqual("", result.stderr)

    def test_rolled_back_failure_json_authoritatively_reports_prior_write(self):
        # Arrange
        import contextlib
        import io
        import studio_manager
        plugin_parent = Path(tempfile.mkdtemp(dir=Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(shutil.rmtree, plugin_parent, True)
        plugin = plugin_parent / "plugin"
        plugin_helpers.copy_plugin_fixture(PLUGIN, plugin)
        planned = json.loads(run_manager("install", self.repo, plugin_root=plugin).stdout)
        stream = io.StringIO()

        # Act
        with mock.patch(
            "studio_manager.apply_operation",
            side_effect=studio_manager.ManagerError(
                "VALIDATION_FAILED", "redacted", wrote=True
            ),
        ), contextlib.redirect_stdout(stream):
            code = studio_manager.main([
                "install", "--root", str(self.repo),
                "--plugin-root", str(plugin),
                "--approve-digest", planned["digest"],
                "--approval-context", planned["approval_context"],
            ])

        # Assert
        document = json.loads(stream.getvalue())
        self.assertEqual(1, code)
        self.assertEqual("VALIDATION_FAILED", document["status"])
        self.assertTrue(document["wrote"])
        self.assertNotIn(str(self.repo), stream.getvalue())

    def test_rollback_failed_json_emits_trusted_relative_recovery_object(self):
        # Arrange
        import contextlib
        import io
        import studio_manager
        plugin_parent = Path(tempfile.mkdtemp(dir=Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(shutil.rmtree, plugin_parent, True)
        plugin = plugin_parent / "plugin"
        plugin_helpers.copy_plugin_fixture(PLUGIN, plugin)
        planned = json.loads(run_manager("install", self.repo, plugin_root=plugin).stdout)
        transaction_id = studio_manager.decode_approval_context(
            planned["approval_context"], "install"
        ).transaction_id
        generation = f".codex/codex-game-studios/recovery/{transaction_id}"
        recovery = {
            "generation": generation,
            "journal": f"{generation}/journal.json",
            "snapshots": f"{generation}/snapshots",
            "phase": "ROLLBACK_FAILED",
            "status": "retained",
        }
        stream = io.StringIO()

        # Act
        with mock.patch(
            "studio_manager.apply_operation",
            side_effect=studio_manager.ManagerError(
                "ROLLBACK_FAILED", "redacted", wrote=True, recovery=recovery
            ),
        ), contextlib.redirect_stdout(stream):
            code = studio_manager.main([
                "install", "--root", str(self.repo),
                "--plugin-root", str(plugin),
                "--approve-digest", planned["digest"],
                "--approval-context", planned["approval_context"],
            ])

        # Assert
        document = json.loads(stream.getvalue())
        self.assertEqual(1, code)
        self.assertEqual("ROLLBACK_FAILED", document["status"])
        self.assertEqual(recovery, document["recovery"])
        self.assertTrue(document["wrote"])
        self.assertNotIn(str(self.repo), stream.getvalue())

    def test_subprocess_validation_filesystem_failure_rolls_back_with_stable_json(self):
        # Arrange: create a self-consistent embedded payload whose validator
        # deterministically raises an expected safe filesystem exception.
        plugin_parent = Path(tempfile.mkdtemp(dir=Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(shutil.rmtree, plugin_parent, True)
        plugin = plugin_parent / "plugin"
        plugin_helpers.copy_plugin_fixture(PLUGIN, plugin)
        validator = plugin / "assets/studio/tools/codex_studio/validate.py"
        validator.write_bytes(validator.read_bytes() + b"\n\ndef _validate_installed_repository_secure(root):\n    raise OSError('injected /private/secret failure')\n")
        manifest_path = plugin / "assets/payload-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = next(
            item for item in manifest["entries"]
            if item["path"] == "tools/codex_studio/validate.py"
        )
        entry["sha256"] = hashlib.sha256(validator.read_bytes()).hexdigest()
        body = {key: value for key, value in manifest.items() if key != "digest"}
        from models import canonical_json
        manifest["digest"] = hashlib.sha256(canonical_json(body)).hexdigest()
        manifest_path.write_bytes(canonical_json(manifest))
        before = snapshot_tree(self.repo)
        planned = json.loads(run_manager("install", self.repo, plugin_root=plugin).stdout)

        # Act
        result = run_manager(
            "install", self.repo, planned["digest"], plugin,
            planned["approval_context"],
        )
        document = json.loads(result.stdout)

        # Assert
        self.assertEqual(1, result.returncode)
        self.assertEqual("UNSAFE_PATH", document["status"])
        self.assertTrue(document["wrote"])
        self.assertEqual("installed-validation", document["failure_phase"])
        self.assertEqual("", result.stderr)
        self.assertNotIn(str(self.repo), result.stdout)
        self.assertNotIn("secret", result.stdout)
        after = {
            path: value for path, value in snapshot_tree(self.repo).items()
            if not path.startswith(".codex/codex-game-studios")
            and path not in {".codex"}
        }
        self.assertEqual(before, after)

        replayed = run_manager(
            "install", self.repo, planned["digest"], plugin,
            planned["approval_context"],
        )
        self.assertEqual(1, replayed.returncode)
        self.assertEqual("STALE_PLAN", json.loads(replayed.stdout)["status"])
        self.assertEqual("", replayed.stderr)

    def test_subprocess_payload_failure_before_write_has_stable_error_boundary(self):
        # Arrange
        plugin_parent = Path(tempfile.mkdtemp(dir=Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(shutil.rmtree, plugin_parent, True)
        plugin = plugin_parent / "plugin"
        plugin_helpers.copy_plugin_fixture(PLUGIN, plugin)
        manifest = plugin / "assets/payload-manifest.json"
        manifest.write_bytes(manifest.read_bytes().replace(b'"digest":"', b'"digest":"0', 1))
        before = snapshot_tree(self.repo)

        # Act
        result = run_manager("install", self.repo, plugin_root=plugin)
        document = json.loads(result.stdout)

        # Assert
        self.assertEqual(1, result.returncode)
        self.assertEqual("INVALID_PAYLOAD", document["status"])
        self.assertFalse(document["wrote"])
        self.assertEqual("planning", document["failure_phase"])
        self.assertEqual([], document["findings"])
        self.assertEqual("", result.stderr)
        self.assertNotIn(str(plugin), result.stdout)
        self.assertEqual(before, snapshot_tree(self.repo))

    def test_verify_subprocess_filesystem_failure_before_validator_return_is_stable(self):
        # Arrange: build a self-consistent plugin fixture whose installed
        # validator raises before returning its result or state bytes.
        plugin_parent = Path(tempfile.mkdtemp(dir=Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(shutil.rmtree, plugin_parent, True)
        plugin = plugin_parent / "plugin"
        plugin_helpers.copy_plugin_fixture(PLUGIN, plugin)
        validator = plugin / "assets/studio/tools/codex_studio/validate.py"
        secret = "/private/verify-secret"
        validator.write_bytes(
            validator.read_bytes()
            + f"\n\ndef _validate_installed_repository_secure(root):\n    raise OSError('{secret}')\n".encode()
        )
        manifest_path = plugin / "assets/payload-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = next(
            item for item in manifest["entries"]
            if item["path"] == "tools/codex_studio/validate.py"
        )
        entry["sha256"] = hashlib.sha256(validator.read_bytes()).hexdigest()
        body = {key: value for key, value in manifest.items() if key != "digest"}
        from models import canonical_json
        manifest["digest"] = hashlib.sha256(canonical_json(body)).hexdigest()
        manifest_path.write_bytes(canonical_json(manifest))
        write_installed_fixture(self.repo, plugin)
        before = snapshot_tree(self.repo)

        # Act
        result = run_manager("verify", self.repo, plugin_root=plugin)
        document = json.loads(result.stdout)

        # Assert
        self.assertEqual(1, result.returncode)
        self.assertEqual("UNSAFE_PATH", document["status"])
        self.assertFalse(document["wrote"])
        self.assertEqual("installed-validation", document["failure_phase"])
        self.assertEqual("", result.stderr)
        self.assertEqual(canonical_json(document).decode("utf-8"), result.stdout)
        self.assertNotIn(str(self.repo), result.stdout)
        self.assertNotIn(secret, result.stdout)
        self.assertNotIn("verify-secret", result.stdout)
        self.assertEqual(before, snapshot_tree(self.repo))

    def test_verify_subprocess_validator_payload_failure_is_installation_state_error(self):
        # Arrange: make the installed validator raise the path-model error used
        # for malformed installed-state paths after payload planning succeeds.
        plugin_parent = Path(tempfile.mkdtemp(dir=Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(shutil.rmtree, plugin_parent, True)
        plugin = plugin_parent / "plugin"
        plugin_helpers.copy_plugin_fixture(PLUGIN, plugin)
        validator = plugin / "assets/studio/tools/codex_studio/validate.py"
        validator.write_bytes(
            validator.read_bytes()
            + b"\n\ndef _validate_installed_repository_secure(root):\n"
            + b"    from models import PayloadError\n"
            + b"    raise PayloadError('/private/state-secret')\n"
        )
        manifest_path = plugin / "assets/payload-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = next(
            item for item in manifest["entries"]
            if item["path"] == "tools/codex_studio/validate.py"
        )
        entry["sha256"] = hashlib.sha256(validator.read_bytes()).hexdigest()
        from models import canonical_json
        body = {key: value for key, value in manifest.items() if key != "digest"}
        manifest["digest"] = hashlib.sha256(canonical_json(body)).hexdigest()
        manifest_path.write_bytes(canonical_json(manifest))
        write_installed_fixture(self.repo, plugin)

        # Act
        result = run_manager("verify", self.repo, plugin_root=plugin)
        document = json.loads(result.stdout)

        # Assert
        self.assertEqual(1, result.returncode)
        self.assertEqual("INVALID_INSTALLATION_STATE", document["status"])
        self.assertFalse(document["wrote"])
        self.assertEqual("", result.stderr)
        self.assertNotIn("state-secret", result.stdout)

    def test_approved_apply_subprocess_state_render_filesystem_failure_is_stable(self):
        # Arrange: plan with a private plugin fixture, then inject a deterministic
        # pre-transaction failure in prospective state rendering for approved apply.
        plugin_parent = Path(tempfile.mkdtemp(dir=Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(shutil.rmtree, plugin_parent, True)
        plugin = plugin_parent / "plugin"
        plugin_helpers.copy_plugin_fixture(PLUGIN, plugin)
        planned = json.loads(run_manager("install", self.repo, plugin_root=plugin).stdout)
        manager = plugin / "scripts/studio_manager.py"
        source = manager.read_text(encoding="utf-8")
        marker = (
            ") -> bytes:\n"
            "    if plan.operation == \"migrate\":"
        )
        replacement = (
            ") -> bytes:\n"
            "    if '--approve-digest' in sys.argv:\n"
            "        raise OSError('/private/apply-secret')\n"
            "    if plan.operation == \"migrate\":"
        )
        self.assertIn(marker, source)
        manager.write_text(source.replace(marker, replacement, 1), encoding="utf-8")
        before = snapshot_tree(self.repo)

        # Act
        result = run_manager(
            "install", self.repo, planned["digest"], plugin,
            planned["approval_context"],
        )
        document = json.loads(result.stdout)

        # Assert
        self.assertEqual(1, result.returncode)
        self.assertEqual("UNSAFE_PATH", document["status"])
        self.assertFalse(document["wrote"])
        self.assertEqual("state-render", document["failure_phase"])
        self.assertEqual("", result.stderr)
        from models import canonical_json
        self.assertEqual(canonical_json(document).decode("utf-8"), result.stdout)
        self.assertNotIn(str(self.repo), result.stdout)
        self.assertNotIn("apply-secret", result.stdout)
        self.assertEqual(before, snapshot_tree(self.repo))

    def test_subprocess_unicode_and_toml_merge_failures_are_stable_and_redacted(self):
        # Arrange / Act / Assert
        for content in (b"\xff\n", b"[agents\n"):
            with self.subTest(content=content):
                write_installed_fixture(self.repo, PLUGIN)
                target = self.repo / ".codex/config.toml"
                target.write_bytes(content)
                result = run_manager("update", self.repo)
                document = json.loads(result.stdout)
                self.assertEqual(1, result.returncode)
                self.assertEqual("CUSTOMIZED_MANAGED_FILE", document["status"])
                self.assertFalse(document["wrote"])
                self.assertEqual("", result.stderr)
                self.assertNotIn(str(self.repo), result.stdout)


if __name__ == "__main__":
    unittest.main()
