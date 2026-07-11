from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools.codex_studio.engine_pack import (
    apply_activation,
    load_studio_config,
    plan_activation,
    validate_activation,
)


ROOT = Path(__file__).resolve().parents[2]


def tree_bytes(root: Path) -> dict[str, tuple[str, bytes | str]]:
    result: dict[str, tuple[str, bytes | str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
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
        apply_activation(self.project, plan_activation(self.project, "godot"))
        apply_activation(self.project, plan_activation(self.project, "unreal"))
        self.assertEqual('name = "my-agent"\n', custom.read_text(encoding="utf-8"))
        self.assertEqual(5, len(list(agents.glob("ue-*.toml"))) + len(list(agents.glob("unreal-*.toml"))))

    def test_unmanaged_name_collision_is_rejected(self):
        target = self.project / ".codex/agents/godot-specialist.toml"
        target.parent.mkdir(parents=True)
        target.write_text("unmanaged", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unmanaged profile collision"):
            plan_activation(self.project, "godot")

    def test_modified_generated_profile_blocks_switch(self):
        apply_activation(self.project, plan_activation(self.project, "godot"))
        generated = next((self.project / ".codex/agents").glob("godot-*.toml"))
        generated.write_text(generated.read_text(encoding="utf-8") + "\n# user edit\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "generated profile was modified"):
            plan_activation(self.project, "unity")

    def test_symlinked_pack_profile_and_target_are_rejected(self):
        source = self.project / ".codex/agent-packs/godot/godot-specialist.toml"
        original = source.read_bytes()
        real_source = self.project / "outside-profile.toml"
        real_source.write_bytes(original)
        source.unlink()
        source.symlink_to(real_source)
        with self.assertRaisesRegex(ValueError, "symlink"):
            plan_activation(self.project, "godot")
        source.unlink()
        source.write_bytes(original)
        target = self.project / ".codex/agents/godot-specialist.toml"
        target.parent.mkdir(parents=True)
        target.symlink_to(source)
        with self.assertRaisesRegex(ValueError, "symlink"):
            plan_activation(self.project, "godot")

    def test_symlinked_codex_control_directory_is_rejected(self):
        codex = self.project / ".codex"
        relocated = self.project / "relocated-codex"
        codex.rename(relocated)
        codex.symlink_to(relocated.name, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "control directory.*symlink"):
            plan_activation(self.project, "godot")

    def test_malformed_config_and_manifest_are_rejected(self):
        config = self.project / ".codex/studio.toml"
        config.write_text("engine = [\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "studio config"):
            plan_activation(self.project, "godot")
        shutil.copy2(ROOT / "tests/studio/fixtures/engine-project/.codex/studio.toml", config)
        (self.project / ".codex/active-engine.json").write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "active-engine manifest"):
            plan_activation(self.project, "godot")

    def test_manifest_traversal_and_invalid_hash_are_rejected(self):
        manifest = self.project / ".codex/active-engine.json"
        manifest.write_text(
            json.dumps({"engine": "godot", "generated": {"../outside.toml": "0" * 64}}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "filename"):
            plan_activation(self.project, "unity")
        manifest.write_text(
            json.dumps({"engine": "godot", "generated": {"godot-specialist.toml": "bad"}}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "hash"):
            plan_activation(self.project, "unity")

    def test_windows_style_manifest_traversal_is_rejected(self):
        generated = {"..\\outside.toml": "0" * 64}
        generated.update({f"safe-{index}.toml": "0" * 64 for index in range(4)})
        (self.project / ".codex/active-engine.json").write_text(
            json.dumps({"engine": "godot", "generated": generated}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "filename"):
            plan_activation(self.project, "unity")

    def test_stale_plan_and_changed_source_pack_are_rejected_without_mutation(self):
        plan = plan_activation(self.project, "godot")
        custom = self.project / ".codex/agents/custom.toml"
        custom.parent.mkdir(parents=True)
        custom.write_text("changed", encoding="utf-8")
        before = tree_bytes(self.project)
        with self.assertRaisesRegex(ValueError, "stale activation plan"):
            apply_activation(self.project, plan)
        self.assertEqual(before, tree_bytes(self.project))
        custom.unlink()
        plan = plan_activation(self.project, "godot")
        source = plan.install[0]
        source.write_bytes(source.read_bytes() + b"\n# source drift\n")
        before = tree_bytes(self.project)
        with self.assertRaisesRegex(ValueError, "source pack changed"):
            apply_activation(self.project, plan)
        self.assertEqual(before, tree_bytes(self.project))

    def test_forged_plan_cannot_remove_a_path_outside_managed_agents(self):
        important = self.project / "important.txt"
        important.write_text("preserve me", encoding="utf-8")
        plan = plan_activation(self.project, "godot")
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

    def test_each_mutation_failure_rolls_back_byte_for_byte(self):
        phases = ("remove", "copy", "manifest-write", "config-write", "post-validation")
        for phase in phases:
            with self.subTest(phase=phase):
                apply_activation(self.project, plan_activation(self.project, "godot"))
                before = tree_bytes(self.project)
                plan = plan_activation(self.project, "unity")

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
                apply_activation(self.project, plan_activation(self.project, "godot"))
        self.assertEqual(before, tree_bytes(self.project))

    def test_actual_copy_replace_write_and_validation_failures_rollback(self):
        failure_cases = ("copy", "replace", "manifest-write", "config-write", "validation")
        for failure_case in failure_cases:
            with self.subTest(failure_case=failure_case):
                before = tree_bytes(self.project)
                plan = plan_activation(self.project, "godot")
                patches = []
                if failure_case == "copy":
                    real_copy = shutil.copy2
                    calls = 0

                    def copy_failure(source, destination, *args, **kwargs):
                        nonlocal calls
                        calls += 1
                        if calls == 3:
                            raise OSError("actual copy failure")
                        return real_copy(source, destination, *args, **kwargs)

                    patches.append(mock.patch("tools.codex_studio.engine_pack.shutil.copy2", side_effect=copy_failure))
                elif failure_case == "replace":
                    patches.append(mock.patch("tools.codex_studio.engine_pack.os.replace", side_effect=OSError("actual replace failure")))
                elif failure_case in {"manifest-write", "config-write"}:
                    from tools.codex_studio import engine_pack

                    real_write = engine_pack._atomic_write

                    def write_failure(path, content, selected=failure_case):
                        if (selected == "manifest-write" and path.name == "active-engine.json") or (
                            selected == "config-write" and path.name == "studio.toml"
                        ):
                            raise OSError(f"actual {selected} failure")
                        return real_write(path, content)

                    patches.append(mock.patch("tools.codex_studio.engine_pack._atomic_write", side_effect=write_failure))
                else:
                    patches.append(mock.patch("tools.codex_studio.engine_pack.validate_activation", return_value=["injected invalid state"]))
                with patches[0]:
                    with self.assertRaises((OSError, ValueError)):
                        apply_activation(self.project, plan)
                self.assertEqual(before, tree_bytes(self.project))

    def test_actual_remove_failure_rolls_back(self):
        apply_activation(self.project, plan_activation(self.project, "godot"))
        before = tree_bytes(self.project)
        plan = plan_activation(self.project, "unity")
        with mock.patch(
            "tools.codex_studio.engine_pack._unlink_managed",
            create=True,
            side_effect=OSError("actual remove failure"),
        ):
            with self.assertRaisesRegex(OSError, "actual remove failure"):
                apply_activation(self.project, plan)
        self.assertEqual(before, tree_bytes(self.project))


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
        self.assertIn("CONFIG engine=godot version=4.6 language=gdscript", result.stdout)
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
            [sys.executable, "-m", "tools.codex_studio.engine_pack", "--root", str(collision_project), "--engine", "godot", "--apply"],
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
