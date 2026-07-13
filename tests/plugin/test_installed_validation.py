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

    def test_installed_mode_accepts_game_owned_files_and_excluded_maintainer_material(self):
        # Arrange
        (self.repo / "src/game.py").write_text("print('game')\n", encoding="utf-8")

        # Act
        issues = validate_installed_repository(self.repo)

        # Assert
        self.assertEqual([], issues)
        self.assertFalse((self.repo / "README.md").exists())
        self.assertFalse((self.repo / "docs/superpowers").exists())

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
        original = os.read
        swapped = False

        def replace_root(descriptor, size):
            nonlocal swapped
            if not swapped:
                displaced = self.repo.with_name("displaced")
                self.repo.rename(displaced)
                shutil.copytree(displaced, self.repo)
                swapped = True
            return original(descriptor, size)

        # Act
        with mock.patch("os.read", side_effect=replace_root):
            issues = validate_installed_repository(self.repo)

        # Assert
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
