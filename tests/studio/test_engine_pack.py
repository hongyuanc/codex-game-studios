from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

from tools.codex_studio.engine_pack import (
    apply_activation,
    load_studio_config,
    plan_activation,
    recover_activation,
    _serialize_config,
    validate_activation,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGETS = {
    "godot": ("4.6", "gdscript"),
    "unity": ("6000.1", "csharp"),
    "unreal": ("5.7", "cpp"),
}


class FakeWindowsDirectoryApi:
    """Deterministic native-handle surface for engine-pack identity tests."""

    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_SHARE_READ = 0x1
    FILE_SHARE_WRITE = 0x2
    FILE_SHARE_DELETE = 0x4

    def __init__(self) -> None:
        self.change_times: dict[str, int] = {}
        self.file_ids: dict[str, int] = {}
        self.creation_times: dict[str, int] = {}
        self.opened: list[int] = []
        self.closed: list[int] = []
        self.handles: dict[int, str] = {}
        self.fail_info = False
        self.reparse_paths: set[str] = set()
        self.open_calls: list[tuple[str, int, int]] = []

    def open(self, path: str, *, flags: int, share: int) -> int:
        handle = 100 + len(self.opened)
        self.opened.append(handle)
        self.handles[handle] = path
        self.open_calls.append((path, flags, share))
        return handle

    def info(self, handle: int):
        if self.fail_info:
            raise OSError("mock GetFileInformationByHandleEx failure")
        path = self.handles[handle]
        return types.SimpleNamespace(
            volume=7,
            file_id=self.file_ids.setdefault(path, len(self.file_ids) + 1),
            creation_time=self.creation_times.setdefault(path, 1_000),
            change_time=self.change_times.setdefault(path, 2_000),
            directory=True,
            reparse=path in self.reparse_paths,
            disk=True,
        )

    def close(self, handle: int) -> None:
        self.closed.append(handle)
        self.handles.pop(handle, None)


def complete_plan(root: Path, engine: str):
    version, language = DEFAULT_TARGETS[engine]
    return plan_activation(root, engine, version=version, language=language)


def tree_bytes(root: Path) -> dict[str, tuple[str, bytes | str]]:
    result: dict[str, tuple[str, bytes | str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == ".codex/engine-pack.lock":
            continue
        if path.is_symlink():
            result[relative] = ("symlink", os.readlink(path))
        elif path.is_file():
            result[relative] = ("file", path.read_bytes())
        elif path.is_dir():
            result[relative] = ("dir", b"")
    return result


class EnginePackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name) / "project"
        shutil.copytree(ROOT / "tests/studio/fixtures/engine-project", self.project)
        shutil.copytree(ROOT / ".codex/agent-packs", self.project / ".codex/agent-packs")

    def tearDown(self):
        self.temp.cleanup()

    def leave_incomplete_recovery(self, *, configured: bool = False) -> Path:
        if configured:
            apply_activation(
                self.project,
                plan_activation(self.project, "godot", version="4.6", language="gdscript"),
            )
            plan = plan_activation(self.project, "unity", version="6000.1", language="csharp")
        else:
            plan = plan_activation(self.project, "godot", version="4.6", language="gdscript")

        def fail_after_copy(phase: str) -> None:
            if phase == "copy":
                raise OSError("original failure")

        with mock.patch("tools.codex_studio.engine_pack._checkpoint", side_effect=fail_after_copy):
            with mock.patch("tools.codex_studio.engine_pack._restore_backup", side_effect=OSError("rollback failure")):
                with self.assertRaises(RuntimeError):
                    apply_activation(self.project, plan)
        return self.project / ".codex/engine-pack-recovery"

    def test_engine_pack_content_descriptors_request_binary_mode(self):
        # Arrange
        from tools.codex_studio import engine_pack

        binary = 0x8000
        file_metadata = type(
            "FileMetadata",
            (),
            {"st_mode": stat.S_IFREG | 0o644, "st_dev": 7, "st_ino": 11},
        )()
        directory_metadata = type(
            "DirectoryMetadata",
            (),
            {"st_mode": stat.S_IFDIR | 0o755, "st_dev": 7, "st_ino": 10},
        )()

        # Act
        with mock.patch.object(
            engine_pack.os, "O_BINARY", binary, create=True
        ), mock.patch.object(
            engine_pack, "_checked_lstat", return_value=file_metadata
        ), mock.patch.object(
            engine_pack.os, "open", return_value=51
        ) as read_open, mock.patch.object(
            engine_pack.os, "fstat", return_value=file_metadata
        ), mock.patch.object(
            engine_pack.os, "read", side_effect=(b"profile\n", b"")
        ), mock.patch.object(engine_pack.os, "close"):
            self.assertEqual(
                b"profile\n",
                engine_pack._secure_read(Path("profile.toml"), "profile"),
            )

        with mock.patch.object(
            engine_pack.os, "O_BINARY", binary, create=True
        ), mock.patch.object(
            engine_pack, "_require_directory", return_value=directory_metadata
        ), mock.patch.object(
            engine_pack, "_checked_lstat", side_effect=(None, file_metadata)
        ), mock.patch.object(
            engine_pack.os, "supports_dir_fd", set()
        ), mock.patch.object(
            engine_pack.os, "open", return_value=52
        ) as write_open, mock.patch.object(
            engine_pack.os, "fstat", return_value=file_metadata
        ), mock.patch.object(
            engine_pack.os, "write", return_value=len(b"profile\n")
        ), mock.patch.object(engine_pack.os, "fsync"), mock.patch.object(
            engine_pack.os, "close"
        ):
            engine_pack._exclusive_profile_write(
                Path("agents"), "profile.toml", b"profile\n"
            )

        # Assert
        self.assertTrue(read_open.call_args.args[1] & binary)
        self.assertTrue(write_open.call_args.args[1] & binary)

    def test_engine_pack_profile_round_trip_preserves_raw_disk_bytes(self):
        # Arrange
        from tools.codex_studio import engine_pack

        agents = Path(self.temp.name) / "binary-agents"
        agents.mkdir()
        content = b"name = 'profile'\r\nnotes = 'line-feed:\n'\n"

        # Act
        engine_pack._exclusive_profile_write(agents, "profile.toml", content)
        observed = engine_pack._secure_read(agents / "profile.toml", "profile")

        # Assert
        self.assertEqual(content, observed)
        self.assertEqual(content, (agents / "profile.toml").read_bytes())

    def test_supported_packs_are_exactly_three_with_five_profiles_each(self):
        packs = self.project / ".codex/agent-packs"
        self.assertEqual(["godot", "unity", "unreal"], sorted(path.name for path in packs.iterdir()))
        for pack in packs.iterdir():
            self.assertEqual(5, len(list(pack.glob("*.toml"))))

    def test_fresh_project_is_unconfigured(self):
        self.assertEqual("unconfigured", load_studio_config(self.project).engine)

    def test_dry_plan_is_deterministic_complete_and_read_only(self):
        before = tree_bytes(self.project)
        first = plan_activation(self.project, "godot", version="4.6", language="gdscript")
        second = plan_activation(self.project, "godot", version="4.6", language="gdscript")
        self.assertEqual(first, second)
        self.assertEqual(5, len(first.install))
        self.assertEqual((), first.remove)
        self.assertEqual("4.6", first.target_config.engine_version)
        self.assertEqual(before, tree_bytes(self.project))

    def test_activation_updates_manifest_studio_and_exactly_five_profiles(self):
        apply_activation(self.project, plan_activation(self.project, "unity", version="6000.1", language="csharp"))
        self.assertEqual("unity", load_studio_config(self.project).engine)
        active = list((self.project / ".codex/agents").glob("*.toml"))
        self.assertEqual(5, len(active))
        manifest = json.loads((self.project / ".codex/active-engine.json").read_text(encoding="utf-8"))
        self.assertEqual("unity", manifest["engine"])
        self.assertEqual(5, len(manifest["generated"]))
        self.assertEqual([], validate_activation(self.project))

    def test_switch_preserves_unmanaged_agent(self):
        agents = self.project / ".codex/agents"
        agents.mkdir(parents=True, exist_ok=True)
        custom = agents / "my-agent.toml"
        custom.write_text('name = "my-agent"\n', encoding="utf-8")
        apply_activation(self.project, complete_plan(self.project, "godot"))
        apply_activation(self.project, complete_plan(self.project, "unreal"))
        self.assertEqual('name = "my-agent"\n', custom.read_text(encoding="utf-8"))
        self.assertEqual(5, len(list(agents.glob("ue-*.toml"))) + len(list(agents.glob("unreal-*.toml"))))

    def test_unmanaged_name_collision_is_rejected(self):
        target = self.project / ".codex/agents/godot-specialist.toml"
        target.parent.mkdir(parents=True)
        target.write_text("unmanaged", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unmanaged profile collision"):
            complete_plan(self.project, "godot")

    def test_modified_generated_profile_blocks_switch(self):
        apply_activation(self.project, complete_plan(self.project, "godot"))
        generated = next((self.project / ".codex/agents").glob("godot-*.toml"))
        generated.write_text(generated.read_text(encoding="utf-8") + "\n# user edit\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "generated profile was modified"):
            complete_plan(self.project, "unity")

    def test_symlinked_pack_profile_and_target_are_rejected(self):
        source = self.project / ".codex/agent-packs/godot/godot-specialist.toml"
        original = source.read_bytes()
        real_source = self.project / "outside-profile.toml"
        real_source.write_bytes(original)
        source.unlink()
        source.symlink_to(real_source)
        with self.assertRaisesRegex(ValueError, "symlink"):
            complete_plan(self.project, "godot")
        source.unlink()
        source.write_bytes(original)
        target = self.project / ".codex/agents/godot-specialist.toml"
        target.parent.mkdir(parents=True)
        target.symlink_to(source)
        with self.assertRaisesRegex(ValueError, "symlink"):
            complete_plan(self.project, "godot")

    def test_symlinked_codex_control_directory_is_rejected(self):
        codex = self.project / ".codex"
        relocated = self.project / "relocated-codex"
        codex.rename(relocated)
        codex.symlink_to(relocated.name, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "control directory.*symlink"):
            complete_plan(self.project, "godot")

    def test_symlinked_project_root_pack_root_and_selected_pack_are_rejected(self):
        alias = self.project.parent / "project-alias"
        alias.symlink_to(self.project, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "project root.*symlink"):
            plan_activation(alias, "godot")
        for relative in (Path(".codex/agent-packs"), Path(".codex/agent-packs/godot")):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "project"
                shutil.copytree(self.project, project)
                path = project / relative
                relocated = project / f"relocated-{path.name}"
                path.rename(relocated)
                path.symlink_to(relocated, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, "symlink|junction|reparse"):
                    complete_plan(project, "godot")

    def test_malformed_config_and_manifest_are_rejected(self):
        config = self.project / ".codex/studio.toml"
        config.write_text("engine = [\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "studio config"):
            complete_plan(self.project, "godot")
        shutil.copy2(ROOT / "tests/studio/fixtures/engine-project/.codex/studio.toml", config)
        (self.project / ".codex/active-engine.json").write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "active-engine manifest"):
            complete_plan(self.project, "godot")

    def test_manifest_traversal_and_invalid_hash_are_rejected(self):
        manifest = self.project / ".codex/active-engine.json"
        manifest.write_text(
            json.dumps({"engine": "godot", "generated": {"../outside.toml": "0" * 64}}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "filename"):
            complete_plan(self.project, "unity")
        manifest.write_text(
            json.dumps({"engine": "godot", "generated": {"godot-specialist.toml": "bad"}}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "hash"):
            complete_plan(self.project, "unity")

    def test_forged_manifest_cannot_claim_unmanaged_profiles(self):
        apply_activation(self.project, complete_plan(self.project, "godot"))
        agents = self.project / ".codex/agents"
        generated = {}
        for index in range(5):
            name = f"custom-{index}.toml"
            content = f"custom {index}".encode()
            (agents / name).write_bytes(content)
            generated[name] = hashlib.sha256(content).hexdigest()
        (self.project / ".codex/active-engine.json").write_text(
            json.dumps({"engine": "godot", "generated": generated}), encoding="utf-8"
        )
        before = tree_bytes(self.project)
        with self.assertRaisesRegex(ValueError, "immutable source pack"):
            complete_plan(self.project, "unity")
        self.assertEqual(before, tree_bytes(self.project))

    def test_unsafe_source_filename_is_rejected_before_pack_count_authorization(self):
        pack = self.project / ".codex/agent-packs/godot"
        source = next(pack.iterdir())
        source.rename(pack / "bad\\name.toml")
        with self.assertRaisesRegex(ValueError, "filename"):
            complete_plan(self.project, "godot")

    def test_windows_style_manifest_traversal_is_rejected(self):
        generated = {"..\\outside.toml": "0" * 64}
        generated.update({f"safe-{index}.toml": "0" * 64 for index in range(4)})
        (self.project / ".codex/active-engine.json").write_text(
            json.dumps({"engine": "godot", "generated": generated}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "filename"):
            complete_plan(self.project, "unity")

    def test_stale_plan_and_changed_source_pack_are_rejected_without_mutation(self):
        plan = complete_plan(self.project, "godot")
        custom = self.project / ".codex/agents/custom.toml"
        custom.parent.mkdir(parents=True)
        custom.write_text("changed", encoding="utf-8")
        before = tree_bytes(self.project)
        with self.assertRaisesRegex(ValueError, "stale activation plan"):
            apply_activation(self.project, plan)
        self.assertEqual(before, tree_bytes(self.project))
        custom.unlink()
        plan = complete_plan(self.project, "godot")
        source = plan.install[0]
        source.write_bytes(source.read_bytes() + b"\n# source drift\n")
        before = tree_bytes(self.project)
        with self.assertRaisesRegex(ValueError, "source pack changed"):
            apply_activation(self.project, plan)
        self.assertEqual(before, tree_bytes(self.project))

    def test_forged_plan_cannot_remove_a_path_outside_managed_agents(self):
        important = self.project / "important.txt"
        important.write_text("preserve me", encoding="utf-8")
        plan = complete_plan(self.project, "godot")
        forged = dataclasses.replace(plan, remove=(important,))
        before = tree_bytes(self.project)
        with self.assertRaisesRegex(ValueError, "activation plan"):
            apply_activation(self.project, forged)
        self.assertEqual(before, tree_bytes(self.project))

    def test_same_engine_same_configuration_is_byte_idempotent(self):
        plan = plan_activation(self.project, "unreal", version="5.7", language="cpp-blueprint")
        apply_activation(self.project, plan)
        before = tree_bytes(self.project)
        repeat = plan_activation(self.project, "unreal", version="5.7", language="cpp-blueprint")
        self.assertTrue(repeat.no_op)
        apply_activation(self.project, repeat)
        self.assertEqual(before, tree_bytes(self.project))

    def test_same_engine_config_only_update_preserves_manifest_and_profiles(self):
        apply_activation(self.project, plan_activation(self.project, "godot", version="4.5", language="gdscript"))
        manifest = self.project / ".codex/active-engine.json"
        profiles = {path.name: path.read_bytes() for path in (self.project / ".codex/agents").iterdir()}
        manifest_bytes = manifest.read_bytes()
        update = plan_activation(self.project, "godot", version="4.6", language="gdscript")
        self.assertEqual((), update.install)
        self.assertEqual((), update.remove)
        apply_activation(self.project, update)
        self.assertEqual(manifest_bytes, manifest.read_bytes())
        self.assertEqual(profiles, {path.name: path.read_bytes() for path in (self.project / ".codex/agents").iterdir()})
        self.assertEqual("4.6", load_studio_config(self.project).engine_version)

    def test_each_mutation_failure_rolls_back_byte_for_byte(self):
        phases = ("remove", "copy", "manifest-write", "second-replace", "config-write", "post-validation")
        for phase in phases:
            with self.subTest(phase=phase):
                apply_activation(self.project, complete_plan(self.project, "godot"))
                before = tree_bytes(self.project)
                plan = complete_plan(self.project, "unity")

                def fail(selected: str) -> None:
                    if selected == phase:
                        raise OSError(f"injected {phase} failure")

                with mock.patch("tools.codex_studio.engine_pack._checkpoint", side_effect=fail):
                    with self.assertRaisesRegex(OSError, f"injected {phase} failure"):
                        apply_activation(self.project, plan)
                self.assertEqual(before, tree_bytes(self.project))

    def test_absent_manifest_and_agents_directory_are_restored_on_failure(self):
        before = tree_bytes(self.project)

        def fail(phase: str) -> None:
            if phase == "copy":
                raise OSError("fresh failure")

        with mock.patch("tools.codex_studio.engine_pack._checkpoint", side_effect=fail):
            with self.assertRaisesRegex(OSError, "fresh failure"):
                apply_activation(self.project, complete_plan(self.project, "godot"))
        self.assertEqual(before, tree_bytes(self.project))

    def test_actual_copy_replace_write_and_validation_failures_rollback(self):
        failure_cases = ("copy", "second-replace", "manifest-write", "config-write", "post-validation")
        for failure_case in failure_cases:
            with self.subTest(failure_case=failure_case):
                before = tree_bytes(self.project)
                plan = complete_plan(self.project, "godot")
                def fail(selected: str) -> None:
                    if selected == failure_case:
                        raise OSError(f"actual {failure_case} failure")

                with mock.patch("tools.codex_studio.engine_pack._checkpoint", side_effect=fail):
                    with self.assertRaises((OSError, ValueError)):
                        apply_activation(self.project, plan)
                self.assertEqual(before, tree_bytes(self.project))

    def test_actual_remove_failure_rolls_back(self):
        apply_activation(self.project, complete_plan(self.project, "godot"))
        before = tree_bytes(self.project)
        plan = complete_plan(self.project, "unity")
        with mock.patch(
            "tools.codex_studio.engine_pack._unlink_managed",
            create=True,
            side_effect=OSError("actual remove failure"),
        ):
            with self.assertRaisesRegex(OSError, "actual remove failure"):
                apply_activation(self.project, plan)
        self.assertEqual(before, tree_bytes(self.project))

    def test_mid_copy_and_second_control_replace_failures_restore_logical_state(self):
        for failure_case in ("mid-copy", "second-control-replace"):
            with self.subTest(failure_case=failure_case), tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "project"
                shutil.copytree(self.project, project)
                before = tree_bytes(project)
                plan = complete_plan(project, "godot")
                if failure_case == "mid-copy":
                    from tools.codex_studio import engine_pack

                    real_write = engine_pack._exclusive_profile_write
                    calls = 0

                    def fail_third(agents, name, content):
                        nonlocal calls
                        calls += 1
                        if calls == 3:
                            raise OSError("mid-copy failure")
                        return real_write(agents, name, content)

                    patcher = mock.patch("tools.codex_studio.engine_pack._exclusive_profile_write", side_effect=fail_third)
                else:
                    from tools.codex_studio import engine_pack

                    real_replace = engine_pack.os.replace
                    control_replaces = 0

                    def fail_second(source, destination):
                        nonlocal control_replaces
                        if Path(destination).name in {"active-engine.json", "studio.toml"}:
                            control_replaces += 1
                            if control_replaces == 2:
                                raise OSError("second control replace failure")
                        return real_replace(source, destination)

                    patcher = mock.patch("tools.codex_studio.engine_pack.os.replace", side_effect=fail_second)
                with patcher:
                    with self.assertRaisesRegex(OSError, "mid-copy|second control replace"):
                        apply_activation(project, plan)
                self.assertEqual(before, tree_bytes(project))

    def test_post_validation_failure_restores_logical_state(self):
        before = tree_bytes(self.project)
        plan = complete_plan(self.project, "godot")
        with mock.patch("tools.codex_studio.engine_pack.validate_activation", return_value=["injected invalid state"]):
            with self.assertRaisesRegex(ValueError, "post-apply validation failed"):
                apply_activation(self.project, plan)
        self.assertEqual(before, tree_bytes(self.project))

    def test_target_created_after_locked_revalidation_is_preserved_and_blocks_apply(self):
        plan = complete_plan(self.project, "godot")
        target = self.project / ".codex/agents/godot-specialist.toml"

        def inject(phase: str) -> None:
            if phase == "after-revalidation":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("concurrent unmanaged", encoding="utf-8")

        with mock.patch("tools.codex_studio.engine_pack._checkpoint", side_effect=inject):
            with self.assertRaisesRegex(ValueError, "collision|concurrent"):
                apply_activation(self.project, plan)
        self.assertEqual("concurrent unmanaged", target.read_text(encoding="utf-8"))

    def test_exclusive_destination_fallback_without_dir_fd_is_safe(self):
        from tools.codex_studio import engine_pack

        with mock.patch.object(engine_pack.os, "supports_dir_fd", set()):
            apply_activation(self.project, complete_plan(self.project, "godot"))
        self.assertEqual([], validate_activation(self.project))

    def test_symlink_created_after_locked_revalidation_cannot_escape(self):
        plan = complete_plan(self.project, "godot")
        target = self.project / ".codex/agents/godot-specialist.toml"
        outside = self.project / "outside.txt"
        outside.write_text("outside", encoding="utf-8")

        def inject(phase: str) -> None:
            if phase == "after-revalidation":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(outside)

        with mock.patch("tools.codex_studio.engine_pack._checkpoint", side_effect=inject):
            with self.assertRaisesRegex(ValueError, "collision|symlink|concurrent"):
                apply_activation(self.project, plan)
        self.assertTrue(target.is_symlink())
        self.assertEqual("outside", outside.read_text(encoding="utf-8"))

    def test_second_same_project_activation_cannot_enter_transaction(self):
        plan = complete_plan(self.project, "godot")
        entered = threading.Event()
        release = threading.Event()
        failures = []

        def pause(phase: str) -> None:
            if phase == "after-revalidation":
                entered.set()
                release.wait(5)

        def first() -> None:
            try:
                with mock.patch("tools.codex_studio.engine_pack._checkpoint", side_effect=pause):
                    apply_activation(self.project, plan)
            except BaseException as error:
                failures.append(error)

        thread = threading.Thread(target=first)
        thread.start()
        self.assertTrue(entered.wait(5))
        try:
            with self.assertRaisesRegex(ValueError, "activation.*locked"):
                apply_activation(self.project, plan)
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], failures)

    def test_rollback_failure_preserves_journal_and_can_be_recovered(self):
        plan = complete_plan(self.project, "godot")
        def fail_after_copy(phase: str) -> None:
            if phase == "copy":
                raise OSError("original failure")

        with mock.patch("tools.codex_studio.engine_pack._checkpoint", side_effect=fail_after_copy):
            with mock.patch("tools.codex_studio.engine_pack._restore_backup", side_effect=OSError("rollback failure")):
                with self.assertRaisesRegex(RuntimeError, "original failure.*rollback failure"):
                    apply_activation(self.project, plan)
        recovery = self.project / ".codex/engine-pack-recovery"
        self.assertTrue((recovery / "journal.json").is_file())
        self.assertTrue((recovery / "backup-agents").is_dir() or (recovery / "agents-absent").is_file())
        self.assertTrue(any("recovery" in issue for issue in validate_activation(self.project)))
        with self.assertRaisesRegex(ValueError, "--recover"):
            complete_plan(self.project, "unity")
        recover_activation(self.project)
        self.assertFalse(recovery.exists())
        self.assertEqual("unconfigured", load_studio_config(self.project).engine)

    def test_corrupt_recovery_backup_is_never_consumed_or_deleted(self):
        plan = complete_plan(self.project, "godot")

        def fail_after_copy(phase: str) -> None:
            if phase == "copy":
                raise OSError("original failure")

        with mock.patch("tools.codex_studio.engine_pack._checkpoint", side_effect=fail_after_copy):
            with mock.patch("tools.codex_studio.engine_pack._restore_backup", side_effect=OSError("rollback failure")):
                with self.assertRaises(RuntimeError):
                    apply_activation(self.project, plan)
        recovery = self.project / ".codex/engine-pack-recovery"
        backup = recovery / "backup-config"
        backup.write_bytes(backup.read_bytes() + b"corrupt")
        with self.assertRaisesRegex(ValueError, "backup.*(?:hash|digest)"):
            recover_activation(self.project)
        self.assertTrue(recovery.is_dir())
        self.assertTrue(backup.is_file())

    def test_recovery_journal_schema_checksum_root_phase_and_digest_are_strict(self):
        from tools.codex_studio import engine_pack

        mutations = ("checksum", "extra", "missing", "version", "phase", "root", "digest")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "project"
                shutil.copytree(self.project, project)
                original_project = self.project
                self.project = project
                try:
                    recovery = self.leave_incomplete_recovery()
                finally:
                    self.project = original_project
                journal_path = recovery / "journal.json"
                journal = json.loads(journal_path.read_text(encoding="utf-8"))
                if mutation == "checksum":
                    journal["phase"] = "remove"
                elif mutation == "extra":
                    journal["unexpected"] = "value"
                    journal["checksum"] = engine_pack._journal_checksum(journal)
                elif mutation == "missing":
                    journal.pop("config_sha256")
                    journal["checksum"] = engine_pack._journal_checksum(journal)
                elif mutation == "version":
                    journal["version"] = 2
                    journal["checksum"] = engine_pack._journal_checksum(journal)
                elif mutation == "phase":
                    journal["phase"] = "invented"
                    journal["checksum"] = engine_pack._journal_checksum(journal)
                elif mutation == "root":
                    journal["project_root"] = str(project.parent)
                    journal["checksum"] = engine_pack._journal_checksum(journal)
                else:
                    journal["config_sha256"] = "not-a-sha256"
                    journal["checksum"] = engine_pack._journal_checksum(journal)
                journal_path.write_text(json.dumps(journal), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "corrupt|journal|checksum|phase|root|digest"):
                    plan_activation(project, "unity", version="6000.1", language="csharp")
                self.assertTrue(recovery.is_dir())

    def test_schema_valid_false_flag_cannot_authorize_live_state_deletion(self):
        from tools.codex_studio import engine_pack

        recovery = self.leave_incomplete_recovery(configured=True)
        journal_path = recovery / "journal.json"
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal["agents_existed"] = False
        journal["agents_digest"] = None
        journal["checksum"] = engine_pack._journal_checksum(journal)
        journal_path.write_text(json.dumps(journal), encoding="utf-8")
        before = tree_bytes(self.project)
        with self.assertRaisesRegex(ValueError, "artifact|flag|backup|corrupt"):
            recover_activation(self.project)
        self.assertEqual(before, tree_bytes(self.project))
        self.assertTrue((recovery / "backup-agents").is_dir())

    def test_terminal_journal_is_verified_before_retirement(self):
        from tools.codex_studio import engine_pack

        for phase in ("committed", "rolled-back"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "project"
                shutil.copytree(self.project, project)
                original_project = self.project
                self.project = project
                try:
                    recovery = self.leave_incomplete_recovery()
                finally:
                    self.project = original_project
                journal_path = recovery / "journal.json"
                journal = json.loads(journal_path.read_text(encoding="utf-8"))
                if phase == "committed":
                    snapshot = engine_pack._snapshot_live(project)
                    journal.update(engine_pack._target_fields(snapshot))
                    for noun, digest_name in (
                        ("agents", "agents_digest"),
                        ("manifest", "manifest_sha256"),
                        ("config", "config_sha256"),
                    ):
                        journal[f"target_{noun}_existed"] = True
                        if journal[f"target_{digest_name}"] is None:
                            journal[f"target_{digest_name}"] = "0" * 64
                journal["phase"] = phase
                journal["checksum"] = engine_pack._journal_checksum(journal)
                journal_path.write_text(json.dumps(journal), encoding="utf-8")
                (project / ".codex/studio.toml").write_text("corrupt live state", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "terminal|live|original|target|corrupt"):
                    recover_activation(project)
                self.assertTrue(recovery.is_dir())

    def test_silent_restore_corruption_preserves_recovery(self):
        from tools.codex_studio import engine_pack

        recovery = self.leave_incomplete_recovery(configured=True)
        real_copy = engine_pack._copy_agents

        def corrupt_restore(source: Path, destination: Path) -> None:
            real_copy(source, destination)
            if destination.name.startswith("restore-agents"):
                victim = next(destination.glob("*.toml"))
                victim.write_bytes(victim.read_bytes() + b"corrupt")

        with mock.patch("tools.codex_studio.engine_pack._copy_agents", side_effect=corrupt_restore):
            with self.assertRaisesRegex(ValueError, "restored|original|digest"):
                recover_activation(self.project)
        self.assertTrue(recovery.is_dir())
        self.assertTrue((recovery / "backup-agents").is_dir())

    def test_silent_config_restore_corruption_preserves_recovery(self):
        from tools.codex_studio import engine_pack

        recovery = self.leave_incomplete_recovery(configured=True)
        real_write = engine_pack._atomic_write

        def corrupt_config(path: Path, content: bytes) -> None:
            if path.name == "studio.toml":
                return real_write(path, content + b"# silent corruption\n")
            return real_write(path, content)

        with mock.patch("tools.codex_studio.engine_pack._atomic_write", side_effect=corrupt_config):
            with self.assertRaisesRegex(ValueError, "original recovery snapshot"):
                recover_activation(self.project)
        self.assertTrue(recovery.is_dir())
        self.assertTrue((recovery / "backup-config").is_file())

    def test_direct_apply_requires_complete_safe_target_and_safe_policy_fields(self):
        blank = plan_activation(self.project, "godot")
        with self.assertRaisesRegex(ValueError, "engine version is required"):
            apply_activation(self.project, blank)
        valid = plan_activation(self.project, "godot", version="4.6", language="gdscript")
        unsafe = dataclasses.replace(
            valid,
            target_config=dataclasses.replace(valid.target_config, review_mode="phase-gated\nunsafe"),
        )
        with self.assertRaisesRegex(ValueError, "review mode.*control"):
            apply_activation(self.project, unsafe)
        unsafe_model = dataclasses.replace(
            valid,
            target_config=dataclasses.replace(valid.target_config, model_policy="balanced\u2028unsafe"),
        )
        with self.assertRaisesRegex(ValueError, "model policy.*control"):
            apply_activation(self.project, unsafe_model)
        self.assertEqual("unconfigured", load_studio_config(self.project).engine)

    def test_reparse_and_name_surrogate_metadata_are_rejected(self):
        from tools.codex_studio import engine_pack

        real_lstat = os.lstat
        control = self.project / ".codex"

        def fake_lstat(path, *args, **kwargs):
            result = real_lstat(path, *args, **kwargs)
            if Path(os.fspath(path)).name == ".codex":
                values = {name: getattr(result, name) for name in dir(result) if name.startswith("st_")}
                values["st_file_attributes"] = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                values["st_reparse_tag"] = 0xA0000003
                return type("FakeStat", (), values)()
            return result

        with mock.patch("tools.codex_studio.engine_pack.os.lstat", side_effect=fake_lstat):
            with self.assertRaisesRegex(ValueError, "reparse|name-surrogate"):
                complete_plan(self.project, "godot")

    def test_direct_agents_manifest_config_lock_and_recovery_links_are_rejected(self):
        cases = ("agents", "active-engine.json", "studio.toml", "engine-pack.lock", "engine-pack-recovery")
        for name in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "project"
                shutil.copytree(self.project, project)
                path = project / ".codex" / name
                if path.exists() or path.is_symlink():
                    if path.is_dir() and not path.is_symlink():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                outside = project / f"outside-{name.replace('/', '-') }"
                if name in {"agents", "engine-pack-recovery"}:
                    outside.mkdir()
                    path.symlink_to(outside, target_is_directory=True)
                else:
                    outside.write_text("outside", encoding="utf-8")
                    path.symlink_to(outside)
                with self.assertRaisesRegex(ValueError, "symlink|reparse|link"):
                    complete_plan(project, "godot")

    def test_config_serializer_round_trips_quotes_backslashes_and_unicode(self):
        config = dataclasses.replace(
            load_studio_config(self.project),
            engine_version='4.6-"beta"\\路径',
            language="gdscript",
        )
        import tomllib

        parsed = tomllib.loads(_serialize_config(config).decode("utf-8"))
        self.assertEqual(dataclasses.asdict(config), parsed)


class PluginNativeEnginePackTests(unittest.TestCase):
    """Activation reads a separate trusted bundle and mutates only the target."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.target = Path(self.temp.name) / "target"
        self.source = Path(self.temp.name) / "bundle"
        shutil.copytree(ROOT / "tests/studio/fixtures/engine-project", self.target)
        shutil.copytree(ROOT / ".codex/agent-packs", self.source / ".codex/agent-packs")

    def tearDown(self):
        self.temp.cleanup()

    def test_plugin_native_source_root_dry_run_apply_and_no_op_leave_bundle_immutable(self):
        # Arrange
        target_before = tree_bytes(self.target)
        source_before = tree_bytes(self.source)

        # Act
        plan = plan_activation(
            self.target, "godot", version="4.6", language="gdscript", source_root=self.source,
        )

        # Assert
        self.assertEqual(self.source.resolve(), plan.source_root)
        self.assertEqual(5, len(plan.install))
        self.assertEqual(target_before, tree_bytes(self.target))
        self.assertEqual(source_before, tree_bytes(self.source))
        apply_activation(self.target, plan)
        self.assertEqual([], validate_activation(self.target, source_root=self.source))
        self.assertFalse((self.target / ".codex/agent-packs").exists())
        self.assertFalse((self.target / ".agents/skills").exists())
        self.assertEqual(source_before, tree_bytes(self.source))
        self.assertTrue(
            plan_activation(
                self.target, "godot", version="4.6", language="gdscript", source_root=self.source,
            ).no_op
        )

    def test_plugin_native_external_source_rendering_and_cli_are_read_only(self):
        # Arrange
        before = tree_bytes(self.target)
        script = ROOT / "tools/codex_studio/engine_pack.py"

        # Act
        result = subprocess.run(
            [
                sys.executable, "-B", str(script), "--root", str(self.target),
                "--source-root", str(self.source), "--engine", "godot", "--version", "4.6",
                "--language", "gdscript", "--dry-run",
            ],
            cwd=self.target,
            text=True,
            capture_output=True,
            check=False,
        )

        # Assert
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(5, result.stdout.count("INSTALL SOURCE .codex/agent-packs/godot/"))
        self.assertEqual(before, tree_bytes(self.target))

    def test_plugin_native_plan_reads_only_the_selected_source_pack(self):
        # Arrange
        next((self.source / ".codex/agent-packs/unity").glob("*.toml")).unlink()
        before = tree_bytes(self.target)

        # Act
        plan = plan_activation(
            self.target, "godot", version="4.6", language="gdscript", source_root=self.source,
        )

        # Assert
        self.assertEqual(5, len(plan.install))
        self.assertEqual(before, tree_bytes(self.target))

    def test_plugin_native_source_root_rejects_target_links_and_source_drift_without_target_writes(self):
        # Arrange / Act / Assert
        before = tree_bytes(self.target)
        with self.assertRaisesRegex(ValueError, "must differ"):
            plan_activation(self.target, "godot", version="4.6", language="gdscript", source_root=self.target)
        self.assertEqual(before, tree_bytes(self.target))
        linked = Path(self.temp.name) / "linked-bundle"
        linked.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "source root.*symlink"):
            plan_activation(self.target, "godot", version="4.6", language="gdscript", source_root=linked)
        plan = plan_activation(self.target, "godot", version="4.6", language="gdscript", source_root=self.source)
        source = plan.install[0]
        source.write_bytes(source.read_bytes() + b"\n# source drift\n")
        with self.assertRaisesRegex(ValueError, "source pack changed"):
            apply_activation(self.target, plan)
        self.assertEqual(before, tree_bytes(self.target))

    def test_plugin_native_plan_rejects_byte_identical_source_root_substitution(self):
        # Arrange
        plan = plan_activation(self.target, "godot", version="4.6", language="gdscript", source_root=self.source)
        replacement = Path(self.temp.name) / "replacement"
        shutil.copytree(self.source, replacement)
        retired = Path(self.temp.name) / "retired"
        self.source.rename(retired)
        replacement.rename(self.source)
        before = tree_bytes(self.target)

        # Act / Assert
        with self.assertRaisesRegex(ValueError, "identity changed"):
            apply_activation(self.target, plan)
        self.assertEqual(before, tree_bytes(self.target))

    def test_plugin_native_plan_rejects_source_a_to_b_to_a_at_same_path(self):
        # Arrange
        plan = plan_activation(
            self.target, "godot", version="4.6", language="gdscript",
            source_root=self.source,
        )
        source_a = Path(self.temp.name) / "source-a"
        source_b = Path(self.temp.name) / "source-b"
        shutil.copytree(self.source, source_b)
        self.source.rename(source_a)
        source_b.rename(self.source)
        self.source.rename(source_b)
        source_a.rename(self.source)
        before = tree_bytes(self.target)

        # Act / Assert
        with self.assertRaisesRegex(ValueError, "identity changed"):
            apply_activation(self.target, plan)
        self.assertEqual(before, tree_bytes(self.target))

    def test_plugin_native_windows_change_time_rejects_source_a_to_b_to_a(self):
        # Arrange
        from tools.codex_studio import engine_pack

        api = FakeWindowsDirectoryApi()
        source_key = str(self.source.resolve())
        with mock.patch.object(
            engine_pack, "_is_windows_platform", return_value=True
        ), mock.patch.object(
            engine_pack, "_NativeWindowsDirectoryApi", return_value=api
        ):
            plan = plan_activation(
                self.target, "godot", version="4.6", language="gdscript",
                source_root=self.source,
            )
            original_stable_identity = plan.source_root_identity[:3]
            source_a = Path(self.temp.name) / "source-a"
            source_b = Path(self.temp.name) / "source-b"
            shutil.copytree(self.source, source_b)
            self.source.rename(source_a)
            source_b.rename(self.source)
            self.source.rename(source_b)
            source_a.rename(self.source)
            api.change_times[source_key] += 1
            before = tree_bytes(self.target)

            # Act / Assert
            with self.assertRaisesRegex(ValueError, "identity changed"):
                apply_activation(self.target, plan)
        self.assertEqual(
            original_stable_identity,
            (7, api.file_ids[source_key], api.creation_times[source_key]),
        )
        self.assertCountEqual(api.opened, api.closed)
        self.assertEqual(before, tree_bytes(self.target))

    def test_plugin_native_windows_directory_identity_unchanged_passes_and_closes_handle(self):
        # Arrange
        from tools.codex_studio import engine_pack

        api = FakeWindowsDirectoryApi()
        with mock.patch.object(
            engine_pack, "_is_windows_platform", return_value=True
        ), mock.patch.object(
            engine_pack, "_NativeWindowsDirectoryApi", return_value=api
        ):
            # Act
            first = engine_pack._directory_identity(self.source, "source")
            second = engine_pack._directory_identity(self.source, "source")

        # Assert
        self.assertEqual(first, second)
        self.assertCountEqual(api.opened, api.closed)
        for _path, flags, share in api.open_calls:
            self.assertTrue(flags & api.FILE_FLAG_OPEN_REPARSE_POINT)
            self.assertTrue(flags & api.FILE_FLAG_BACKUP_SEMANTICS)
            self.assertEqual(
                api.FILE_SHARE_READ | api.FILE_SHARE_WRITE | api.FILE_SHARE_DELETE,
                share,
            )

    def test_plugin_native_windows_directory_identity_error_is_actionable_and_closes_handle(self):
        # Arrange
        from tools.codex_studio import engine_pack

        api = FakeWindowsDirectoryApi()
        api.fail_info = True

        # Act / Assert
        with mock.patch.object(
            engine_pack, "_is_windows_platform", return_value=True
        ), mock.patch.object(
            engine_pack, "_NativeWindowsDirectoryApi", return_value=api
        ):
            with self.assertRaisesRegex(
                ValueError, "native Windows directory identity.*GetFileInformation"
            ):
                engine_pack._directory_identity(self.source, "source")
        self.assertCountEqual(api.opened, api.closed)

    def test_plugin_native_windows_directory_identity_rejects_reparse_handle(self):
        # Arrange
        from tools.codex_studio import engine_pack

        api = FakeWindowsDirectoryApi()
        api.reparse_paths.add(str(self.source))

        # Act / Assert
        with mock.patch.object(
            engine_pack, "_is_windows_platform", return_value=True
        ), mock.patch.object(
            engine_pack, "_NativeWindowsDirectoryApi", return_value=api,
        ):
            with self.assertRaisesRegex(ValueError, "reparse point"):
                engine_pack._directory_identity(self.source, "source")
        self.assertCountEqual(api.opened, api.closed)

    def test_plugin_native_source_root_rejects_linked_ancestor_component(self):
        # Arrange
        linked_parent = Path(self.temp.name) / "linked-parent"
        linked_parent.symlink_to(self.source.parent, target_is_directory=True)
        before = tree_bytes(self.target)

        # Act / Assert
        with self.assertRaisesRegex(ValueError, "ancestor.*symlink|symlink.*ancestor"):
            plan_activation(
                self.target, "godot", version="4.6", language="gdscript",
                source_root=linked_parent / self.source.name,
            )
        self.assertEqual(before, tree_bytes(self.target))

    def test_plugin_native_source_pack_replacement_during_apply_rolls_back(self):
        # Arrange
        from tools.codex_studio import engine_pack

        plan = plan_activation(
            self.target, "godot", version="4.6", language="gdscript",
            source_root=self.source,
        )
        pack = self.source / ".codex/agent-packs/godot"
        replacement = Path(self.temp.name) / "replacement-pack"
        shutil.copytree(pack, replacement)
        retired = Path(self.temp.name) / "retired-pack"
        before = tree_bytes(self.target)
        original_write = engine_pack._exclusive_profile_write
        swapped = False

        def replace_after_first_profile(agents: Path, name: str, raw: bytes) -> None:
            nonlocal swapped
            original_write(agents, name, raw)
            if not swapped:
                pack.rename(retired)
                replacement.rename(pack)
                swapped = True

        # Act / Assert
        with mock.patch.object(
            engine_pack, "_exclusive_profile_write",
            side_effect=replace_after_first_profile,
        ):
            with self.assertRaisesRegex(ValueError, "identity changed"):
                apply_activation(self.target, plan)
        self.assertTrue(swapped)
        self.assertEqual(before, tree_bytes(self.target))

    def test_plugin_native_engine_switch_reads_only_current_and_selected_packs(self):
        # Arrange
        shutil.rmtree(self.source / ".codex/agent-packs/unreal")
        apply_activation(
            self.target,
            plan_activation(
                self.target, "godot", version="4.6", language="gdscript",
                source_root=self.source,
            ),
        )

        # Act
        apply_activation(
            self.target,
            plan_activation(
                self.target, "unity", version="6000.1", language="csharp",
                source_root=self.source,
            ),
        )

        # Assert
        self.assertEqual([], validate_activation(self.target, source_root=self.source))
        self.assertEqual("unity", load_studio_config(self.target).engine)

    def test_plugin_native_switch_rejects_byte_identical_current_pack_replacement(self):
        # Arrange
        apply_activation(
            self.target,
            plan_activation(
                self.target, "godot", version="4.6", language="gdscript",
                source_root=self.source,
            ),
        )
        plan = plan_activation(
            self.target, "unity", version="6000.1", language="csharp",
            source_root=self.source,
        )
        self.assertEqual(
            ("godot", "unity"),
            tuple(engine for engine, _identity in plan.source_pack_identities),
        )
        current_pack = self.source / ".codex/agent-packs/godot"
        replacement = Path(self.temp.name) / "replacement-godot"
        retired = Path(self.temp.name) / "retired-godot"
        shutil.copytree(current_pack, replacement)
        current_pack.rename(retired)
        replacement.rename(current_pack)
        before = tree_bytes(self.target)

        # Act / Assert
        with self.assertRaisesRegex(ValueError, "source pack identity changed"):
            apply_activation(self.target, plan)
        self.assertEqual(before, tree_bytes(self.target))

    def test_plugin_native_external_pack_rejects_missing_canonical_profile_before_writes(self):
        # Arrange
        (self.source / ".codex/agent-packs/godot/godot-specialist.toml").unlink()
        before = tree_bytes(self.target)

        # Act / Assert
        with self.assertRaisesRegex(ValueError, "exactly five"):
            plan_activation(
                self.target, "godot", version="4.6", language="gdscript",
                source_root=self.source,
            )
        self.assertEqual(before, tree_bytes(self.target))

    def test_plugin_native_external_pack_rejects_arbitrary_profile_names_before_writes(self):
        # Arrange
        profile = self.source / ".codex/agent-packs/godot/godot-specialist.toml"
        renamed = profile.with_name("arbitrary-profile.toml")
        renamed.write_text(profile.read_text(encoding="utf-8").replace('name = "godot-specialist"', 'name = "arbitrary-profile"'), encoding="utf-8")
        profile.unlink()
        before = tree_bytes(self.target)

        # Act / Assert
        with self.assertRaisesRegex(ValueError, "canonical five"):
            plan_activation(self.target, "godot", version="4.6", language="gdscript", source_root=self.source)
        self.assertEqual(before, tree_bytes(self.target))

    def test_plugin_native_external_pack_rejects_unexpected_sixth_profile_before_writes(self):
        # Arrange
        extra = self.source / ".codex/agent-packs/godot/unexpected.toml"
        extra.write_text('name = "unexpected"\n', encoding="utf-8")
        before = tree_bytes(self.target)

        # Act / Assert
        with self.assertRaisesRegex(ValueError, "exactly five"):
            plan_activation(
                self.target, "godot", version="4.6", language="gdscript",
                source_root=self.source,
            )
        self.assertEqual(before, tree_bytes(self.target))

    def test_plugin_native_external_pack_rejects_internal_name_mismatch_before_writes(self):
        # Arrange
        profile = self.source / ".codex/agent-packs/godot/godot-specialist.toml"
        profile.write_text(
            profile.read_text(encoding="utf-8").replace(
                'name = "godot-specialist"', 'name = "wrong-specialist"'
            ),
            encoding="utf-8",
        )
        before = tree_bytes(self.target)

        # Act / Assert
        with self.assertRaisesRegex(ValueError, "name must match filename"):
            plan_activation(
                self.target, "godot", version="4.6", language="gdscript",
                source_root=self.source,
            )
        self.assertEqual(before, tree_bytes(self.target))


class EnginePackCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name) / "project"
        shutil.copytree(ROOT / "tests/studio/fixtures/engine-project", self.project)
        shutil.copytree(ROOT / ".codex/agent-packs", self.project / ".codex/agent-packs")

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "tools.codex_studio.engine_pack", "--root", str(self.project), *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_dry_run_lists_complete_plan_without_mutation(self):
        before = tree_bytes(self.project)
        result = self.run_cli("--engine", "godot", "--version", "4.6", "--language", "gdscript", "--dry-run")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(5, result.stdout.count("INSTALL "))
        self.assertIn("CONFIG engine=godot engine_version=4.6 language=gdscript", result.stdout)
        self.assertIn("active_engine_pack=godot", result.stdout)
        self.assertIn("review_mode=phase-gated", result.stdout)
        self.assertIn("model_policy=balanced", result.stdout)
        self.assertEqual(before, tree_bytes(self.project))

    def test_apply_succeeds_and_safety_failure_exits_nonzero(self):
        result = self.run_cli("--engine", "unity", "--version", "6000.1", "--language", "csharp", "--apply")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Activated unity with 5 managed profiles", result.stdout)
        collision_project = Path(self.temp.name) / "collision"
        shutil.copytree(ROOT / "tests/studio/fixtures/engine-project", collision_project)
        shutil.copytree(ROOT / ".codex/agent-packs", collision_project / ".codex/agent-packs")
        target = collision_project / ".codex/agents/godot-specialist.toml"
        target.parent.mkdir(parents=True)
        target.write_text("unmanaged", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "tools.codex_studio.engine_pack", "--root", str(collision_project), "--engine", "godot", "--version", "4.6", "--language", "gdscript", "--apply"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("unmanaged profile collision", result.stderr)

    def test_cli_requires_exactly_one_mode_and_valid_engine(self):
        neither = self.run_cli("--engine", "godot")
        both = self.run_cli("--engine", "godot", "--dry-run", "--apply")
        invalid = self.run_cli("--engine", "cryengine", "--dry-run")
        self.assertEqual(2, neither.returncode)
        self.assertEqual(2, both.returncode)
        self.assertEqual(2, invalid.returncode)

    def test_cli_recover_is_explicit_and_idempotent_without_pending_journal(self):
        result = self.run_cli("--recover")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("recovery complete", result.stdout.lower())

    @unittest.skipUnless(os.name == "posix", "subprocess flock contention requires POSIX")
    def test_subprocess_lock_contention_fails_closed(self):
        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import pathlib,time; "
                    "from tools.codex_studio.engine_pack import _activation_lock,_normalize_root; "
                    f"root=_normalize_root(pathlib.Path({str(self.project)!r})); "
                    "ctx=_activation_lock(root); ctx.__enter__(); print('LOCKED', flush=True); time.sleep(10)"
                ),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            self.assertEqual("LOCKED", holder.stdout.readline().strip())
            result = self.run_cli(
                "--engine", "godot", "--version", "4.6", "--language", "gdscript", "--apply"
            )
            self.assertEqual(1, result.returncode)
            self.assertIn("locked", result.stderr)
        finally:
            holder.terminate()
            holder.wait(timeout=5)
            assert holder.stdout is not None and holder.stderr is not None
            holder.stdout.close()
            holder.stderr.close()

    def test_apply_requires_exact_version_and_compatible_control_free_language(self):
        cases = (
            ("godot", "", "gdscript"),
            ("godot", "4.6", ""),
            ("godot", "4.6\nmalicious", "gdscript"),
            ("godot", "4.6", "gdscript\nmalicious"),
            ("unity", "6000.1", "gdscript"),
            ("unreal", "5.7", "csharp"),
        )
        for engine, version, language in cases:
            with self.subTest(engine=engine, version=version, language=language):
                result = self.run_cli(
                    "--engine", engine, "--version", version, "--language", language, "--apply"
                )
                self.assertEqual(1, result.returncode)
        for engine, version, language in (
            ("godot", "4.6", "gdscript"),
            ("godot", "4.6", "csharp"),
            ("unity", "6000.1", "csharp"),
            ("unreal", "5.7", "cpp"),
            ("unreal", "5.7", "blueprint"),
        ):
            with self.subTest(valid=(engine, language)), tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "project"
                shutil.copytree(ROOT / "tests/studio/fixtures/engine-project", project)
                shutil.copytree(ROOT / ".codex/agent-packs", project / ".codex/agent-packs")
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "tools.codex_studio.engine_pack",
                        "--root",
                        str(project),
                        "--engine",
                        engine,
                        "--version",
                        version,
                        "--language",
                        language,
                        "--apply",
                    ],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)
