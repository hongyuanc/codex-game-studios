"""Contract tests for the deterministic operational plugin payload."""

from __future__ import annotations

import json
import hashlib
import ntpath
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"
MANIFEST = PLUGIN / "assets/payload-manifest.json"
sys.path.insert(0, str(PLUGIN / "scripts"))

from models import PayloadError, canonical_json, normalize_relative_path  # noqa: E402
from payload import (  # noqa: E402
    build_payload,
    load_manifest,
    load_verified_manifest,
    verify_payload,
    inventory_attestation,
)
from safe_fs import list_immediate_secure  # noqa: E402


class PayloadPathTests(unittest.TestCase):
    """Verify cross-platform payload path safety."""

    def test_payload_parent_traversal_is_rejected(self):
        # Arrange / Act / Assert
        with self.assertRaisesRegex(PayloadError, "parent traversal"):
            normalize_relative_path("../escape")

    def test_payload_unsafe_and_non_normalized_paths_are_rejected(self):
        # Arrange
        unsafe_paths = (
            "/absolute",
            "back\\slash",
            "nul\x00byte",
            "two//parts",
            "dot/./part",
            "Cafe\u0301.md",
            "CON",
            "trailing. ",
            "bad:name",
            "surrogate-\ud800",
        )

        # Act / Assert
        for unsafe_path in unsafe_paths:
            with self.subTest(path=repr(unsafe_path)):
                with self.assertRaises(PayloadError):
                    normalize_relative_path(unsafe_path)

    def test_payload_canonical_json_is_stable_and_newline_terminated(self):
        # Arrange
        value = {"z": 1, "a": "caf\u00e9"}

        # Act
        encoded = canonical_json(value)

        # Assert
        self.assertEqual(b'{"a":"caf\xc3\xa9","z":1}\n', encoded)


