"""End-to-end lifecycle integration tests for the embedded studio."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.plugin.helpers import (
    PLUGIN,
    approved_install,
    init_git_repo,
    run_manager,
    snapshot_tree,
    write_installed_fixture,
)


class LifecycleIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        )
        self.repo = Path(self.temporary.name)
        init_git_repo(self.repo)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _apply(self, operation: str):
        planned = run_manager(operation, self.repo)
        self.assertEqual(2, planned.returncode, planned.stderr)
        document = json.loads(planned.stdout)
        return run_manager(
            operation, self.repo, document["digest"],
            approval_context=document["approval_context"],
        )

    def test_all_five_operations_dispatch_with_two_phase_mutations(self):
        installed = approved_install(self.repo)
        self.assertEqual(0, installed.applied.returncode, installed.applied.stderr)

        before = snapshot_tree(self.repo)
        verified = run_manager("verify", self.repo)
        self.assertEqual(0, verified.returncode, verified.stderr)
        self.assertEqual(before, snapshot_tree(self.repo))

        for operation in ("update", "repair"):
            applied = self._apply(operation)
            self.assertEqual(0, applied.returncode, applied.stderr)

        uninstalled = self._apply("uninstall")
        self.assertEqual(0, uninstalled.returncode, uninstalled.stderr)
        self.assertFalse((self.repo / ".codex/codex-game-studios/installation.json").exists())

    def test_install_adopts_identical_payload_file_and_rejects_unowned_collision(self):
        identical = self.repo / ".codex/studio.toml"
        identical.parent.mkdir(parents=True)
        identical.write_bytes(
            (Path(__file__).resolve().parents[2] / "plugins/codex-game-studios/assets/studio/.codex/studio.toml").read_bytes()
        )
        planned = run_manager("install", self.repo)
        actions = json.loads(planned.stdout)["actions"]
        self.assertTrue(any(item["kind"] == "adopt" and item["path"] == ".codex/studio.toml" for item in actions))

        collision = self.repo / ".codex/hooks.json"
        collision.write_text("unowned", encoding="utf-8")
        before = snapshot_tree(self.repo)
        blocked = run_manager("install", self.repo)
        document = json.loads(blocked.stdout)
        self.assertEqual(1, blocked.returncode)
        self.assertEqual("UNMANAGED_COLLISION", document["status"])
        self.assertEqual(before, snapshot_tree(self.repo))

    def test_uninstall_preserves_customized_owned_file_and_legal_notices(self):
        installed = approved_install(self.repo)
        self.assertEqual(0, installed.applied.returncode, installed.applied.stderr)
        customized = self.repo / ".codex/studio.toml"
        customized.write_bytes(customized.read_bytes() + b"\n# project customization\n")
        agents = self.repo / "AGENTS.md"
        project_agents = b"# Project-owned instructions\n\n"
        agents.write_bytes(project_agents + agents.read_bytes())
        legal_license = self.repo / ".codex/codex-game-studios/legal/LICENSE"
        legal_attribution = self.repo / ".codex/codex-game-studios/legal/ATTRIBUTION.md"
        expected_license = legal_license.read_bytes()
        expected_attribution = legal_attribution.read_bytes() + b"\nproject legal note\n"
        legal_attribution.write_bytes(expected_attribution)

        planned = run_manager("uninstall", self.repo)
        document = json.loads(planned.stdout)

        self.assertEqual(2, planned.returncode)
        self.assertEqual("awaiting-approval", document["status"])
        applied = run_manager(
            "uninstall", self.repo, document["digest"],
            approval_context=document["approval_context"],
        )
        self.assertEqual(0, applied.returncode, applied.stderr)
        self.assertTrue(customized.exists())
        self.assertEqual(project_agents, agents.read_bytes())
        self.assertEqual(expected_license, legal_license.read_bytes())
        self.assertEqual(expected_attribution, legal_attribution.read_bytes())
        self.assertFalse((self.repo / ".agents/skills/start/SKILL.md").exists())
        self.assertFalse((self.repo / ".codex/codex-game-studios/installation.json").exists())
        result = json.loads(applied.stdout)
        self.assertEqual("committed", result["recovery"])

    def test_uninstall_validation_failure_rolls_back_and_retains_state(self):
        # Arrange
        installed = approved_install(self.repo)
        self.assertEqual(0, installed.applied.returncode, installed.applied.stderr)
        planned = json.loads(run_manager("uninstall", self.repo).stdout)
        state = self.repo / ".codex/codex-game-studios/installation.json"

        # Act
        import studio_manager
        from unittest import mock
        context = studio_manager.decode_approval_context(
            planned["approval_context"], "uninstall"
        )
        plan = studio_manager.plan_operation(
            "uninstall", self.repo,
            studio_manager.Path(studio_manager.__file__).parents[1], context,
        )
        with mock.patch("studio_manager._validate_uninstall_read_only", return_value=["bad"]):
            with self.assertRaises(studio_manager.ManagerError) as caught:
                studio_manager.apply_operation(
                    plan, self.repo, studio_manager.Path(studio_manager.__file__).parents[1],
                    approval_context=context,
                )

        # Assert
        self.assertEqual("VALIDATION_FAILED", caught.exception.code)
        self.assertTrue(caught.exception.wrote)
        self.assertTrue(state.is_file())

    def test_repeated_repair_stale_update_and_uninstall_public_lifecycle(self):
        # Arrange: a complete installed fixture avoids duplicating the expensive
        # fresh-install setup while exercising each public subprocess boundary.
        import dataclasses
        import studio_manager
        write_installed_fixture(self.repo, PLUGIN)
        repeated_install = run_manager("install", self.repo)
        self.assertEqual(1, repeated_install.returncode)
        self.assertEqual(
            "INVALID_INSTALLATION_STATE",
            json.loads(repeated_install.stdout)["status"],
        )

        missing = self.repo / ".agents/skills/start/SKILL.md"
        expected = (PLUGIN / "assets/studio/.agents/skills/start/SKILL.md").read_bytes()
        missing.unlink()

        # Act / Assert: actual missing owned content is restored.
        repaired = self._apply("repair")
        self.assertEqual(0, repaired.returncode, repaired.stderr)
        self.assertEqual(expected, missing.read_bytes())

        # Actual differing bytes are conservatively classified as customized,
        # not silently overwritten as "corruption."
        missing.write_bytes(b"corrupt or customized\n")
        blocked_repair = run_manager("repair", self.repo)
        self.assertEqual(1, blocked_repair.returncode)
        self.assertEqual(
            "CUSTOMIZED_MANAGED_FILE",
            json.loads(blocked_repair.stdout)["status"],
        )
        self.assertEqual(b"corrupt or customized\n", missing.read_bytes())
        missing.write_bytes(expected)

        # A historical/stale payload record is advanced by update and rewritten
        # only after installed validation succeeds.
        state_path = self.repo / ".codex/codex-game-studios/installation.json"
        state = studio_manager.load_installation_state(state_path)
        stale = studio_manager.state_with_checksum(
            dataclasses.replace(state, payload_digest="0" * 64, checksum="")
        )
        state_path.write_bytes(studio_manager.write_state_document(stale))
        updated = self._apply("update")
        self.assertEqual(0, updated.returncode, updated.stderr)
        current = studio_manager.load_installation_state(state_path)
        self.assertNotEqual("0" * 64, current.payload_digest)

        uninstalled = self._apply("uninstall")
        self.assertEqual(0, uninstalled.returncode, uninstalled.stderr)
        repeated_uninstall = run_manager("uninstall", self.repo)
        self.assertEqual(1, repeated_uninstall.returncode)
        self.assertEqual(
            "INVALID_INSTALLATION_STATE",
            json.loads(repeated_uninstall.stdout)["status"],
        )


if __name__ == "__main__":
    unittest.main()
