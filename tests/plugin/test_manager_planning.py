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
    snapshot_tree,
    write_installed_fixture,
)
from models import canonical_json  # noqa: E402
from studio_manager import (  # noqa: E402
    ManagerError,
    load_installation_state,
    plan_operation,
    state_with_checksum,
    write_state_document,
)


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
        self.assertEqual(0, completed.returncode, completed.stderr)
        document = json.loads(completed.stdout)
        self.assertEqual("install", document["operation"])
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
        self.assertEqual(0, outputs[0][0])
        self.assertEqual(outputs[0], outputs[1])
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
        self.assertIn(
            "CUSTOMIZED_MANAGED_FILE", {conflict.code for conflict in plan.conflicts}
        )

    def test_plan_digest_changes_when_target_changes(self):
        # Arrange
        first = plan_operation("install", self.repo, PLUGIN)
        (self.repo / "AGENTS.md").write_text("changed\n", encoding="utf-8")

        # Act
        second = plan_operation("install", self.repo, PLUGIN)

        # Assert
        self.assertNotEqual(first.digest, second.digest)

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
        self.assertEqual(2, completed.returncode)
        self.assertIn("UNSAFE_PATH", completed.stderr)
        self.assertEqual(before, snapshot_tree(self.repo))

    def test_plan_is_deterministic_and_binds_ordered_actions(self):
        # Arrange / Act
        first = plan_operation("install", self.repo, PLUGIN)
        second = plan_operation("install", self.repo, PLUGIN)

        # Assert
        self.assertEqual(first, second)
        self.assertRegex(first.digest, r"^[0-9a-f]{64}$")

    def test_uninstall_orders_child_removals_before_parent_directories(self):
        # Arrange
        write_installed_fixture(self.repo, PLUGIN)

        # Act
        plan = plan_operation("uninstall", self.repo, PLUGIN)

        # Assert
        removals = [action.path for action in plan.actions if action.kind == "remove"]
        self.assertLess(
            removals.index(".agents/skills/start/SKILL.md"),
            removals.index(".agents/skills/start"),
        )

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