class PayloadGenerationTests(unittest.TestCase):
    """Verify generation, policy parity, and committed payload integrity."""

    def test_payload_inventory_attestation_matches_exact_manifest_projection(self):
        # Arrange
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        validator = (ROOT / "tools/codex_studio/validate.py").read_text(encoding="utf-8")
        projection = []
        for entry in manifest["entries"]:
            expected_hash = entry["sha256"] if entry["ownership"] == "dedicated" and entry["path"] != "tools/codex_studio/validate.py" else None
            projection.append([entry["path"], entry["ownership"], entry["merge"], entry["entry_type"], expected_hash])

        # Act
        digest = hashlib.sha256((json.dumps(projection, separators=(",", ":")) + "\n").encode()).hexdigest()

        # Assert
        self.assertEqual(515, len(projection))
        self.assertIn(f'_INSTALLED_INVENTORY_ENTRY_COUNT = {len(projection)}', validator)
        self.assertIn(f'_INSTALLED_INVENTORY_SHA256 = "{digest}"', validator)

    def test_payload_check_rejects_stale_generated_inventory_attestation(self):
        # Arrange
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", ".superpowers", "__pycache__"))
            validator = source / "tools/codex_studio/validate.py"
            validator.write_text(
                __import__("re").sub(
                    r'_INSTALLED_INVENTORY_SHA256 = "[0-9a-f]{64}"',
                    f'_INSTALLED_INVENTORY_SHA256 = "{"0" * 64}"',
                    validator.read_text(encoding="utf-8"),
                    count=1,
                ),
                encoding="utf-8",
            )

            # Act / Assert
            with self.assertRaisesRegex(PayloadError, "inventory attestation"):
                build_payload(source, source / "plugins/codex-game-studios", check=True)

    def test_payload_build_and_check_report_reviewed_attestation_without_source_mutation(self):
        # Arrange / Act / Assert
        expected_count, expected_digest = inventory_attestation(load_manifest(MANIFEST))
        expected_message = f"expected count={expected_count} sha256={expected_digest}"
        for check, malformed in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(check=check, malformed=malformed), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "source"
                shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", ".superpowers", "__pycache__"))
                validator = source / "tools/codex_studio/validate.py"
                original = validator.read_bytes()
                if malformed:
                    stale = original.replace(b"# payload-inventory-attestation:start", b"# malformed-attestation:start", 1)
                else:
                    stale = __import__("re").sub(
                        rb'_INSTALLED_INVENTORY_SHA256 = "[0-9a-f]{64}"',
                        b'_INSTALLED_INVENTORY_SHA256 = "' + b"0" * 64 + b'"',
                        original,
                        count=1,
                    )
                validator.write_bytes(stale)
                before = validator.read_bytes()

                with self.assertRaisesRegex(PayloadError, expected_message):
                    build_payload(source, source / "plugins/codex-game-studios", check=check)
                self.assertEqual(before, validator.read_bytes())
    def test_payload_verified_snapshot_consumes_one_manifest_object(self):
        # Arrange
        import payload

        # Act
        with mock.patch("payload.load_manifest", wraps=load_manifest) as loader:
            manifest = load_verified_manifest(PLUGIN)

        # Assert
        self.assertEqual(1, loader.call_count)
        self.assertEqual(load_manifest(MANIFEST), manifest)

    def test_windows_immediate_listing_pins_children_without_recursion(self):
        # Arrange
        import safe_fs

        class FakeApi:
            def __init__(self):
                self.paths = {}
                self.closed = []

            def create_file(self, path, access, share, disposition, flags):
                handle = len(self.paths) + 1
                self.paths[handle] = path
                return handle

            def attributes(self, handle):
                return safe_fs.FILE_ATTRIBUTE_DIRECTORY, 0

            def final_path(self, handle):
                return self.paths[handle]

            def close(self, handle):
                self.closed.append(handle)

        class Scan:
            def __enter__(self):
                return iter((types.SimpleNamespace(name="child"),))

            def __exit__(self, exc_type, exc, traceback):
                return None

        api = FakeApi()
        windows_root = Path(r"C:\repo")

        # Act
        with mock.patch("safe_fs._is_windows", return_value=True), mock.patch(
            "safe_fs._WindowsApi", return_value=api
        ), mock.patch("safe_fs.os.scandir", return_value=Scan()) as scandir:
            entries = list_immediate_secure(windows_root, "managed")

        # Assert
        self.assertEqual((safe_fs.ImmediateEntry("child", "directory", None),), entries)
        self.assertEqual(1, scandir.call_count)
        self.assertEqual(set(api.paths), set(api.closed))

    def test_windows_listing_allows_exact_cooperative_child_sharing(self):
        # Arrange
        import safe_fs

        class FakeApi:
            def __init__(self):
                self.calls = []
                self.paths = {}

            def create_file(self, path, access, share, disposition, flags):
                handle = len(self.calls) + 1
                self.calls.append((handle, path, access, share, disposition, flags))
                self.paths[handle] = path
                return handle

            def attributes(self, handle):
                name = ntpath.basename(self.paths[handle])
                if name in {
                    "manager.lock",
                    ".installation.json.transaction.tmp",
                    "unknown.txt",
                }:
                    return 0, 0
                return safe_fs.FILE_ATTRIBUTE_DIRECTORY, 0

            def final_path(self, handle):
                return self.paths[handle]

            def close(self, handle):
                return None

        class Scan:
            def __enter__(self):
                return iter(
                    (
                        types.SimpleNamespace(name="manager.lock"),
                        types.SimpleNamespace(
                            name=".installation.json.transaction.tmp"
                        ),
                        types.SimpleNamespace(name="unknown.txt"),
                    )
                )

            def __exit__(self, exc_type, exc, traceback):
                return None

        api = FakeApi()

        # Act
        with mock.patch("safe_fs._is_windows", return_value=True), mock.patch(
            "safe_fs._WindowsApi", return_value=api
        ), mock.patch("safe_fs.os.scandir", return_value=Scan()), mock.patch(
            "safe_fs._windows_descriptor_from_verified", return_value=91
        ) as descriptor, mock.patch(
            "safe_fs.os.fstat", return_value=types.SimpleNamespace()
        ), mock.patch(
            "safe_fs._hash_descriptor", return_value="a" * 64
        ), mock.patch("safe_fs.os.close"):
            entries = list_immediate_secure(
                Path(r"C:\repo"),
                ".codex/codex-game-studios",
                cooperative_children={".installation.json.transaction.tmp"},
            )

        # Assert
        child_calls = {ntpath.basename(call[1]): call for call in api.calls[1:]}
        self.assertEqual(
            safe_fs.FILE_SHARE_READ | safe_fs.FILE_SHARE_WRITE,
            child_calls["manager.lock"][3],
        )
        self.assertEqual(
            safe_fs.FILE_SHARE_READ
            | safe_fs.FILE_SHARE_WRITE
            | safe_fs.FILE_SHARE_DELETE,
            child_calls[".installation.json.transaction.tmp"][3],
        )
        self.assertEqual(safe_fs.FILE_SHARE_READ, child_calls["unknown.txt"][3])
        self.assertEqual(2, descriptor.call_count)
        self.assertEqual(
            (
                safe_fs.ImmediateEntry(
                    ".installation.json.transaction.tmp", "file", "a" * 64
                ),
                safe_fs.ImmediateEntry("manager.lock", "file", None),
                safe_fs.ImmediateEntry("unknown.txt", "file", "a" * 64),
            ),
            entries,
        )

    @unittest.skipIf(os.name == "nt", "POSIX descriptor behavior")
    def test_posix_manager_lock_listing_skips_hash_only_for_exact_path(self):
        # Arrange
        import safe_fs

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = root / ".codex/codex-game-studios"
            ordinary = root / "ordinary"
            manager.mkdir(parents=True)
            ordinary.mkdir()
            (manager / "manager.lock").write_bytes(b"manager")
            (manager / "unknown.txt").write_bytes(b"unknown")
            (ordinary / "manager.lock").write_bytes(b"ordinary")

            # Act
            with mock.patch(
                "safe_fs._hash_descriptor", return_value="a" * 64
            ) as hash_descriptor:
                manager_entries = list_immediate_secure(
                    root, ".codex/codex-game-studios"
                )
                ordinary_entries = list_immediate_secure(root, "ordinary")

        # Assert
        self.assertEqual(2, hash_descriptor.call_count)
        self.assertEqual(
            (
                safe_fs.ImmediateEntry("manager.lock", "file", None),
                safe_fs.ImmediateEntry("unknown.txt", "file", "a" * 64),
            ),
            manager_entries,
        )
        self.assertEqual(
            (safe_fs.ImmediateEntry("manager.lock", "file", "a" * 64),),
            ordinary_entries,
        )

    def test_payload_build_is_deterministic_and_source_identical(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temporary_directory:
            plugin = Path(temporary_directory) / "codex-game-studios"
            shutil.copytree(PLUGIN, plugin)

            # Act
            first_manifest = build_payload(ROOT, plugin)
            first_bytes = (plugin / "assets/payload-manifest.json").read_bytes()
            second_manifest = build_payload(ROOT, plugin)

            # Assert
            self.assertEqual(first_manifest, second_manifest)
            self.assertEqual(first_bytes, (plugin / "assets/payload-manifest.json").read_bytes())
            self.assertEqual([], verify_payload(plugin))
            for entry in second_manifest.entries:
                if entry.entry_type != "file":
                    continue
                payload_bytes = (plugin / "assets/studio" / entry.path).read_bytes()
                if entry.path == ".codex/codex-game-studios/legal/LICENSE":
                    source_bytes = (PLUGIN / "LICENSE").read_bytes()
                elif entry.path == ".codex/codex-game-studios/legal/ATTRIBUTION.md":
                    source_bytes = (PLUGIN / "ATTRIBUTION.md").read_bytes()
                else:
                    source_bytes = (ROOT / entry.path).read_bytes()
                self.assertEqual(source_bytes, payload_bytes, entry.path)

    def test_payload_policy_excludes_maintainer_material(self):
        # Arrange
        manifest = load_manifest(MANIFEST)

        # Act
        paths = {entry.path for entry in manifest.entries}

        # Assert
        for path in ("README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "UPGRADING.md"):
            self.assertNotIn(path, paths)
        self.assertFalse(any(path.startswith(".github/") for path in paths))
        self.assertFalse(any(path.startswith("docs/superpowers/") for path in paths))
        self.assertFalse(any(path.startswith(".superpowers/") for path in paths))
        self.assertFalse(any(path.startswith("production/migration/") for path in paths))
        self.assertFalse(any("__pycache__" in path or path.endswith(".pyc") for path in paths))
        self.assertIn(".agents/skills/start/SKILL.md", paths)
        self.assertIn(".codex/agents/producer.toml", paths)
        self.assertIn(".codex/agent-packs/godot/godot-specialist.toml", paths)
        self.assertIn("docs/engine-reference/unreal/VERSION.md", paths)
        self.assertIn("src/.gitkeep", paths)

    def test_payload_whitespace_exception_is_exact_and_preserves_governed_bytes(self):
        # Arrange
        relative = (
            "Codex Studio Testing Framework/skills/sprint/retrospective.md"
        )
        generated_relative = f"plugins/codex-game-studios/assets/studio/{relative}"
        generated = ROOT / generated_relative
        source = ROOT / relative
        attributes = ROOT / ".gitattributes"

        # Act
        exact = subprocess.run(
            ["git", "check-attr", "whitespace", "--", generated_relative],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        other_relative = "plugins/codex-game-studios/assets/studio/.codex/agents/producer.toml"
        other = subprocess.run(
            ["git", "check-attr", "whitespace", "--", other_relative],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        attribute_lines = [
            line for line in attributes.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        ]

        # Assert
        self.assertEqual(source.read_bytes(), generated.read_bytes())
        self.assertEqual(
            f"{generated_relative}: whitespace: -trailing-space",
            exact,
        )
        self.assertEqual(f"{other_relative}: whitespace: unspecified", other)
        self.assertEqual(
            [
                "* text=auto eol=lf",
                f'"{generated_relative}" whitespace=-trailing-space',
            ],
            attribute_lines,
        )

    def test_payload_policy_explicitly_denies_every_maintainer_scope(self):
        # Arrange
        policy_path = PLUGIN / "assets/payload-policy.json"

        # Act
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        exact = set(policy["denied_exact_paths"])
        prefixes = set(policy["denied_prefixes"])

        # Assert
        self.assertLessEqual(
            {"README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "UPGRADING.md"},
            exact,
        )
        self.assertLessEqual(
            {
                ".git/",
                ".github/",
                ".superpowers/",
                ".venv/",
                ".codex/codex-game-studios/recovery/",
                "docs/superpowers/",
                "production/migration/",
                "production/releases/",
                "production/session-logs/",
                "production/session-state/",
                "tests/plugin/",
            },
            prefixes,
        )

    def test_payload_policy_excludes_release_packager_but_keeps_runtime_tools(self):
        # Arrange
        policy = json.loads(
            (PLUGIN / "assets/payload-policy.json").read_text(encoding="utf-8")
        )

        # Act
        denied = set(policy["denied_exact_paths"])
        approved = {item["source"] for item in policy["approved_sources"]}

        # Assert
        self.assertIn("tools/codex_studio/package_plugin.py", denied)
        self.assertNotIn("tools/codex_studio/package_plugin.py", approved)
        self.assertLessEqual(
            {
                "tools/codex_studio/build_plugin_payload.py",
                "tools/codex_studio/engine_pack.py",
                "tools/codex_studio/validate.py",
            },
            approved,
        )

    def test_payload_manifest_has_actual_inventory_and_shared_strategies(self):
        # Arrange
        manifest = load_manifest(MANIFEST)
        file_entries = {entry.path: entry for entry in manifest.entries if entry.entry_type == "file"}

        # Act
        skill_count = sum(
            path.startswith(".agents/skills/") and path.endswith("/SKILL.md")
            for path in file_entries
        )
        core_agent_count = sum(
            path.startswith(".codex/agents/") and path.count("/") == 2 and path.endswith(".toml")
            for path in file_entries
        )
        engine_agent_count = sum(
            path.startswith(".codex/agent-packs/") and path.endswith(".toml")
            for path in file_entries
        )

        # Assert
        self.assertEqual(73, skill_count)
        self.assertEqual(34, core_agent_count)
        self.assertEqual(15, engine_agent_count)
        self.assertEqual("managed-block", file_entries["AGENTS.md"].merge)
        self.assertEqual("toml-keys", file_entries[".codex/config.toml"].merge)
        self.assertEqual("managed-block", file_entries[".gitignore"].merge)
        self.assertEqual("shared", file_entries["AGENTS.md"].ownership)
        self.assertEqual("dedicated", file_entries[".codex/hooks.json"].ownership)
        self.assertTrue(file_entries[".codex/codex-game-studios/legal/LICENSE"].required)
        self.assertTrue(file_entries[".codex/codex-game-studios/legal/ATTRIBUTION.md"].required)

    def test_payload_verifier_reports_tampering_and_unexpected_files(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temporary_directory:
            plugin = Path(temporary_directory) / "codex-game-studios"
            shutil.copytree(PLUGIN, plugin)
            tampered = plugin / "assets/studio/.codex/agents/producer.toml"
            unexpected = plugin / "assets/studio/unexpected.txt"

            # Act
            tampered.write_text("tampered\n", encoding="utf-8")
            unexpected.write_text("unexpected\n", encoding="utf-8")
            issues = verify_payload(plugin)

            # Assert
            self.assertTrue(any("sha256 mismatch" in issue and "producer.toml" in issue for issue in issues))
            self.assertTrue(any("unexpected payload path" in issue for issue in issues))

    def test_payload_verifier_rejects_links(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temporary_directory:
            plugin = Path(temporary_directory) / "codex-game-studios"
            shutil.copytree(PLUGIN, plugin)
            path = plugin / "assets/studio/.codex/agents/producer.toml"
            path.unlink()
            path.symlink_to(PLUGIN / "LICENSE")

            # Act
            issues = verify_payload(plugin)

            # Assert
            self.assertTrue(any("link or reparse point" in issue for issue in issues))

    def test_payload_manifest_rejects_duplicate_paths_and_version_drift(self):
        # Arrange
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            original = json.loads(MANIFEST.read_text(encoding="utf-8"))
            original["entries"].append(dict(original["entries"][0]))
            duplicate_manifest = temporary / "duplicate.json"
            duplicate_manifest.write_bytes(canonical_json(original))

            # Act / Assert
            with self.assertRaisesRegex(PayloadError, "duplicate payload path"):
                load_manifest(duplicate_manifest)

            mismatched_plugin = temporary / "plugin"
            shutil.copytree(PLUGIN, mismatched_plugin)
            plugin_manifest = mismatched_plugin / ".codex-plugin/plugin.json"
            plugin_data = json.loads(plugin_manifest.read_text(encoding="utf-8"))
            plugin_data["version"] = "9.9.9"
            plugin_manifest.write_bytes(canonical_json(plugin_data))
            self.assertTrue(any("version" in issue for issue in verify_payload(mismatched_plugin)))

    def test_payload_modes_are_normalized(self):
        # Arrange
        manifest = load_manifest(MANIFEST)

        # Act
        modes = {entry.mode for entry in manifest.entries}

        # Assert
        self.assertLessEqual(modes, {0o644, 0o755})

    def test_payload_verifier_rejects_symlinked_payload_ancestors(self):
        for relative in ("assets", "assets/studio", "assets/studio/.codex"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                plugin = Path(directory) / "plugin"
                shutil.copytree(PLUGIN, plugin)
                path = plugin / relative
                real = path.with_name(path.name + "-real")
                path.rename(real)
                path.symlink_to(real, target_is_directory=True)

                issues = verify_payload(plugin)

                self.assertTrue(
                    any("link or reparse point" in issue for issue in issues), issues
                )

    def test_payload_builder_rejects_symlinked_source_ancestor(self):
        for relative in (".codex", ".agents/skills/start"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "source"
                shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", ".superpowers"))
                plugin = source / "plugins/codex-game-studios"
                path = source / relative
                real = path.with_name(path.name + "-real")
                path.rename(real)
                path.symlink_to(real, target_is_directory=True)

                with self.assertRaisesRegex(PayloadError, "link or reparse point"):
                    build_payload(source, plugin)

    def test_secure_copy_detects_controlled_source_and_destination_swap_races(self):
        from safe_fs import copy_file_secure

        for swap_target in ("source", "destination"):
            with self.subTest(swap_target=swap_target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source_root = root / "source"
                destination_root = root / "destination"
                source_root.mkdir()
                destination_root.mkdir()
                (source_root / "file.txt").write_bytes(b"approved\n")
                replacement = root / "replacement.txt"
                replacement.write_bytes(b"replacement\n")
                source_backup = source_root / "file-original.txt"
                destination_backup = destination_root / "file-original.txt"
                rename_attempted = False
                rename_blocked = False

                import safe_fs
                original_copy_stream = safe_fs._copy_stream

                def swap_then_copy(source_fd, destination_fd):
                    nonlocal rename_attempted, rename_blocked
                    if swap_target == "source":
                        original = source_root / "file.txt"
                        backup = source_backup
                    else:
                        original = destination_root / "file.txt"
                        backup = destination_backup
                    rename_attempted = True
                    try:
                        original.rename(backup)
                    except PermissionError:
                        rename_blocked = True
                        raise
                    if swap_target == "source":
                        original.symlink_to(replacement)
                    else:
                        original.symlink_to(replacement)
                    return original_copy_stream(source_fd, destination_fd)

                with mock.patch("safe_fs._copy_stream", side_effect=swap_then_copy):
                    with self.assertRaises((PayloadError, PermissionError)) as caught:
                        copy_file_secure(
                            source_root,
                            "file.txt",
                            destination_root,
                            "file.txt",
                            0o644,
                        )
                self.assertTrue(rename_attempted)
                self.assertEqual(b"replacement\n", replacement.read_bytes())
                destination_path = destination_root / "file.txt"
                if isinstance(caught.exception, PermissionError):
                    self.assertEqual("nt", os.name)
                    self.assertTrue(rename_blocked)
                    self.assertEqual(
                        b"approved\n", (source_root / "file.txt").read_bytes()
                    )
                    self.assertFalse(source_backup.exists())
                    self.assertFalse(destination_backup.exists())
                    self.assertTrue(destination_path.is_file())
                    self.assertFalse(destination_path.is_symlink())
                    self.assertEqual(b"", destination_path.read_bytes())
                else:
                    self.assertFalse(rename_blocked)
                    self.assertRegex(
                        str(caught.exception), "changed during secure copy"
                    )
                    if swap_target == "source":
                        self.assertTrue((source_root / "file.txt").is_symlink())
                        self.assertEqual(b"approved\n", source_backup.read_bytes())
                        self.assertFalse(destination_backup.exists())
                        self.assertFalse(destination_path.is_symlink())
                        self.assertEqual(b"approved\n", destination_path.read_bytes())
                    else:
                        self.assertEqual(
                            b"approved\n", (source_root / "file.txt").read_bytes()
                        )
                        self.assertFalse(source_backup.exists())
                        self.assertTrue(destination_backup.exists())
                        self.assertTrue(destination_path.is_symlink())
                        self.assertEqual(
                            b"approved\n", destination_backup.read_bytes()
                        )

    def test_payload_policy_rejects_rogue_and_missing_root_inventory(self):
        for mutation in ("rogue", "rogue-directory", "missing"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "source"
                shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", ".superpowers"))
                plugin = source / "plugins/codex-game-studios"
                if mutation == "rogue":
                    rogue = source / ".agents/skills/rogue/SKILL.md"
                    rogue.parent.mkdir()
                    rogue.write_text("rogue\n", encoding="utf-8")
                elif mutation == "rogue-directory":
                    (source / ".agents/skills/rogue-empty").mkdir()
                else:
                    (source / ".agents/skills/start/SKILL.md").unlink()

                with self.assertRaisesRegex(PayloadError, "source inventory"):
                    build_payload(source, plugin)

    def test_payload_policy_requires_every_explicit_category_source(self):
        representatives = (
            ("standalone", ".codex/hooks.json"),
            ("nested", "src/ui/AGENTS.md"),
            ("shared", "AGENTS.md"),
            ("legal", "plugins/codex-game-studios/ATTRIBUTION.md"),
        )
        for category, relative in representatives:
            with self.subTest(category=category), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "source"
                shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", ".superpowers"))
                plugin = source / "plugins/codex-game-studios"
                (source / relative).unlink()

                with self.assertRaisesRegex(PayloadError, "approved source.*missing"):
                    build_payload(source, plugin)

    def test_payload_policy_rejects_malformed_duplicate_and_noncanonical_data(self):
        mutations = (
            ("wrong schema type", lambda policy: policy.__setitem__("schema_version", True)),
            ("duplicate root", lambda policy: policy["dedicated_roots"].append(policy["dedicated_roots"][0])),
            ("bad merge", lambda policy: policy["shared_files"][0].__setitem__("merge", "overwrite")),
            ("bad inventory shape", lambda policy: policy["approved_sources"].__setitem__(0, "bad")),
            ("bad provenance", lambda policy: policy["approved_sources"][0].__setitem__("provenance", "unknown")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                plugin = Path(directory) / "plugin"
                shutil.copytree(PLUGIN, plugin)
                policy_path = plugin / "assets/payload-policy.json"
                policy = json.loads(policy_path.read_text(encoding="utf-8"))
                mutate(policy)
                policy_path.write_bytes(canonical_json(policy))

                with self.assertRaisesRegex(PayloadError, "invalid payload policy"):
                    build_payload(ROOT, plugin)

        with tempfile.TemporaryDirectory() as directory:
            plugin = Path(directory) / "plugin"
            shutil.copytree(PLUGIN, plugin)
            policy_path = plugin / "assets/payload-policy.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy_path.write_text(json.dumps(policy, indent=4) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(PayloadError, "canonical JSON"):
                build_payload(ROOT, plugin)

    def test_payload_license_matches_approved_complete_mit_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", ".superpowers"))
            plugin = source / "plugins/codex-game-studios"
            license_path = plugin / "LICENSE"
            license_text = license_path.read_text(encoding="utf-8")
            license_path.write_text(license_text[: license_text.index("Permission is hereby")], encoding="utf-8")

            with self.assertRaisesRegex(PayloadError, "complete approved MIT license"):
                build_payload(source, plugin)

    def test_payload_policy_rejects_unmatched_provenance_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            plugin = Path(directory) / "plugin"
            shutil.copytree(PLUGIN, plugin)
            policy_path = plugin / "assets/payload-policy.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["approved_sources"].pop()
            policy_path.write_bytes(canonical_json(policy))

            with self.assertRaisesRegex(PayloadError, "source inventory"):
                build_payload(ROOT, plugin)

    @unittest.skipIf(os.name == "nt", "POSIX exact mode contract")
    def test_payload_verifier_rejects_exact_posix_mode_drift(self):
        for relative, mode in ((".codex/agents/producer.toml", 0o666), (".codex/agents", 0o777)):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                plugin = Path(directory) / "plugin"
                shutil.copytree(PLUGIN, plugin)
                (plugin / "assets/studio" / relative).chmod(mode)

                issues = verify_payload(plugin)

                self.assertTrue(any("mode mismatch" in issue for issue in issues), issues)

    def test_windows_mode_contract_detects_writable_state_drift(self):
        from safe_fs import mode_matches

        writable_file = type("FileStat", (), {"st_mode": stat.S_IFREG | stat.S_IWRITE})()
        readonly_file = type("FileStat", (), {"st_mode": stat.S_IFREG | stat.S_IREAD})()
        writable_directory = type("DirStat", (), {"st_mode": stat.S_IFDIR | stat.S_IWRITE})()
        readonly_directory = type("DirStat", (), {"st_mode": stat.S_IFDIR | stat.S_IREAD})()

        self.assertTrue(mode_matches(writable_file, 0o644, is_windows=True))
        self.assertFalse(mode_matches(readonly_file, 0o644, is_windows=True))
        self.assertTrue(mode_matches(writable_directory, 0o755, is_windows=True))
        self.assertFalse(mode_matches(readonly_directory, 0o755, is_windows=True))

    def test_windows_inspection_maps_only_missing_path_to_logical_missing_error(self):
        # Arrange
        import safe_fs

        root = Path("D:/repo")

        # Act / Assert
        for error, expected in (
            (FileNotFoundError(2, "missing"), PayloadError),
            (PermissionError(13, "denied"), PermissionError),
        ):
            with self.subTest(error=type(error).__name__), mock.patch.object(
                safe_fs.os, "name", "nt"
            ), mock.patch.object(
                safe_fs, "_windows_open_verified", side_effect=error
            ):
                with self.assertRaises(expected) as caught:
                    safe_fs.inspect_secure(root, "missing.txt")
                if isinstance(error, FileNotFoundError):
                    self.assertIn("cannot inspect payload path", str(caught.exception))
                else:
                    self.assertIs(caught.exception, error)

        pinned = types.SimpleNamespace(
            root=Path("D:/repo"), verify=lambda: None, _descriptor=None
        )
        filesystem = safe_fs.AnchoredFilesystem(pinned)
        with mock.patch.object(
            safe_fs.os, "name", "nt"
        ), mock.patch.object(
            safe_fs,
            "_windows_open_verified",
            side_effect=FileNotFoundError(2, "missing"),
        ):
            self.assertEqual(
                safe_fs.SecureEntry("missing", None, None, None),
                filesystem.observe("missing.txt"),
            )

    def test_windows_secure_open_contract_pins_handles_and_rejects_reparse_points(self):
        import safe_fs

        class FakeWindowsApi:
            def __init__(self, *, reparse_handle=None):
                self.calls = []
                self.closed = []
                self.reparse_handle = reparse_handle

            def create_file(self, path, access, share, disposition, flags):
                handle = len(self.calls) + 1
                self.calls.append((handle, path, access, share, disposition, flags))
                return handle

            def attributes(self, handle):
                if handle == self.reparse_handle:
                    return safe_fs.FILE_ATTRIBUTE_REPARSE_POINT, 1
                if handle < 3:
                    return safe_fs.FILE_ATTRIBUTE_DIRECTORY, 0
                return 0, 0

            def final_path(self, handle):
                return {
                    1: r"\\?\C:\repo",
                    2: r"\\?\C:\repo\directory",
                    3: r"\\?\C:\repo\directory\file.txt",
                }[handle]

            def close(self, handle):
                self.closed.append(handle)

            def create_directory(self, path):
                raise AssertionError("read open must not create directories")

        api = FakeWindowsApi()
        opened = safe_fs._windows_open_verified(
            Path(r"C:\repo"), "directory/file.txt",
            access=safe_fs.GENERIC_READ, share=safe_fs.FILE_SHARE_READ,
            disposition=safe_fs.OPEN_EXISTING, create_parents=False,
            final_directory=False, api=api,
        )
        with opened as handles:
            self.assertEqual(3, handles.final_handle)
            self.assertEqual((1, 2), handles.ancestor_handles)
            self.assertEqual([], api.closed)
            self.assertTrue(all(call[3] == safe_fs.FILE_SHARE_READ for call in api.calls))
            self.assertTrue(all(not call[3] & safe_fs.FILE_SHARE_WRITE for call in api.calls))
            self.assertTrue(all(not call[3] & safe_fs.FILE_SHARE_DELETE for call in api.calls))
        self.assertTrue(all(call[5] & safe_fs.FILE_FLAG_OPEN_REPARSE_POINT for call in api.calls))
        self.assertEqual(safe_fs.OPEN_EXISTING, api.calls[-1][4])
        self.assertEqual([3, 2, 1], api.closed)

        descriptor_api = FakeWindowsApi()
        descriptor_open = safe_fs._windows_open_verified(
            Path(r"C:\repo"), "directory/file.txt",
            access=safe_fs.GENERIC_READ | safe_fs.GENERIC_WRITE,
            share=0, disposition=safe_fs.CREATE_NEW,
            create_parents=False, final_directory=False, api=descriptor_api,
        )
        fake_msvcrt = mock.Mock()
        fake_msvcrt.open_osfhandle.return_value = 91
        with descriptor_open as handles:
            descriptor = safe_fs._windows_descriptor_from_verified(
                handles, os.O_RDWR, msvcrt_module=fake_msvcrt
            )
            self.assertEqual(91, descriptor)
            fake_msvcrt.open_osfhandle.assert_called_once_with(3, os.O_RDWR)
            self.assertEqual([], descriptor_api.closed)
            self.assertTrue(all(call[3] == 0 for call in descriptor_api.calls))
        self.assertEqual([2, 1], descriptor_api.closed)

        reparse_api = FakeWindowsApi(reparse_handle=2)
        with self.assertRaisesRegex(PayloadError, "link or reparse point"):
            with safe_fs._windows_open_verified(
                Path(r"C:\repo"),
                "directory/file.txt",
                access=safe_fs.GENERIC_READ,
                share=safe_fs.FILE_SHARE_READ,
                disposition=safe_fs.OPEN_EXISTING,
                create_parents=False,
                final_directory=False,
                api=reparse_api,
            ):
                self.fail("reparse handle must fail before yielding")

    def test_windows_secure_open_accepts_an_existing_verified_parent(self):
        # Arrange
        import safe_fs

        class ExistingParentApi:
            def __init__(self):
                self.calls = []
                self.created = []
                self.closed = []

            def create_directory(self, path):
                self.created.append(path)
                raise FileExistsError(183, "already exists")

            def create_file(self, path, access, share, disposition, flags):
                handle = len(self.calls) + 1
                self.calls.append((handle, path, access, share, disposition, flags))
                return handle

            def attributes(self, handle):
                if handle < 3:
                    return safe_fs.FILE_ATTRIBUTE_DIRECTORY, 0
                return 0, 0

            def final_path(self, handle):
                return {
                    1: r"\\?\C:\repo",
                    2: r"\\?\C:\repo\directory",
                    3: r"\\?\C:\repo\directory\file.txt",
                }[handle]

            def close(self, handle):
                self.closed.append(handle)

        api = ExistingParentApi()

        # Act
        try:
            opened = safe_fs._windows_open_verified(
                Path(r"C:\repo"),
                "directory/file.txt",
                access=safe_fs.GENERIC_READ,
                share=safe_fs.FILE_SHARE_READ,
                disposition=safe_fs.OPEN_EXISTING,
                create_parents=True,
                final_directory=False,
                api=api,
            )
        except FileExistsError as error:
            self.fail(f"existing parent was not reopened for verification: {error}")

        # Assert
        with opened as handles:
            self.assertEqual(3, handles.final_handle)
            self.assertEqual((1, 2), handles.ancestor_handles)
            self.assertEqual([r"C:\repo\directory"], api.created)
        self.assertEqual([3, 2, 1], api.closed)

    def test_windows_handle_contract_uses_verified_descriptor_attributes_and_directories(self):
        import safe_fs

        class FakeBasicInfo:
            def __init__(self, attributes):
                self.CreationTime = 11
                self.LastAccessTime = 22
                self.LastWriteTime = 33
                self.ChangeTime = 44
                self.FileAttributes = attributes

        class FakeWindowsApi:
            def __init__(self):
                self.calls = []
                self.closed = []
                self.set_calls = []

            def create_file(self, path, access, share, disposition, flags):
                handle = len(self.calls) + 1
                self.calls.append((handle, path, access, share, disposition, flags))
                return handle

            def attributes(self, handle):
                return (safe_fs.FILE_ATTRIBUTE_DIRECTORY if handle in {1, 2, 3} else 0), 0

            def final_path(self, handle):
                return {
                    1: r"\\?\C:\repo",
                    2: r"\\?\C:\repo\directory",
                    3: r"\\?\C:\repo\directory\child",
                }[handle]

            def close(self, handle):
                self.closed.append(handle)

            def create_directory(self, path):
                return None

            def basic_info(self, handle):
                return FakeBasicInfo(safe_fs.FILE_ATTRIBUTE_DIRECTORY | 0x20)

            def set_basic_info(self, handle, information):
                self.set_calls.append((handle, information))

        api = FakeWindowsApi()
        opened = safe_fs._windows_open_verified(
            Path(r"C:\repo"), "directory/child",
            access=safe_fs.GENERIC_READ | safe_fs.FILE_WRITE_ATTRIBUTES,
            share=0, disposition=safe_fs.OPEN_EXISTING,
            create_parents=False, final_directory=True, api=api,
        )
        with opened as handles:
            self.assertEqual([], api.closed)
            self.assertTrue(api.calls[-1][5] & safe_fs.FILE_FLAG_BACKUP_SEMANTICS)
            safe_fs._windows_set_writable(api, handles.final_handle, writable=False)
            handle, information = api.set_calls[-1]
            self.assertEqual(handles.final_handle, handle)
            self.assertTrue(information.FileAttributes & safe_fs.FILE_ATTRIBUTE_READONLY)
            self.assertEqual((11, 22, 33, 44), (
                information.CreationTime, information.LastAccessTime,
                information.LastWriteTime, information.ChangeTime,
            ))
            self.assertEqual([], api.closed)
        self.assertEqual([3, 2, 1], api.closed)

        class EmptyScandir:
            def __init__(self, pinned_api):
                self.pinned_api = pinned_api

            def __call__(self, path):
                self.assertion = self.pinned_api.closed == []
                return self

            def __enter__(self):
                self.assertion = self.assertion and self.pinned_api.closed == []
                return iter(())

            def __exit__(self, exc_type, exc, traceback):
                return None

        listing_api = FakeWindowsApi()
        listing_api.final_path = lambda handle: {
            1: r"\\?\C:\base",
            2: r"\\?\C:\base\repo",
        }[handle]
        listing_api.attributes = lambda handle: (safe_fs.FILE_ATTRIBUTE_DIRECTORY, 0)
        listing_api.basic_info = lambda handle: FakeBasicInfo(safe_fs.FILE_ATTRIBUTE_DIRECTORY)
        scandir = EmptyScandir(listing_api)
        self.assertEqual(
            {}, safe_fs._walk_tree_windows(Path("repo"), api=listing_api, scandir=scandir)
        )
        self.assertTrue(scandir.assertion)
        self.assertEqual([2, 1], listing_api.closed)

    def test_windows_writable_update_skips_redundant_attribute_write(self):
        # Arrange
        import safe_fs

        information = safe_fs._FileBasicInfo(
            11, 22, 33, 44, safe_fs.FILE_ATTRIBUTE_DIRECTORY
        )
        api = mock.Mock()
        api.basic_info.return_value = information

        # Act
        safe_fs._windows_set_writable(api, 17, writable=True)

        # Assert
        api.set_basic_info.assert_not_called()

    def test_payload_policy_enforces_exact_semantics_for_every_category(self):
        import payload

        base_policy = json.loads((PLUGIN / "assets/payload-policy.json").read_text(encoding="utf-8"))
        representatives = {
            category: next(item for item in base_policy["approved_sources"] if item["category"] == category)
            for category in ("dedicated-root", "standalone", "nested-instruction", "shared", "legal")
        }
        mutations = ("target", "ownership", "merge", "category", "provenance")
        for category, representative in representatives.items():
            for mutation in mutations:
                with self.subTest(category=category, mutation=mutation), tempfile.TemporaryDirectory() as directory:
                    policy_data = json.loads(json.dumps(base_policy))
                    item = next(
                        candidate for candidate in policy_data["approved_sources"]
                        if candidate["source"] == representative["source"]
                    )
                    if mutation == "target":
                        item["target"] = "illegal-remap/" + Path(item["target"]).name
                    elif mutation == "ownership":
                        item["ownership"] = "shared" if item["ownership"] == "dedicated" else "dedicated"
                        item["merge"] = "managed-block" if item["ownership"] == "shared" else None
                    elif mutation == "merge":
                        if item["ownership"] == "shared":
                            item["merge"] = "toml-keys" if item["merge"] != "toml-keys" else "managed-block"
                        else:
                            item["ownership"] = "shared"
                            item["merge"] = "toml-keys"
                    elif mutation == "category":
                        item["category"] = "shared" if category != "shared" else "standalone"
                    else:
                        alternatives = {"codex-native", "upstream-adapted", "upstream-legal"}
                        item["provenance"] = sorted(alternatives - {item["provenance"]})[0]
                    policy_path = Path(directory) / "payload-policy.json"
                    policy_path.write_bytes(canonical_json(policy_data))

                    with self.assertRaisesRegex(PayloadError, "invalid payload policy"):
                        payload._load_policy(policy_path)


if __name__ == "__main__":
    unittest.main()
