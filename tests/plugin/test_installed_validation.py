"""Installed-repository validator contract tests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import shutil
import stat
import types
import runpy
from unittest import mock

from tests.plugin.helpers import init_git_repo, snapshot_tree, write_installed_fixture
from tools.codex_studio.validate import _SecureInstalledRoot, validate_installed_repository
import tools.codex_studio.validate as validator_module
from tools.codex_studio.engine_pack import apply_activation, plan_activation


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"
sys.path.insert(0, str(PLUGIN / "scripts"))


class InstalledValidationTests(unittest.TestCase):
    """Validate installed operational content without source-only requirements."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name).resolve() / "game"
        init_git_repo(self.repo)
        write_installed_fixture(self.repo, PLUGIN)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _rewrite_state(self, mutate) -> None:
        state_path = self.repo / ".codex/codex-game-studios/installation.json"
        document = json.loads(state_path.read_text(encoding="utf-8"))
        mutate(document)
        body = dict(document)
        body.pop("checksum", None)
        canonical = (json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
        document["checksum"] = hashlib.sha256(canonical).hexdigest()
        state_path.write_bytes(canonical_json_with_checksum(document))

    def test_schema_two_state_requires_exact_digest_type_and_utc_timestamp(self):
        # Arrange: exercise the source validator and the actual bundled validator
        # against the same canonical state documents.
        bundled_path = (
            PLUGIN / "assets/studio/tools/codex_studio/validate.py"
        )
        previous_path = list(sys.path)
        try:
            bundled = runpy.run_path(
                str(bundled_path), run_name="_bundled_validator_contract"
            )
        finally:
            sys.path[:] = previous_path
        loaders = (
            validator_module._load_installed_state,
            bundled["_load_installed_state"],
        )

        def state_raw(*, legacy_checksum: object, migrated_at: str) -> bytes:
            body = {
                "schema_version": 2,
                "plugin_version": "2.0.0",
                "legacy_version": "1.0.0",
                "legacy_state_checksum": legacy_checksum,
                "preserved_paths": [],
                "migrated_at": migrated_at,
            }
            body["checksum"] = hashlib.sha256(
                canonical_json_with_checksum(body)
            ).hexdigest()
            return canonical_json_with_checksum(body)

        invalid = (
            (int("1" * 64), "2026-07-18T01:02:03Z"),
            ("A" * 64, "2026-07-18T01:02:03Z"),
            ("a" * 64, "2026-07-18T01:02:03+00:00"),
            ("a" * 64, "2026-07-18T01:02:03.000Z"),
            ("a" * 64, "2026-07-18T01:02:03z"),
            ("a" * 64, "2026-02-30T01:02:03Z"),
        )

        # Act / Assert
        for loader in loaders:
            document, issues = loader(
                state_raw(
                    legacy_checksum="a" * 64,
                    migrated_at="2026-07-18T01:02:03Z",
                )
            )
            self.assertIsNotNone(document)
            self.assertEqual([], issues)
            for legacy_checksum, migrated_at in invalid:
                with self.subTest(
                    loader=loader.__module__,
                    legacy_checksum=legacy_checksum,
                    migrated_at=migrated_at,
                ):
                    document, issues = loader(state_raw(
                        legacy_checksum=legacy_checksum,
                        migrated_at=migrated_at,
                    ))
                    self.assertIsNone(document)
                    self.assertTrue(issues)

    def test_installed_mode_accepts_game_owned_files_and_excluded_maintainer_material(self):
        # Arrange
        (self.repo / "src/game.py").write_text("print('game')\n", encoding="utf-8")

        # Act
        issues = validate_installed_repository(self.repo)

        # Assert
        self.assertEqual([], issues)
        self.assertFalse((self.repo / "README.md").exists())
        self.assertFalse((self.repo / "docs/superpowers").exists())

    def test_bundled_plugin_scripts_activate_and_validate_a_fresh_minimal_target(self):
        # Arrange
        target = Path(self.temporary.name).resolve() / "plugin-native-target"
        shutil.copytree(ROOT / "tests/studio/fixtures/engine-project", target)
        fixture_files = {
            ".editorconfig": b"root = true\n",
            ".gitattributes": b"* text=auto\n",
            ".gitignore": b".godot/\n",
            "project.godot": b"[application]\nconfig/name=\"Embermarch Fixture\"\n",
        }
        for relative, content in fixture_files.items():
            (target / relative).write_bytes(content)
        bundle = PLUGIN / "assets/studio"
        engine_pack = bundle / "tools/codex_studio/engine_pack.py"
        validator = bundle / "tools/codex_studio/validate.py"
        before = snapshot_tree(target)
        bundle_before = snapshot_tree(bundle)
        source_fixture_before = snapshot_tree(
            ROOT / "tests/studio/fixtures/engine-project"
        )
        godot_names = {
            "godot-csharp-specialist.toml",
            "godot-gdextension-specialist.toml",
            "godot-gdscript-specialist.toml",
            "godot-shader-specialist.toml",
            "godot-specialist.toml",
        }
        unity_names = {
            "unity-addressables-specialist.toml",
            "unity-dots-specialist.toml",
            "unity-shader-specialist.toml",
            "unity-specialist.toml",
            "unity-ui-specialist.toml",
        }

        # Act
        dry_run = subprocess.run(
            [
                sys.executable, "-B", str(engine_pack), "--root", str(target),
                "--source-root", str(bundle), "--engine", "godot", "--version", "4.6",
                "--language", "gdscript", "--dry-run",
            ], cwd=target, text=True, capture_output=True, check=False,
        )

        # Assert
        self.assertEqual(0, dry_run.returncode, dry_run.stderr)
        self.assertEqual(5, dry_run.stdout.count("INSTALL SOURCE .codex/agent-packs/godot/"))
        self.assertEqual(before, snapshot_tree(target))
        apply = subprocess.run(
            [
                sys.executable, "-B", str(engine_pack), "--root", str(target),
                "--source-root", str(bundle), "--engine", "godot", "--version", "4.6",
                "--language", "gdscript", "--apply",
            ], cwd=target, text=True, capture_output=True, check=False,
        )
        self.assertEqual(0, apply.returncode, apply.stderr)
        self.assertIn("Activated godot with 5 managed profiles", apply.stdout)
        manifest = json.loads(
            (target / ".codex/active-engine.json").read_text(encoding="utf-8")
        )
        self.assertEqual("godot", manifest["engine"])
        self.assertEqual(godot_names, set(manifest["generated"]))
        for name, digest in manifest["generated"].items():
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            active = (target / ".codex/agents" / name).read_bytes()
            source = (bundle / ".codex/agent-packs/godot" / name).read_bytes()
            self.assertEqual(source, active)
            self.assertEqual(digest, hashlib.sha256(active).hexdigest())

        validator_result = subprocess.run(
            [
                sys.executable, "-B", str(validator), "--mode", "plugin-native",
                "--root", str(target), "--source-root", str(bundle), "--phase", "final",
            ], cwd=target, text=True, capture_output=True, check=False,
        )
        self.assertEqual(0, validator_result.returncode, validator_result.stderr)
        self.assertEqual("Codex Studio validation: PASS\n", validator_result.stdout)
        self.assertEqual("", validator_result.stderr)

        no_op = subprocess.run(
            [
                sys.executable, "-B", str(engine_pack), "--root", str(target),
                "--source-root", str(bundle), "--engine", "godot", "--version", "4.6",
                "--language", "gdscript", "--dry-run",
            ], cwd=target, text=True, capture_output=True, check=False,
        )
        self.assertEqual(0, no_op.returncode, no_op.stderr)
        self.assertIn("NO-OP active pack and configuration already match", no_op.stdout)
        self.assertNotIn("INSTALL ", no_op.stdout)

        switched = subprocess.run(
            [
                sys.executable, "-B", str(engine_pack), "--root", str(target),
                "--source-root", str(bundle), "--engine", "unity", "--version", "6000.1",
                "--language", "csharp", "--apply",
            ], cwd=target, text=True, capture_output=True, check=False,
        )
        self.assertEqual(0, switched.returncode, switched.stderr)
        self.assertIn("Activated unity with 5 managed profiles", switched.stdout)
        switched_manifest = json.loads(
            (target / ".codex/active-engine.json").read_text(encoding="utf-8")
        )
        self.assertEqual("unity", switched_manifest["engine"])
        self.assertEqual(unity_names, set(switched_manifest["generated"]))
        self.assertEqual(unity_names, {path.name for path in (target / ".codex/agents").iterdir()})
        switched_validation = subprocess.run(
            [
                sys.executable, "-B", str(validator), "--mode", "plugin-native",
                "--root", str(target), "--source-root", str(bundle), "--phase", "final",
            ], cwd=target, text=True, capture_output=True, check=False,
        )
        self.assertEqual(0, switched_validation.returncode, switched_validation.stderr)
        self.assertEqual("Codex Studio validation: PASS\n", switched_validation.stdout)

        for forbidden in (
            ".agents/skills", ".codex/agent-packs", ".codex/engine-pack-recovery",
            "tools", "docs/engine-reference", "references",
        ):
            self.assertFalse((target / forbidden).exists(), forbidden)
        for relative, content in fixture_files.items():
            self.assertEqual(content, (target / relative).read_bytes())
        self.assertEqual(bundle_before, snapshot_tree(bundle))
        self.assertEqual(
            source_fixture_before,
            snapshot_tree(ROOT / "tests/studio/fixtures/engine-project"),
        )

    def test_bundled_engine_pack_rejects_a_swapped_source_root_without_target_writes(self):
        # Arrange
        target = Path(self.temporary.name).resolve() / "swapped-source-target"
        shutil.copytree(ROOT / "tests/studio/fixtures/engine-project", target)
        before = snapshot_tree(target)
        engine_pack = PLUGIN / "assets/studio/tools/codex_studio/engine_pack.py"

        # Act
        result = subprocess.run(
            [
                sys.executable, "-B", str(engine_pack), "--root", str(target),
                "--source-root", str(ROOT), "--engine", "godot", "--version", "4.6",
                "--language", "gdscript", "--dry-run",
            ], cwd=target, text=True, capture_output=True, check=False,
        )

        # Assert
        self.assertNotEqual(0, result.returncode)
        self.assertIn("bundled studio root", result.stderr)
        self.assertEqual(before, snapshot_tree(target))

    def test_installed_validator_accepts_configured_39_profile_routing(self):
        # Arrange
        apply_activation(self.repo, plan_activation(self.repo, "godot", version="4.6", language="gdscript"))

        # Act
        issues = validate_installed_repository(self.repo)

        # Assert
        self.assertEqual([], issues)

    def test_installed_validator_never_invokes_unanchored_studio_loader(self):
        # Arrange
        apply_activation(self.repo, plan_activation(self.repo, "godot", version="4.6", language="gdscript"))

        # Act
        with mock.patch.object(
            validator_module,
            "load_studio_config",
            side_effect=AssertionError("unanchored loader invoked"),
        ):
            issues = validate_installed_repository(self.repo)

        # Assert
        self.assertEqual([], issues)

    def test_installed_validator_configured_routing_rejects_unrelated_studio_authority_change(self):
        # Arrange
        apply_activation(self.repo, plan_activation(self.repo, "godot", version="4.6", language="gdscript"))
        studio = self.repo / ".codex/studio.toml"
        studio.write_text(studio.read_text(encoding="utf-8").replace('review_mode = "phase-gated"', 'review_mode = "solo"'), encoding="utf-8")

        # Act
        issues = validate_installed_repository(self.repo)

        # Assert
        self.assertTrue(any(issue.path == ".codex/studio.toml" for issue in issues))

    def test_installed_mode_reports_tampered_managed_file(self):
        # Arrange
        target = self.repo / ".codex/agents/producer.toml"
        target.write_text("tampered\n", encoding="utf-8")

        # Act
        issues = validate_installed_repository(self.repo)

        # Assert
        self.assertTrue(any(issue.path == ".codex/agents/producer.toml" for issue in issues))

    def test_installed_mode_reports_checksum_and_payload_provenance_tampering(self):
        # Arrange
        state_path = self.repo / ".codex/codex-game-studios/installation.json"
        document = json.loads(state_path.read_text(encoding="utf-8"))
        document["payload_digest"] = "0" * 64
        state_path.write_text(json.dumps(document), encoding="utf-8")

        # Act
        issues = validate_installed_repository(self.repo)

        # Assert
        self.assertTrue(any(issue.path.endswith("installation.json") for issue in issues))

    def test_installed_mode_rejects_checksummed_unknown_state_fields(self):
        # Arrange
        state_path = self.repo / ".codex/codex-game-studios/installation.json"
        document = json.loads(state_path.read_text(encoding="utf-8"))
        document["unknown"] = "forged"
        body = dict(document)
        body.pop("checksum")
        canonical = (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode()
        document["checksum"] = hashlib.sha256(canonical).hexdigest()
        state_path.write_text(json.dumps(document), encoding="utf-8")

        # Act
        issues = validate_installed_repository(self.repo)

        # Assert
        self.assertTrue(any("state schema" in issue.message for issue in issues))

    def test_installed_validator_rejects_rechecksummed_semantic_state_mutations(self):
        # Arrange / Act / Assert
        mutations = (
            lambda state: state.__setitem__("transaction_id", "not-a-uuid"),
            lambda state: state.__setitem__("installed_at", "yesterday"),
            lambda state: state.__setitem__("validator_version", ""),
            lambda state: state["decisions"].append({"kind": "unknown", "path": "AGENTS.md"}),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                shutil.rmtree(self.repo)
                init_git_repo(self.repo)
                write_installed_fixture(self.repo, PLUGIN)
                self._rewrite_state(mutation)
                self.assertTrue(validate_installed_repository(self.repo))

    def test_installed_validator_rejects_rechecksummed_omitted_required_inventory(self):
        # Arrange
        omitted = ".codex/codex-game-studios/legal/LICENSE"
        (self.repo / omitted).unlink()
        self._rewrite_state(lambda state: state["managed_paths"].__setitem__(slice(None), [item for item in state["managed_paths"] if item["path"] != omitted]))

        # Act
        issues = validate_installed_repository(self.repo)

        # Assert
        self.assertTrue(any("inventory" in issue.message or issue.path == omitted for issue in issues))

    def test_installed_validator_rejects_intermediate_and_ancestor_symlinks(self):
        # Arrange
        outside = Path(self.temporary.name) / "outside"
        shutil.copytree(self.repo / ".codex", outside / ".codex")
        shutil.rmtree(self.repo / ".codex")
        (self.repo / ".codex").symlink_to(outside / ".codex", target_is_directory=True)

        # Act
        intermediate = validate_installed_repository(self.repo)
        alias = Path(self.temporary.name) / "alias"
        alias.symlink_to(self.repo.parent, target_is_directory=True)
        ancestor = validate_installed_repository(alias / self.repo.name)

        # Assert
        self.assertTrue(intermediate)
        self.assertTrue(ancestor)

    def test_installed_validator_rejects_root_replacement_during_state_read(self):
        # Arrange
        swapped = False
        blocked = False

        def attempt_replacement():
            nonlocal blocked, swapped
            if not swapped and not blocked:
                displaced = self.repo.with_name("displaced")
                try:
                    self.repo.rename(displaced)
                except PermissionError:
                    blocked = True
                    return
                shutil.copytree(displaced, self.repo)
                swapped = True

        original_read = os.read

        def replace_root_posix(descriptor, size):
            attempt_replacement()
            return original_read(descriptor, size)

        original_windows_read = validator_module._NativeWindowsApi.read

        def replace_root_windows(api, handle):
            attempt_replacement()
            return original_windows_read(api, handle)

        hook = (
            mock.patch.object(
                validator_module._NativeWindowsApi,
                "read",
                new=replace_root_windows,
            )
            if os.name == "nt"
            else mock.patch("os.read", side_effect=replace_root_posix)
        )

        # Act
        with hook:
            issues = validate_installed_repository(self.repo)

        # Assert
        self.assertTrue(swapped or blocked)
        if blocked:
            self.assertEqual("nt", os.name)
            self.assertFalse(self.repo.with_name("displaced").exists())
            self.assertEqual([], issues)
        else:
            self.assertTrue(issues)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires POSIX")
    def test_installed_validator_rejects_special_file_without_blocking(self):
        # Arrange
        fifo = self.repo / ".codex/agents/unsafe-fifo"
        os.mkfifo(fifo)

        # Act
        issues = validate_installed_repository(self.repo)

        # Assert
        self.assertTrue(any("special file" in issue.message for issue in issues))

    def test_installed_validator_rejects_deterministic_reparse_metadata(self):
        # Arrange
        metadata = types.SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o755,
            st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
            st_reparse_tag=0xA000000C,
        )

        # Act / Assert
        self.assertTrue(_SecureInstalledRoot._unsafe(metadata))

    def test_installed_validator_windows_pins_root_ancestors_with_secure_flags(self):
        # Arrange
        api = FakeWindowsApi({
            "C:\\": windows_directory(1),
            "C:\\games": windows_directory(2),
            "C:\\games\\repo": windows_directory(3),
        })

        # Act
        with _SecureInstalledRoot(Path("C:/games/repo"), windows_api=api):
            pass

        # Assert
        self.assertEqual(["C:\\", "C:\\games", "C:\\games\\repo", "C:\\games\\repo"], [call[0] for call in api.open_calls])
        self.assertTrue(all(call[1] & api.FILE_FLAG_OPEN_REPARSE_POINT for call in api.open_calls))
        self.assertTrue(all(call[1] & api.FILE_FLAG_BACKUP_SEMANTICS for call in api.open_calls))
        self.assertTrue(all(call[2] == api.FILE_SHARE_READ for call in api.open_calls))
        self.assertCountEqual(api.opened_handles, api.closed)

    def test_installed_validator_windows_shares_write_only_for_exact_manager_lock(self):
        # Arrange
        manager_lock = "C:\\repo\\.codex\\codex-game-studios\\manager.lock"
        similarly_named = "C:\\repo\\ordinary\\manager.lock"
        api = FakeWindowsApi(
            {
                "C:\\": windows_directory(1),
                "C:\\repo": windows_directory(2),
                "C:\\repo\\.codex": windows_directory(3),
                "C:\\repo\\.codex\\codex-game-studios": windows_directory(4),
                manager_lock: windows_file(5, b"manager"),
                "C:\\repo\\ordinary": windows_directory(6),
                similarly_named: windows_file(7, b"ordinary"),
            }
        )

        # Act
        with _SecureInstalledRoot(Path("C:/repo"), windows_api=api) as secure:
            secure.kind(".codex/codex-game-studios/manager.lock")
            secure.kind("ordinary/manager.lock")

        # Assert
        shares_by_path = {path: share for path, _, share in api.open_calls}
        self.assertEqual(
            api.FILE_SHARE_READ | api.FILE_SHARE_WRITE,
            shares_by_path[manager_lock],
        )
        self.assertEqual(api.FILE_SHARE_READ, shares_by_path[similarly_named])
        self.assertTrue(
            all(not (share & api.FILE_SHARE_DELETE) for _, _, share in api.open_calls)
        )
        self.assertTrue(
            all(
                share == api.FILE_SHARE_READ
                for path, _, share in api.open_calls
                if path != manager_lock
            )
        )
        self.assertCountEqual(api.opened_handles, api.closed)

    def test_installed_validator_windows_rejects_reparse_component_and_closes_handles(self):
        # Arrange
        api = FakeWindowsApi({
            "C:\\": windows_directory(1),
            "C:\\games": windows_directory(2, reparse=True),
        })

        # Act / Assert
        with self.assertRaisesRegex(OSError, "reparse"):
            with _SecureInstalledRoot(Path("C:/games/repo"), windows_api=api):
                pass
        self.assertCountEqual(api.opened_handles, api.closed)

    def test_installed_validator_windows_rejects_handle_final_path_substitution(self):
        # Arrange
        api = FakeWindowsApi({
            "C:\\": windows_directory(1),
            "C:\\repo": windows_directory(2),
            "C:\\repo\\state.bin": windows_file(3, b"\x00\xffpayload"),
        })

        # Act / Assert
        with _SecureInstalledRoot(Path("C:/repo"), windows_api=api) as secure:
            api.final_paths["C:\\repo\\state.bin"] = "C:\\outside\\state.bin"
            with self.assertRaisesRegex(OSError, "final path|chain"):
                secure.read("state.bin")
        self.assertCountEqual(api.opened_handles, api.closed)

    def test_installed_validator_windows_rejects_file_identity_substitution_during_read(self):
        # Arrange
        api = FakeWindowsApi({
            "C:\\": windows_directory(1),
            "C:\\repo": windows_directory(2),
            "C:\\repo\\state.bin": windows_file(3, b"\x00\xffpayload"),
        })
        api.mutate_identity_after_read.add("C:\\repo\\state.bin")

        # Act / Assert
        with _SecureInstalledRoot(Path("C:/repo"), windows_api=api) as secure:
            with self.assertRaisesRegex(OSError, "changed"):
                secure.read("state.bin")
        self.assertCountEqual(api.opened_handles, api.closed)

    def test_installed_validator_windows_rejects_root_directory_identity_substitution(self):
        # Arrange
        api = FakeWindowsApi({
            "C:\\": windows_directory(1),
            "C:\\repo": windows_directory(2),
        })

        # Act / Assert
        with self.assertRaisesRegex(OSError, "changed"):
            with _SecureInstalledRoot(Path("C:/repo"), windows_api=api):
                api.entries["C:\\repo"]["identity"] = (7, 2002)
        self.assertCountEqual(api.opened_handles, api.closed)

    def test_installed_validator_windows_accepts_canonical_alias_chain_but_rejects_escape(self):
        # Arrange
        requested_root = "D:\\profiles\\RUNNER~1\\repo"
        canonical_root = "D:\\profiles\\runneradmin\\repo"
        state_path = f"{canonical_root}\\state.bin"
        api = FakeWindowsApi(
            {
                "D:\\": windows_directory(1),
                "D:\\profiles": windows_directory(2),
                "D:\\profiles\\RUNNER~1": windows_directory(3),
                requested_root: windows_directory(4),
                state_path: windows_file(5, b"canonical"),
            }
        )
        api.final_paths["D:\\profiles\\RUNNER~1"] = "D:\\profiles\\runneradmin"
        api.final_paths[requested_root] = canonical_root

        # Act / Assert
        with _SecureInstalledRoot(
            Path("D:/profiles/RUNNER~1/repo"), windows_api=api
        ) as secure:
            self.assertEqual(b"canonical", secure.read("state.bin"))
            api.final_paths[state_path] = "C:\\escape\\state.bin"
            with self.assertRaisesRegex(OSError, "chain"):
                secure.read("state.bin")
        self.assertCountEqual(api.opened_handles, api.closed)

    def test_installed_validator_windows_reads_binary_bytes_exactly_and_rejects_special_files(self):
        # Arrange
        content = b"\x00\xff\x80binary\r\n"
        api = FakeWindowsApi({
            "C:\\": windows_directory(1),
            "C:\\repo": windows_directory(2),
            "C:\\repo\\state.bin": windows_file(3, content),
            "C:\\repo\\device": windows_file(4, b"", disk=False),
        })

        # Act
        with _SecureInstalledRoot(Path("C:/repo"), windows_api=api) as secure:
            actual = secure.read("state.bin")
            with self.assertRaisesRegex(OSError, "special"):
                secure.kind("device")

        # Assert
        self.assertEqual(content, actual)
        self.assertCountEqual(api.opened_handles, api.closed)

    def test_installed_validator_windows_walk_retains_directory_handles_until_recursion_finishes(self):
        # Arrange
        api = FakeWindowsApi({
            "C:\\": windows_directory(1),
            "C:\\repo": windows_directory(2, children=("dir", "top.bin")),
            "C:\\repo\\dir": windows_directory(3, children=("nested.bin",)),
            "C:\\repo\\dir\\nested.bin": windows_file(4, b"nested"),
            "C:\\repo\\top.bin": windows_file(5, b"top"),
        })

        # Act
        with _SecureInstalledRoot(Path("C:/repo"), windows_api=api) as secure:
            walked = secure.walk_files(".")

        # Assert
        self.assertEqual({"dir/nested.bin", "top.bin"}, walked)
        self.assertTrue(api.directory_handle_retained_during_list)
        self.assertCountEqual(api.opened_handles, api.closed)

    def test_installed_validator_windows_walk_reports_logical_reparse_path(self):
        # Arrange
        api = FakeWindowsApi({
            "C:\\": windows_directory(1),
            "C:\\repo": windows_directory(2),
            "C:\\repo\\.agents": windows_directory(3),
            "C:\\repo\\.agents\\skills": windows_directory(4),
            "C:\\repo\\.agents\\skills\\start": windows_directory(
                5, children=("escape",)
            ),
            "C:\\repo\\.agents\\skills\\start\\escape": windows_directory(
                6, reparse=True
            ),
        })

        # Act / Assert
        with _SecureInstalledRoot(Path("C:/repo"), windows_api=api) as secure:
            with self.assertRaisesRegex(
                OSError, r"\.agents/skills/start/escape"
            ):
                secure.walk_files(".agents/skills/start")
        self.assertCountEqual(api.opened_handles, api.closed)

    def test_installed_mode_reports_shared_block_and_owned_toml_tampering(self):
        # Arrange
        agents = self.repo / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8").replace("Codex", "Changed", 1), encoding="utf-8")
        config = self.repo / ".codex/config.toml"
        config.write_text(config.read_text(encoding="utf-8").replace("max_depth = 1", "max_depth = 9"), encoding="utf-8")

        # Act
        issues = validate_installed_repository(self.repo)

        # Assert
        paths = {issue.path for issue in issues}
        self.assertIn("AGENTS.md", paths)
        self.assertIn(".codex/config.toml", paths)

    def test_installed_mode_reports_unsafe_path_and_unrecorded_manager_write(self):
        # Arrange
        (self.repo / ".codex/codex-game-studios/unknown.txt").write_text("unexpected", encoding="utf-8")
        target = self.repo / "outside"
        target.write_text("outside", encoding="utf-8")
        (self.repo / ".agents/skills/start/escape").symlink_to(target)
        (self.repo / ".codex/agents/unrecorded.toml").write_text("manager residue", encoding="utf-8")

        # Act
        issues = validate_installed_repository(self.repo)

        # Assert
        paths = {issue.path for issue in issues}
        self.assertIn(".codex/codex-game-studios/unknown.txt", paths)
        self.assertTrue(any(issue.path == ".agents/skills/start/escape" or ".agents/skills/start/escape" in issue.message for issue in issues))
        self.assertIn(".codex/agents/unrecorded.toml", paths)

    def test_installed_mode_cli_and_manager_bridge_are_read_only(self):
        # Arrange
        before = snapshot_tree(self.repo)
        plugin_before = snapshot_tree(PLUGIN)
        command = [sys.executable, "-m", "tools.codex_studio.validate", "--root", str(self.repo), "--mode", "installed"]
        from studio_manager import validate_installed_read_only

        # Act
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        bridge_issues = validate_installed_read_only(self.repo, PLUGIN)

        # Assert
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("Codex Studio validation: PASS", completed.stdout)
        self.assertEqual([], bridge_issues)
        self.assertEqual(before, snapshot_tree(self.repo))
        self.assertEqual(plugin_before, snapshot_tree(PLUGIN))
        self.assertFalse(any(path.endswith("__pycache__") or "/__pycache__/" in path for path in snapshot_tree(self.repo)))

    def test_manager_bridge_rejects_rechecksummed_foreign_payload_and_version(self):
        # Arrange
        from studio_manager import ManagerError, validate_installed_read_only
        self._rewrite_state(lambda state: (state.__setitem__("payload_digest", "0" * 64), state.__setitem__("plugin_version", "9.9.9")))

        # Act / Assert
        with self.assertRaises(ManagerError):
            validate_installed_read_only(self.repo, PLUGIN)


def canonical_json_with_checksum(document: dict[str, object]) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def windows_directory(identity: int, *, reparse: bool = False, children: tuple[str, ...] = ()) -> dict[str, object]:
    return {"identity": (7, identity), "kind": "directory", "reparse": reparse, "disk": True, "content": b"", "children": children}


def windows_file(identity: int, content: bytes, *, disk: bool = True) -> dict[str, object]:
    return {"identity": (7, identity), "kind": "file", "reparse": False, "disk": disk, "content": content, "children": ()}


class FakeWindowsApi:
    """Deterministic handle API used to exercise the native-Windows validator path."""

    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_SHARE_READ = 0x1
    FILE_SHARE_WRITE = 0x2
    FILE_SHARE_DELETE = 0x4

    def __init__(self, entries: dict[str, dict[str, object]]):
        self.entries = entries
        self.final_paths = {path: path for path in entries}
        self.open_calls: list[tuple[str, int, int]] = []
        self.opened_handles: list[int] = []
        self.closed: list[int] = []
        self.handles: dict[int, str] = {}
        self.mutate_identity_after_read: set[str] = set()
        self.directory_handle_retained_during_list = True

    def open(self, path: str, *, flags: int, share: int) -> int:
        if path not in self.entries:
            raise OSError(f"missing fake path: {path}")
        handle = len(self.opened_handles) + 100
        self.open_calls.append((path, flags, share))
        self.opened_handles.append(handle)
        self.handles[handle] = path
        return handle

    def close(self, handle: int) -> None:
        self.closed.append(handle)
        self.handles.pop(handle, None)

    def info(self, handle: int):
        path = self.handles[handle]
        entry = self.entries[path]
        return types.SimpleNamespace(
            identity=entry["identity"],
            kind=entry["kind"],
            reparse=entry["reparse"],
            disk=entry["disk"],
            size=len(entry["content"]),
            write_time=11,
        )

    def final_path(self, handle: int) -> str:
        return self.final_paths[self.handles[handle]]

    def read(self, handle: int) -> bytes:
        path = self.handles[handle]
        content = self.entries[path]["content"]
        if path in self.mutate_identity_after_read:
            volume, identity = self.entries[path]["identity"]
            self.entries[path]["identity"] = (volume, identity + 1000)
        return content

    def listdir(self, handle: int) -> list[str]:
        path = self.handles[handle]
        self.directory_handle_retained_during_list &= handle not in self.closed
        return list(self.entries[path]["children"])
