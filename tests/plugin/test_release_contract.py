"""Release packaging, version, documentation, and CI contract tests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"
WORKFLOW = ROOT / ".github/workflows/plugin-ci.yml"


def release_tag_matches_version(tag: str, version: str) -> bool:
    """Return whether a stable or prerelease tag belongs to the plugin version."""

    version_pattern = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    if re.fullmatch(version_pattern, version) is None:
        return False
    identifier = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    return re.fullmatch(
        rf"v{re.escape(version)}(?:-{identifier}(?:\.{identifier})*)?",
        tag,
    ) is not None


class ReleaseContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.output = Path(self.temporary_directory.name) / "dist"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def assert_release_workflow_contract(self, workflow):
        self.assertEqual({"contents": "read"}, workflow["permissions"])
        jobs = workflow["jobs"]
        self.assertEqual(
            {"native-plugin", "studio", "windows-lifecycle-smoke", "release"},
            set(jobs),
        )
        native = jobs["native-plugin"]
        studio = jobs["studio"]
        windows_smoke = jobs["windows-lifecycle-smoke"]
        release = jobs["release"]
        self.assertEqual(
            ["ubuntu-latest", "macos-latest", "windows-latest"],
            native["strategy"]["matrix"]["os"],
        )
        self.assertEqual("${{ matrix.os }}", native["runs-on"])
        self.assertEqual(
            [
                "python -m unittest discover -s tests/plugin -v",
                "python tools/codex_studio/build_plugin_payload.py --root . --check",
                "python -m tools.codex_studio.validate --root . --mode source --phase final",
            ],
            [step["run"] for step in native["steps"] if "run" in step],
        )
        self.assertEqual(
            ["actions/checkout@v4", "actions/setup-python@v5"],
            [step["uses"] for step in native["steps"] if "uses" in step],
        )
        self.assertEqual("ubuntu-latest", studio["runs-on"])
        self.assertEqual(
            ["python -m unittest discover -s tests/studio -v"],
            [step["run"] for step in studio["steps"] if "run" in step],
        )
        self.assertEqual(
            ["actions/checkout@v4", "actions/setup-python@v5"],
            [step["uses"] for step in studio["steps"] if "uses" in step],
        )
        self.assertEqual("windows-latest", windows_smoke["runs-on"])
        self.assertEqual(
            [
                "python -m unittest tests.plugin.test_lifecycle_integration."
                "LifecycleIntegrationTests."
                "test_windows_update_replaces_existing_installation_state -v"
            ],
            [step["run"] for step in windows_smoke["steps"] if "run" in step],
        )
        self.assertEqual(
            ["actions/checkout@v4", "actions/setup-python@v5"],
            [step["uses"] for step in windows_smoke["steps"] if "uses" in step],
        )
        self.assertEqual(
            ["native-plugin", "studio", "windows-lifecycle-smoke"],
            release["needs"],
        )
        self.assertEqual(
            ["python tools/codex_studio/package_plugin.py --root . --output dist"],
            [step["run"] for step in release["steps"] if "run" in step],
        )
        self.assertEqual(
            [
                "actions/checkout@v4",
                "actions/setup-python@v5",
                "actions/upload-artifact@v4",
            ],
            [step["uses"] for step in release["steps"] if "uses" in step],
        )
        upload = release["steps"][-1]
        self.assertEqual(
            {
                "name": "codex-game-studios-plugin",
                "path": (
                    "dist/codex-game-studios-*.zip\n"
                    "dist/codex-game-studios-*.zip.sha256\n"
                ),
                "if-no-files-found": "error",
            },
            upload["with"],
        )

    def test_release_versions_and_tag_contract_match(self):
        # Arrange
        plugin = json.loads(
            (PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        payload = json.loads(
            (PLUGIN / "assets/payload-manifest.json").read_text(encoding="utf-8")
        )

        # Act
        tag = os.environ.get("GITHUB_REF_NAME")

        # Assert
        self.assertEqual(plugin["version"], payload["version"])
        if tag and tag.startswith("v"):
            self.assertTrue(release_tag_matches_version(tag, plugin["version"]))

    def test_byte_exact_release_inputs_force_lf_checkouts(self):
        # Arrange
        paths = (
            ".gitattributes",
            "AGENTS.md",
            ".codex/hooks/hook_runner.py",
            "plugins/codex-game-studios/assets/payload-manifest.json",
            "plugins/codex-game-studios/assets/payload-policy.json",
            "plugins/codex-game-studios/assets/studio/AGENTS.md",
            "plugins/codex-game-studios/scripts/payload.py",
            "tests/plugin/fixtures/shared-files/agents-existing.md",
        )

        # Act
        completed = subprocess.run(
            ["git", "check-attr", "eol", "--", *paths],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )

        # Assert
        self.assertEqual(
            [f"{path}: eol: lf" for path in paths],
            completed.stdout.splitlines(),
        )

    def test_release_tag_contract_accepts_stable_and_semver_prerelease_tags(self):
        # Arrange
        version = "1.0.0"
        accepted = (
            "v1.0.0",
            "v1.0.0-rc.1",
            "v1.0.0-alpha",
            "v1.0.0-alpha.1",
            "v1.0.0-0A-0",
            "v1.0.0--rc.1",
        )
        rejected = (
            "v1.0.1",
            "v2.0.0-rc.1",
            "v1.0.0-rc.01",
            "v1.0.0-rc.",
            "v1.0.0-rc..1",
            "v1.0.0+build.1",
            "v1.0.0-rc.1+build.1",
            "1.0.0-rc.1",
        )

        # Act
        accepted_results = [release_tag_matches_version(tag, version) for tag in accepted]
        rejected_results = [release_tag_matches_version(tag, version) for tag in rejected]

        # Assert
        self.assertEqual([True] * len(accepted), accepted_results)
        self.assertEqual([False] * len(rejected), rejected_results)

    def test_documented_prerelease_tags_match_declared_plugin_version(self):
        # Arrange
        plugin = json.loads(
            (PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        documents = (ROOT / "README.md", PLUGIN / "README.md")

        # Act
        documented_tags = [
            match.group(1)
            for document in documents
            for match in re.finditer(
                r"codex plugin marketplace add hongyuanc/codex-game-studios --ref (v\S+)",
                document.read_text(encoding="utf-8"),
            )
        ]

        # Assert
        self.assertEqual(["v1.0.0-rc.1", "v1.0.0-rc.1"], documented_tags)
        self.assertTrue(
            all(
                release_tag_matches_version(tag, plugin["version"])
                for tag in documented_tags
            )
        )

    def test_release_archive_is_deterministic_and_checksummed(self):
        # Arrange
        from tools.codex_studio.package_plugin import package_plugin

        # Act
        first = package_plugin(ROOT, self.output)
        first_bytes = first.archive.read_bytes()
        second = package_plugin(ROOT, self.output)

        # Assert
        self.assertEqual(first.archive_sha256, second.archive_sha256)
        self.assertEqual(first_bytes, second.archive.read_bytes())
        self.assertEqual(
            f"{second.archive_sha256}  {second.archive.name}\n",
            second.checksum.read_text(encoding="ascii"),
        )
        self.assertEqual(
            second.archive_sha256,
            hashlib.sha256(second.archive.read_bytes()).hexdigest(),
        )

    def test_release_archive_contains_only_sorted_plugin_posix_entries(self):
        # Arrange
        from tools.codex_studio.package_plugin import package_plugin

        # Act
        result = package_plugin(ROOT, self.output)
        with zipfile.ZipFile(result.archive) as archive:
            infos = archive.infolist()

        # Assert
        names = [info.filename for info in infos]
        self.assertEqual(sorted(names), names)
        self.assertTrue(names)
        self.assertTrue(
            all(
                name.startswith("plugins/codex-game-studios/")
                and "\\" not in name
                and not PurePosixPath(name).is_absolute()
                for name in names
            )
        )
        self.assertTrue(
            all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos)
        )
        self.assertIn(
            "plugins/codex-game-studios/.codex-plugin/plugin.json", names
        )
        self.assertIn("plugins/codex-game-studios/LICENSE", names)
        self.assertIn("plugins/codex-game-studios/ATTRIBUTION.md", names)

    def test_release_packager_rejects_links_and_special_files(self):
        # Arrange
        from tools.codex_studio.package_plugin import package_plugin

        cases = ("symlink", "special")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "repository"
                shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "dist"))
                hostile = root / "plugins/codex-game-studios/hostile"
                if case == "symlink":
                    hostile.symlink_to("README.md")
                else:
                    if not hasattr(os, "mkfifo"):
                        continue
                    os.mkfifo(hostile)

                # Act / Assert
                with self.assertRaisesRegex(ValueError, "link|reparse|special"):
                    package_plugin(root, root / "dist")

    def test_release_packager_rejects_symlinked_plugin_root_and_cache_entry(self):
        # Arrange
        from tools.codex_studio.package_plugin import package_plugin

        cases = ("plugins ancestor", "plugin root", "cache entry")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "repository"
                shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "dist"))
                plugin = root / "plugins/codex-game-studios"
                if case == "plugins ancestor":
                    plugins = plugin.parent
                    real_plugins = plugins.with_name("plugins-real")
                    plugins.rename(real_plugins)
                    plugins.symlink_to(real_plugins.name, target_is_directory=True)
                elif case == "plugin root":
                    real_plugin = plugin.with_name("codex-game-studios-real")
                    plugin.rename(real_plugin)
                    plugin.symlink_to(real_plugin.name, target_is_directory=True)
                else:
                    cache = plugin / "__pycache__"
                    cache.mkdir()
                    (cache / "forbidden.pyc").symlink_to("../README.md")
                    output = root / "dist"
                    output.mkdir()
                    stale_archive = output / "codex-game-studios-1.0.0.zip"
                    stale_checksum = output / f"{stale_archive.name}.sha256"
                    stale_archive.write_bytes(b"stale")
                    stale_checksum.write_bytes(b"stale")

                # Act / Assert
                with self.assertRaisesRegex(ValueError, "link|reparse"):
                    package_plugin(root, root / "dist")
                if case == "cache entry":
                    self.assertFalse(stale_archive.exists())
                    self.assertFalse(stale_checksum.exists())

    def test_release_packager_ignores_only_regular_bytecode_in_cache_trees(self):
        # Arrange
        from tools.codex_studio.package_plugin import package_plugin

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repository"
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "dist"))
            cache = root / "plugins/codex-game-studios/__pycache__/nested"
            cache.mkdir(parents=True)
            allowed = cache / "manager.cpython-311.pyc"
            allowed.write_bytes(b"cache bytes")

            # Act
            result = package_plugin(root, root / "dist")
            with zipfile.ZipFile(result.archive) as archive:
                names = archive.namelist()

            # Assert
            self.assertNotIn(
                "plugins/codex-game-studios/__pycache__/nested/manager.cpython-311.pyc",
                names,
            )
            unexpected = cache / "notes.txt"
            unexpected.write_text("not bytecode", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unexpected regular file"):
                package_plugin(root, root / "dist")

    def test_release_packager_rejects_swap_to_link_after_inventory(self):
        # Arrange
        import tools.codex_studio.package_plugin as packager

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repository"
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "dist"))
            target = (root / "plugins/codex-game-studios/README.md").resolve()
            backup = target.with_name("README.original")
            original_lstat = Path.lstat
            swapped = False
            blocked = False

            def lstat_then_swap(path, *args, **kwargs):
                nonlocal blocked, swapped
                observed = original_lstat(path, *args, **kwargs)
                if Path(path) == target and not swapped:
                    try:
                        target.rename(backup)
                    except PermissionError:
                        blocked = True
                        raise
                    target.symlink_to(backup.name)
                    swapped = True
                return observed

            # Act / Assert
            with mock.patch.object(Path, "lstat", new=lstat_then_swap):
                with self.assertRaises((ValueError, PermissionError)) as caught:
                    packager.package_plugin(root, root / "dist")
            if isinstance(caught.exception, PermissionError):
                self.assertEqual("nt", os.name)
                self.assertTrue(blocked)
                self.assertFalse(swapped)
                self.assertTrue(target.is_file())
                self.assertFalse(backup.exists())
            else:
                self.assertRegex(str(caught.exception), "link|changed|identity")
                self.assertTrue(swapped)

    def assert_regular_swap_rejected(self, target_relative, attacker_bytes):
        import tools.codex_studio.package_plugin as packager

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repository"
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "dist"))
            target = (root / target_relative).resolve()
            approved_stash = root / "approved-file"
            attacker = root / "attacker-file"
            attacker.write_bytes(attacker_bytes)
            output = root / "dist"
            archive = output / "codex-game-studios-1.0.0.zip"
            checksum = output / f"{archive.name}.sha256"
            original_manager_api = packager._manager_api
            api = original_manager_api(root / "plugins/codex-game-studios")
            filesystem_type = api[3]
            attacked = False
            blocked = False

            def swap_in_attacker():
                nonlocal blocked
                try:
                    target.rename(approved_stash)
                except PermissionError:
                    blocked = True
                    raise
                attacker.rename(target)

            def restore_approved():
                target.rename(attacker)
                approved_stash.rename(target)

            class AdversarialFilesystem(filesystem_type):
                def read_file(self, relative, expected=None):
                    nonlocal attacked
                    if relative == target_relative and not attacked:
                        before = self.observe(relative)
                        self.assert_matches(before, expected)
                        swap_in_attacker()
                        try:
                            contents = target.read_bytes()
                        finally:
                            restore_approved()
                        after = self.observe(relative)
                        self.assert_matches(after, before)
                        attacked = True
                        return contents
                    return super().read_file(relative, expected=expected)

                def read_file_verified(
                    self, relative, *, expected_digest, expected_mode
                ):
                    nonlocal attacked
                    if relative == target_relative and not attacked:
                        swap_in_attacker()
                        try:
                            return super().read_file_verified(
                                relative,
                                expected_digest=expected_digest,
                                expected_mode=expected_mode,
                            )
                        finally:
                            restore_approved()
                            attacked = True
                    return super().read_file_verified(
                        relative,
                        expected_digest=expected_digest,
                        expected_mode=expected_mode,
                    )

                @staticmethod
                def assert_matches(observed, expected):
                    if expected is None or not filesystem_type.matches(
                        observed, expected
                    ):
                        raise AssertionError("test adversary lost approved identity")

            adversarial_api = (*api[:3], AdversarialFilesystem, api[4])

            # Act / Assert
            with mock.patch.object(
                packager, "_manager_api", return_value=adversarial_api
            ):
                with self.assertRaises((ValueError, PermissionError)) as caught:
                    packager.package_plugin(root, output)
            if isinstance(caught.exception, PermissionError):
                self.assertEqual("nt", os.name)
                self.assertTrue(blocked)
                self.assertFalse(attacked)
                self.assertTrue(target.is_file())
                self.assertTrue(attacker.is_file())
            else:
                self.assertRegex(str(caught.exception), "bytes|mode|changed")
                self.assertTrue(attacked)
            self.assertFalse(archive.exists())
            self.assertFalse(checksum.exists())

    def test_release_packager_binds_actual_read_handle_to_inventory_bytes(self):
        # Arrange / Act / Assert
        self.assert_regular_swap_rejected(
            "plugins/codex-game-studios/README.md",
            b"different regular file bytes\n",
        )

    def test_release_packager_binds_manifest_read_to_observed_bytes(self):
        # Arrange / Act / Assert
        self.assert_regular_swap_rejected(
            "plugins/codex-game-studios/.codex-plugin/plugin.json",
            b'{"forged":true,"version":"1.0.0"}\n',
        )

    def test_release_packager_rejects_stale_payload_and_version_mismatch(self):
        # Arrange
        from tools.codex_studio.package_plugin import package_plugin

        cases = ("stale payload", "version mismatch")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "repository"
                shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "dist"))
                if case == "stale payload":
                    source = root / "tools/codex_studio/validate.py"
                    source.write_text(
                        source.read_text(encoding="utf-8") + "\n# stale release fixture\n",
                        encoding="utf-8",
                    )
                    expected = "release-ready"
                else:
                    manifest_path = (
                        root
                        / "plugins/codex-game-studios/.codex-plugin/plugin.json"
                    )
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["version"] = "9.9.9"
                    manifest_path.write_text(
                        json.dumps(manifest, sort_keys=True, separators=(",", ":"))
                        + "\n",
                        encoding="utf-8",
                    )
                    expected = "version"

                # Act / Assert
                with self.assertRaisesRegex(ValueError, expected):
                    package_plugin(root, root / "dist")

    def test_release_packager_failure_removes_preexisting_final_outputs(self):
        # Arrange
        from tools.codex_studio.package_plugin import package_plugin

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repository"
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "dist"))
            output = root / "dist"
            output.mkdir()
            archive = output / "codex-game-studios-1.0.0.zip"
            checksum = output / f"{archive.name}.sha256"
            archive.write_bytes(b"stale archive")
            checksum.write_bytes(b"stale checksum")
            source = root / "tools/codex_studio/validate.py"
            source.write_text(
                source.read_text(encoding="utf-8") + "\n# stale fixture\n",
                encoding="utf-8",
            )

            # Act / Assert
            with self.assertRaisesRegex(ValueError, "release-ready"):
                package_plugin(root, output)
            self.assertFalse(archive.exists())
            self.assertFalse(checksum.exists())

    def test_release_packager_early_failure_cleans_only_plugin_outputs(self):
        # Arrange
        from tools.codex_studio.package_plugin import package_plugin

        cases = ("malformed manifest", "untrusted version")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "repository"
                shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "dist"))
                output = root / "dist"
                output.mkdir()
                stale = (
                    output / "codex-game-studios-1.0.0.zip",
                    output / "codex-game-studios-1.0.0.zip.sha256",
                    output / ".codex-game-studios-1.0.0.zip.deadbeef.tmp",
                    output / ".codex-game-studios-1.0.0.zip.sha256.deadbeef.tmp",
                )
                for path in stale:
                    path.write_bytes(b"stale")
                unrelated = {
                    output / "other-plugin-1.0.0.zip": b"other plugin",
                    output / "codex-game-studios-not-an-archive.txt": b"notes",
                    output / "codex-game-studios-1.0.0.zip.backup": b"backup",
                }
                for path, contents in unrelated.items():
                    path.write_bytes(contents)
                manifest_path = (
                    root / "plugins/codex-game-studios/.codex-plugin/plugin.json"
                )
                if case == "malformed manifest":
                    manifest_path.write_text("{malformed", encoding="utf-8")
                    expected = "manifest"
                else:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["version"] = "9.9.9"
                    manifest_path.write_text(
                        json.dumps(manifest, sort_keys=True, separators=(",", ":"))
                        + "\n",
                        encoding="utf-8",
                    )
                    expected = "version"

                # Act / Assert
                with self.assertRaisesRegex(ValueError, expected):
                    package_plugin(root, output)
                self.assertTrue(all(not path.exists() for path in stale))
                self.assertEqual(
                    {path: path.read_bytes() for path in unrelated}, unrelated
                )

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX special files")
    def test_release_packager_cleanup_unlinks_links_and_specials_without_following(self):
        # Arrange
        from tools.codex_studio.package_plugin import package_plugin

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repository"
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "dist"))
            output = root / "dist"
            output.mkdir()
            outside = root / "outside.zip"
            outside.write_bytes(b"must survive")
            archive = output / "codex-game-studios-1.0.0.zip"
            checksum = output / "codex-game-studios-1.0.0.zip.sha256"
            archive.symlink_to(outside)
            os.mkfifo(checksum)
            manifest = root / "plugins/codex-game-studios/.codex-plugin/plugin.json"
            manifest.write_text("{malformed", encoding="utf-8")

            # Act / Assert
            with self.assertRaisesRegex(ValueError, "manifest"):
                package_plugin(root, output)
            self.assertFalse(os.path.lexists(archive))
            self.assertFalse(os.path.lexists(checksum))
            self.assertEqual(b"must survive", outside.read_bytes())

    def test_release_packager_cleanup_retries_a_replaced_artifact_name(self):
        # Arrange
        import tools.codex_studio.package_plugin as packager

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repository"
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "dist"))
            output = root / "dist"
            output.mkdir()
            archive = output / "codex-game-studios-1.0.0.zip"
            archive.write_bytes(b"stale")
            manifest = root / "plugins/codex-game-studios/.codex-plugin/plugin.json"
            manifest.write_text("{malformed", encoding="utf-8")
            real_unlink = os.unlink
            raced = False

            def replace_once(path, *args, dir_fd=None, **kwargs):
                nonlocal raced
                matches_posix = path == archive.name and dir_fd is not None
                matches_windows = (
                    os.name == "nt" and Path(path).resolve() == archive.resolve()
                )
                if (matches_posix or matches_windows) and not raced:
                    real_unlink(path, dir_fd=dir_fd)
                    if dir_fd is None:
                        archive.write_bytes(b"replacement")
                    else:
                        descriptor = os.open(
                            path,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=dir_fd,
                        )
                        os.write(descriptor, b"replacement")
                        os.close(descriptor)
                    raced = True
                    raise FileNotFoundError(path)
                return real_unlink(path, *args, dir_fd=dir_fd, **kwargs)

            # Act / Assert
            with mock.patch.object(packager.os, "unlink", side_effect=replace_once):
                with self.assertRaisesRegex(ValueError, "manifest"):
                    packager.package_plugin(root, output)
            self.assertTrue(raced)
            self.assertFalse(archive.exists())

    def test_release_packager_finalization_failure_removes_all_outputs(self):
        # Arrange
        import tools.codex_studio.package_plugin as packager

        output = self.output.resolve()
        archive = output / "codex-game-studios-1.0.0.zip"
        checksum = output / f"{archive.name}.sha256"
        real_replace = os.replace

        def fail_checksum_replace(source, destination, *args, **kwargs):
            destination_path = Path(destination)
            if not destination_path.is_absolute():
                destination_path = output / destination_path
            if destination_path == checksum:
                raise OSError("injected checksum finalization failure")
            return real_replace(source, destination, *args, **kwargs)

        # Act / Assert
        with mock.patch.object(packager.os, "replace", side_effect=fail_checksum_replace):
            with self.assertRaisesRegex(OSError, "checksum finalization"):
                packager.package_plugin(ROOT, output)
        self.assertFalse(archive.exists())
        self.assertFalse(checksum.exists())
        self.assertEqual([], list(output.glob(".*.tmp")))

    def test_release_packager_rejects_substituted_temporary_during_replace(self):
        # Arrange
        import tools.codex_studio.package_plugin as packager

        for target in ("archive", "checksum"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "dist"
                output.mkdir()
                archive = output / "codex-game-studios-1.0.0.zip"
                checksum = output / f"{archive.name}.sha256"
                attacked_final = archive if target == "archive" else checksum
                unrelated = output / "release-notes.txt"
                unrelated.write_bytes(b"preserve me")
                real_replace = os.replace
                attacked = False
                attack_attempted = False
                attack_blocked = False
                blocked_error = None
                used_directory_handle = False

                def install_attacker_after_identity_check(
                    source, destination, *args, **kwargs
                ):
                    nonlocal attack_attempted, attacked, attack_blocked
                    nonlocal blocked_error, used_directory_handle
                    source_path = Path(source)
                    destination_path = Path(destination)
                    if not source_path.is_absolute():
                        source_path = output / source_path
                        used_directory_handle = True
                    if not destination_path.is_absolute():
                        destination_path = output / destination_path
                        used_directory_handle = True
                    same_output = (
                        destination_path.name == attacked_final.name
                        and os.path.samefile(destination_path.parent, output)
                    )
                    if same_output and not attacked:
                        approved = output / "approved-temporary-stash"
                        attack_attempted = True
                        try:
                            real_replace(source_path, approved)
                        except PermissionError as error:
                            attack_blocked = True
                            blocked_error = error
                            raise
                        source_path.write_bytes(
                            f"attacker {target}\n".encode("ascii")
                        )
                        real_replace(source_path, destination_path)
                        approved.unlink()
                        attacked = True
                        return None
                    return real_replace(source, destination, *args, **kwargs)

                # Act / Assert
                with mock.patch.object(
                    packager.os,
                    "replace",
                    side_effect=install_attacker_after_identity_check,
                ):
                    with self.assertRaises(
                        (ValueError, PermissionError)
                    ) as caught:
                        packager.package_plugin(ROOT, output)
                self.assertTrue(attack_attempted)
                if isinstance(caught.exception, PermissionError):
                    self.assertEqual("nt", os.name)
                    self.assertTrue(attack_blocked)
                    self.assertIs(caught.exception, blocked_error)
                    self.assertFalse(attacked)
                    self.assertFalse(
                        (output / "approved-temporary-stash").exists()
                    )
                else:
                    self.assertRegex(
                        str(caught.exception), "final|identity|bytes|changed"
                    )
                    self.assertTrue(attacked)
                    self.assertFalse(attack_blocked)
                    if os.name != "nt":
                        self.assertTrue(used_directory_handle)
                self.assertFalse(archive.exists())
                self.assertFalse(checksum.exists())
                self.assertEqual([], list(output.glob(".*.tmp")))
                self.assertEqual(b"preserve me", unrelated.read_bytes())

    def test_release_finalization_mocked_windows_branch_verifies_installed_bytes(self):
        # Arrange
        import tools.codex_studio.package_plugin as packager

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            temporary = output / ".codex-game-studios-1.0.0.zip.deadbeef.tmp"
            final = output / "codex-game-studios-1.0.0.zip"
            approved_bytes = b"approved archive"
            temporary.write_bytes(approved_bytes)
            written = temporary.lstat()
            identity = (written.st_dev, written.st_ino)
            mode = written.st_mode & 0o777
            digest = hashlib.sha256(approved_bytes).hexdigest()
            real_replace = os.replace
            verified = False

            class MockPinnedWindowsRoot:
                _descriptor = None

            class MockWindowsFilesystem:
                pinned = MockPinnedWindowsRoot()

                def read_file_verified(
                    self, relative, *, expected_digest, expected_mode
                ):
                    nonlocal verified
                    verified = True
                    return (output / relative).read_bytes()

                def verify_boundary(self):
                    return None

            def install_attacker(source, destination):
                approved = output / "approved-stash"
                real_replace(source, approved)
                Path(source).write_bytes(b"attacker archive")
                real_replace(source, destination)
                approved.unlink()

            # Act / Assert
            with mock.patch.object(
                packager.os, "replace", side_effect=install_attacker
            ):
                with self.assertRaisesRegex(ValueError, "identity|bytes"):
                    packager._replace_temporary(
                        temporary,
                        final,
                        identity,
                        mode,
                        digest,
                        MockWindowsFilesystem(),
                    )
            self.assertTrue(verified)

    def test_release_packager_reverifies_both_outputs_before_returning_result(self):
        # Arrange
        import tools.codex_studio.package_plugin as packager

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dist"
            unrelated = output / "release-notes.txt"
            output.mkdir()
            unrelated.write_bytes(b"preserve me")
            archive = output / "codex-game-studios-1.0.0.zip"
            checksum = output / f"{archive.name}.sha256"
            real_replace_temporary = packager._replace_temporary
            attacked = False

            def replace_then_modify_archive(*args, **kwargs):
                nonlocal attacked
                contents = real_replace_temporary(*args, **kwargs)
                final = Path(args[1])
                if final.name == checksum.name and not attacked:
                    archive.write_bytes(
                        b"post-verification attacker archive"
                    )
                    attacked = True
                return contents

            # Act / Assert
            with mock.patch.object(
                packager,
                "_replace_temporary",
                side_effect=replace_then_modify_archive,
            ):
                with self.assertRaisesRegex(
                    ValueError, "final|identity|bytes|metadata"
                ):
                    packager.package_plugin(ROOT, output)
            self.assertTrue(attacked)
            self.assertFalse(archive.exists())
            self.assertFalse(checksum.exists())
            self.assertEqual(b"preserve me", unrelated.read_bytes())

    def assert_output_directory_substitution_rejected(self, target):
        import tools.codex_studio.package_plugin as packager

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            output = parent / "dist"
            retained = parent / "retained-dist"
            output.mkdir()
            retained_note = output / "release-notes.txt"
            retained_note.write_bytes(b"retained unrelated")
            substitute_note = output / "substitute-notes.txt"
            real_new_temporary = packager._new_temporary
            substituted = False
            substitution_blocked = False
            blocked_error = None
            escaped_creation = False

            def substitute_then_create(destination, label, *args, **kwargs):
                nonlocal blocked_error, escaped_creation
                nonlocal substituted, substitution_blocked
                is_target = (
                    target == "archive" and label.endswith(".zip")
                ) or (
                    target == "checksum" and label.endswith(".zip.sha256")
                )
                if is_target and not substituted:
                    try:
                        output.rename(retained)
                    except PermissionError as error:
                        substitution_blocked = True
                        blocked_error = error
                        raise
                    output.mkdir()
                    substitute_note.write_bytes(b"substitute unrelated")
                    substituted = True
                try:
                    return real_new_temporary(
                        destination, label, *args, **kwargs
                    )
                finally:
                    if substituted:
                        escaped_creation = escaped_creation or any(
                            packager._is_package_output_name(path.name)
                            for path in output.iterdir()
                        )

            # Act / Assert
            with mock.patch.object(
                packager,
                "_new_temporary",
                side_effect=substitute_then_create,
            ):
                with self.assertRaises((OSError, ValueError)) as caught:
                    packager.package_plugin(ROOT, output)
            if isinstance(caught.exception, PermissionError):
                self.assertEqual("nt", os.name)
                self.assertTrue(substitution_blocked)
                self.assertIs(caught.exception, blocked_error)
                self.assertFalse(substituted)
                self.assertFalse(retained.exists())
                self.assertEqual(b"retained unrelated", retained_note.read_bytes())
                self.assertEqual(
                    [],
                    [
                        path.name
                        for path in output.iterdir()
                        if packager._is_package_output_name(path.name)
                    ],
                )
                return
            self.assertTrue(
                substituted, (repr(caught.exception), substitution_blocked)
            )
            self.assertFalse(escaped_creation)
            for directory_path in (output, retained):
                self.assertEqual(
                    [],
                    [
                        path.name
                        for path in directory_path.iterdir()
                        if packager._is_package_output_name(path.name)
                    ],
                )
            self.assertEqual(
                b"retained unrelated",
                (retained / retained_note.name).read_bytes(),
            )
            self.assertEqual(b"substitute unrelated", substitute_note.read_bytes())

    def test_release_archive_temp_uses_retained_output_directory_authority(self):
        # Arrange / Act / Assert
        self.assert_output_directory_substitution_rejected("archive")

    def test_release_checksum_temp_uses_retained_output_directory_authority(self):
        # Arrange / Act / Assert
        self.assert_output_directory_substitution_rejected("checksum")

    def test_release_temp_mocked_windows_branch_checks_directory_continuity(self):
        # Arrange
        import tools.codex_studio.package_plugin as packager

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            unrelated = output / "release-notes.txt"
            unrelated.write_bytes(b"preserve me")
            real_open = os.open
            open_call = None

            class MockWindowsPinnedRoot:
                _descriptor = None

            class MockWindowsFilesystem:
                pinned = MockWindowsPinnedRoot()
                checks = 0

                def verify_boundary(self):
                    self.checks += 1
                    if self.checks == 2:
                        raise ValueError("mocked output directory substitution")

            filesystem = MockWindowsFilesystem()

            def record_open(path, flags, mode=0o777, *args, **kwargs):
                nonlocal open_call
                open_call = (Path(path), flags, mode, kwargs)
                return real_open(path, flags, mode, *args, **kwargs)

            # Act / Assert
            with mock.patch.object(packager.os, "open", side_effect=record_open):
                with self.assertRaisesRegex(ValueError, "directory substitution"):
                    packager._new_temporary(
                        output,
                        "codex-game-studios-1.0.0.zip",
                        filesystem,
                    )
            self.assertEqual(2, filesystem.checks)
            self.assertIsNotNone(open_call)
            path, flags, mode, kwargs = open_call
            self.assertEqual(output, path.parent)
            self.assertTrue(flags & os.O_CREAT)
            self.assertTrue(flags & os.O_EXCL)
            self.assertEqual(0o600, mode)
            self.assertEqual({}, kwargs)
            self.assertEqual(
                [],
                [
                    path.name
                    for path in output.iterdir()
                    if packager._is_package_output_name(path.name)
                ],
            )
            self.assertEqual(b"preserve me", unrelated.read_bytes())

    def assert_retained_failure_cleanup_does_not_touch_substitute(self, target):
        import tools.codex_studio.package_plugin as packager

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            output = parent / "dist"
            retained = parent / "retained-dist"
            output.mkdir()
            retained_note = output / "release-notes.txt"
            retained_note.write_bytes(b"retained unrelated")
            real_new_temporary = packager._new_temporary
            real_fdopen = os.fdopen
            failing_descriptor = None
            victims = {}
            substituted = False
            substitution_blocked = False
            blocked_error = None
            blocked_descriptor_closed = False

            def create_then_substitute(destination, label, *args, **kwargs):
                nonlocal blocked_descriptor_closed, blocked_error
                nonlocal failing_descriptor, substituted, substitution_blocked
                nonlocal victims
                descriptor, temporary = real_new_temporary(
                    destination, label, *args, **kwargs
                )
                is_target = (
                    target == "archive" and label.endswith(".zip")
                ) or (
                    target == "checksum" and label.endswith(".zip.sha256")
                )
                if is_target and not substituted:
                    try:
                        output.rename(retained)
                    except PermissionError as error:
                        substitution_blocked = True
                        blocked_error = error
                        os.close(descriptor)
                        blocked_descriptor_closed = True
                        raise
                    output.mkdir()
                    victims = {
                        output / temporary.name: b"attacker temp victim",
                        output / "codex-game-studios-1.0.0.zip": b"attacker zip victim",
                        output
                        / "codex-game-studios-1.0.0.zip.sha256": b"attacker checksum victim",
                    }
                    for path, contents in victims.items():
                        path.write_bytes(contents)
                    (output / "substitute-notes.txt").write_bytes(
                        b"substitute unrelated"
                    )
                    failing_descriptor = descriptor
                    substituted = True
                return descriptor, temporary

            class FailingWriter:
                def __init__(self, stream):
                    self.stream = stream

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, traceback):
                    self.stream.close()
                    return False

                def write(self, contents):
                    raise OSError("injected checksum write failure")

            def fail_selected_fdopen(descriptor, *args, **kwargs):
                stream = real_fdopen(descriptor, *args, **kwargs)
                if descriptor == failing_descriptor:
                    return FailingWriter(stream)
                return stream

            # Act / Assert
            with mock.patch.object(
                packager,
                "_new_temporary",
                side_effect=create_then_substitute,
            ):
                if target == "archive":
                    with mock.patch.object(
                        packager,
                        "_read_plugin_file",
                        side_effect=OSError("injected archive read failure"),
                    ):
                        with self.assertRaises(OSError) as caught:
                            packager.package_plugin(ROOT, output)
                else:
                    with mock.patch.object(
                        packager.os,
                        "fdopen",
                        side_effect=fail_selected_fdopen,
                    ):
                        with self.assertRaises(OSError) as caught:
                            packager.package_plugin(ROOT, output)
            if substitution_blocked:
                self.assertEqual("nt", os.name)
                self.assertIs(caught.exception, blocked_error)
                self.assertTrue(blocked_descriptor_closed)
                self.assertFalse(substituted)
                self.assertFalse(retained.exists())
                self.assertEqual(
                    b"retained unrelated", retained_note.read_bytes()
                )
                self.assertEqual(
                    [],
                    [
                        path.name
                        for path in output.iterdir()
                        if packager._is_package_output_name(path.name)
                    ],
                )
                return
            self.assertTrue(substituted)
            self.assertEqual(
                [],
                [
                    path.name
                    for path in retained.iterdir()
                    if packager._is_package_output_name(path.name)
                ],
            )
            self.assertEqual(
                b"retained unrelated",
                (retained / retained_note.name).read_bytes(),
            )
            for path, contents in victims.items():
                self.assertTrue(path.exists(), path)
                self.assertEqual(contents, path.read_bytes())
            self.assertEqual(
                b"substitute unrelated",
                (output / "substitute-notes.txt").read_bytes(),
            )

    def test_release_archive_failure_cleans_only_retained_authority(self):
        # Arrange / Act / Assert
        self.assert_retained_failure_cleanup_does_not_touch_substitute("archive")

    def test_release_checksum_failure_cleans_only_retained_authority(self):
        # Arrange / Act / Assert
        self.assert_retained_failure_cleanup_does_not_touch_substitute("checksum")

    def test_release_packager_cli_prints_archive_and_checksum_paths(self):
        # Arrange
        output = self.output

        # Act
        completed = subprocess.run(
            [
                sys.executable,
                "tools/codex_studio/package_plugin.py",
                "--root",
                ".",
                "--output",
                str(output),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

        # Assert
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(
            [
                str(output.resolve() / "codex-game-studios-1.0.0.zip"),
                str(output.resolve() / "codex-game-studios-1.0.0.zip.sha256"),
            ],
            completed.stdout.splitlines(),
        )

    def test_release_workflow_gates_artifacts_on_all_native_and_studio_jobs(self):
        # Arrange / Act
        workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))

        # Assert
        self.assert_release_workflow_contract(workflow)

    def test_release_workflow_contract_rejects_nonsemantic_or_misplaced_tokens(self):
        # Arrange
        workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        misplaced = json.loads(json.dumps(workflow))
        command = misplaced["jobs"]["native-plugin"]["steps"].pop()["run"]
        misplaced["jobs"]["studio"]["steps"].append({"run": command})
        malformed = json.loads(json.dumps(workflow))
        del malformed["jobs"]["release"]

        # Act / Assert
        with self.assertRaises(json.JSONDecodeError):
            json.loads("# ubuntu-latest and actions/upload-artifact@v4 only")
        with self.assertRaises(AssertionError):
            self.assert_release_workflow_contract(misplaced)
        with self.assertRaises(AssertionError):
            self.assert_release_workflow_contract(malformed)


if __name__ == "__main__":
    unittest.main()
