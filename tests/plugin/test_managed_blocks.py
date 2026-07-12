"""Contract tests for conservative shared-file merging."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"
FIXTURES = Path(__file__).parent / "fixtures/shared-files"
sys.path.insert(0, str(PLUGIN / "scripts"))

from managed_blocks import (  # noqa: E402
    MergeConflict,
    merge_block,
    merge_owned_toml,
    remove_block,
)


class ManagedBlockTests(unittest.TestCase):
    """Verify exact, hash-owned managed blocks."""

    def test_managed_block_agents_merge_preserves_surrounding_bytes(self):
        # Arrange
        existing = (FIXTURES / "agents-existing.md").read_bytes()

        # Act
        result = merge_block(existing, "codex-game-studios", b"studio rules\n")

        # Assert
        self.assertEqual(
            existing
            + b"<!-- codex-game-studios:start -->\n"
            + b"studio rules\n"
            + b"<!-- codex-game-studios:end -->\n",
            result.content,
        )
        self.assertTrue(result.changed)
        self.assertEqual(
            hashlib.sha256(
                b"<!-- codex-game-studios:start -->\n"
                b"studio rules\n"
                b"<!-- codex-game-studios:end -->\n"
            ).hexdigest(),
            result.block_hash,
        )

    def test_managed_block_crlf_update_preserves_surrounding_bytes_and_newlines(self):
        # Arrange
        existing = (
            b"before\r\n"
            b"<!-- codex-game-studios:start -->\r\n"
            b"old\r\n"
            b"<!-- codex-game-studios:end -->\r\n"
            b"after\r\n"
        )

        # Act
        result = merge_block(existing, "codex-game-studios", b"new\n\n")

        # Assert
        self.assertEqual(
            b"before\r\n"
            b"<!-- codex-game-studios:start -->\r\n"
            b"new\r\n"
            b"<!-- codex-game-studios:end -->\r\n"
            b"after\r\n",
            result.content,
        )
        self.assertNotIn(b"\n\n", result.content)

    def test_managed_block_same_content_is_idempotent(self):
        # Arrange
        first = merge_block(b"project rules\n", "codex-game-studios", b"studio rules\n")

        # Act
        second = merge_block(first.content, "codex-game-studios", b"studio rules\n")

        # Assert
        self.assertEqual(first.content, second.content)
        self.assertEqual(first.block_hash, second.block_hash)
        self.assertFalse(second.changed)

    def test_managed_block_gitignore_fixture_preserves_project_rules(self):
        # Arrange
        existing = (FIXTURES / "gitignore-existing").read_bytes()

        # Act
        result = merge_block(existing, "codex-game-studios", b".codex/cache/\n")

        # Assert
        self.assertTrue(result.content.startswith(existing))
        self.assertIn(b"build/\n", result.content)
        self.assertTrue(
            result.content.endswith(
                b".codex/cache/\n<!-- codex-game-studios:end -->\n"
            )
        )

    def test_managed_block_plain_marker_mentions_are_not_comment_candidates(self):
        # Arrange
        existing = b"Discuss codex-game-studios:start in project prose.\n"

        # Act
        result = merge_block(existing, "codex-game-studios", b"rules\n")

        # Assert
        self.assertTrue(result.content.startswith(existing))

    def test_managed_block_nested_duplicate_unbalanced_and_nonstandalone_markers_conflict(self):
        # Arrange
        malformed_values = (
            b"<!-- codex-game-studios:start -->\n<!-- codex-game-studios:start -->\n",
            b"<!-- codex-game-studios:start -->\n",
            b"<!-- codex-game-studios:end -->\n",
            b"prefix <!-- codex-game-studios:start -->\n",
            b"<!-- codex-game-studios:end --> suffix\n",
            b"<!--  codex-game-studios:start -->\n",
            b"<!-- codex-game-studios:end  -->\n",
            b"<!-- codex-game-studios :start -->\n",
            b"<!-- Codex-Game-Studios:start -->\n",
            b"<! -- codex-game-studios:start -- >\n",
            b"<-- codex-game-studios:end -->\n",
            b"<!-- codex-game-studios:start --\n",
            b"<!-- codex-game-studios:start >\n",
            b"<!-- codex-game-studios:end --\n",
            b"<!-- codex-game-studios:end >\n",
        )

        # Act / Assert
        for malformed in malformed_values:
            with self.subTest(malformed=malformed):
                with self.assertRaisesRegex(MergeConflict, "exactly one managed block"):
                    merge_block(malformed, "codex-game-studios", b"rules\n")

    def test_managed_block_invalid_utf8_conflicts(self):
        # Arrange
        invalid_values = ((b"project \xff\n", b"rules\n"), (b"project\n", b"rules \xff\n"))

        # Act / Assert
        for existing, desired in invalid_values:
            with self.subTest(existing=existing, desired=desired):
                with self.assertRaisesRegex(MergeConflict, "UTF-8"):
                    merge_block(existing, "codex-game-studios", desired)

    def test_managed_block_remove_requires_matching_recorded_hash(self):
        # Arrange
        merged = merge_block(b"before\nafter\n", "codex-game-studios", b"rules\n")

        # Act
        removed = remove_block(
            merged.content, "codex-game-studios", merged.block_hash
        )

        # Assert
        self.assertEqual(b"before\nafter\n", removed.content)
        self.assertEqual("", removed.block_hash)
        self.assertTrue(removed.changed)

    def test_managed_block_remove_rejects_customized_or_missing_blocks(self):
        # Arrange
        merged = merge_block(b"project\n", "codex-game-studios", b"rules\n")
        customized = merged.content.replace(b"rules", b"customized")

        # Act / Assert
        with self.assertRaisesRegex(MergeConflict, "recorded block hash"):
            remove_block(customized, "codex-game-studios", merged.block_hash)
        with self.assertRaisesRegex(MergeConflict, "exactly one managed block"):
            remove_block(b"project\n", "codex-game-studios", merged.block_hash)

    def test_managed_block_remove_restores_no_final_newline_exactly(self):
        # Arrange
        existing_values = (b"first\nlast", b"first\r\nlast")

        # Act / Assert
        for existing in existing_values:
            with self.subTest(existing=existing):
                merged = merge_block(
                    existing, "codex-game-studios", b"managed rules\n"
                )
                removed = remove_block(
                    merged.content, "codex-game-studios", merged.block_hash
                )
                self.assertEqual(existing, removed.content)

                customized = merged.content.replace(b"managed", b"customized")
                with self.assertRaisesRegex(MergeConflict, "recorded block hash"):
                    remove_block(
                        customized, "codex-game-studios", merged.block_hash
                    )

    def test_managed_block_repeated_merge_preserves_recorded_separator_ownership(self):
        # Arrange
        existing_values = (b"first\nlast", b"first\r\nlast")

        # Act / Assert
        for existing in existing_values:
            with self.subTest(existing=existing):
                first = merge_block(
                    existing, "codex-game-studios", b"managed rules\n"
                )
                second = merge_block(
                    first.content,
                    "codex-game-studios",
                    b"managed rules\n",
                    recorded_hash=first.block_hash,
                )

                self.assertEqual(first.content, second.content)
                self.assertFalse(second.changed)
                self.assertEqual(first.block_hash, second.block_hash)
                removed = remove_block(
                    second.content, "codex-game-studios", second.block_hash
                )
                self.assertEqual(existing, removed.content)

    def test_managed_block_repeated_merge_rejects_nonmatching_recorded_hash(self):
        # Arrange
        merged = merge_block(
            b"project without newline", "codex-game-studios", b"rules\n"
        )

        # Act / Assert
        with self.assertRaisesRegex(MergeConflict, "recorded block hash"):
            merge_block(
                merged.content,
                "codex-game-studios",
                b"rules\n",
                recorded_hash="0" * 64,
            )


class OwnedTomlTests(unittest.TestCase):
    """Verify byte-preserving edits of the three approved TOML keys."""

    DESIRED = {
        "agents.max_depth": 4,
        "agents.max_threads": 16,
        "features.hooks": True,
    }

    def test_owned_toml_merge_preserves_unowned_keys(self):
        # Arrange
        existing = (FIXTURES / "config-existing.toml").read_bytes()

        # Act
        result = merge_owned_toml(existing, self.DESIRED, {})

        # Assert
        self.assertEqual(
            b'title = "project"\n'
            b"# project setting\n"
            b"[agents]\n"
            b"# owned and project values share this table\n"
            b"max_depth   = 4 # preserve spacing\n"
            b"project_agent = \"keeper\"\n"
            b"\n"
            b"max_threads = 16\n"
            b"[project]\n"
            b"between = \"untouched\"\n"
            b"\n"
            b"[features]\n"
            b"web_search = true # preserve comment\n"
            b"\n"
            b"hooks = true\n"
            b"[after]\n"
            b"value = \"still untouched\"\n",
            result.content,
        )
        self.assertEqual(True, result.owned_values["features.hooks"])
        self.assertEqual(self.DESIRED, result.owned_values)
        self.assertTrue(result.changed)

    def test_owned_toml_multiline_marker_content_fails_closed_without_mutation(self):
        # Arrange
        existing = (
            b'note = """marker-like text\n'
            b"[agents]\n"
            b"max_depth = 2\n"
            b"<!-- codex-game-studios :start -->\n"
            b'"""\n'
            b"agents = { max_depth = 2 }\n"
            b"features.hooks = true\n"
            b"literal = '''quoted ' and # content\n"
            b"[features]\n"
            b"hooks = false\n"
            b"'''\n"
        )
        original = bytes(existing)

        # Act / Assert
        with self.assertRaisesRegex(MergeConflict, "unsupported TOML layout"):
            merge_owned_toml(
                existing,
                {"agents.max_depth": 4, "features.hooks": True},
                {"agents.max_depth": 2, "features.hooks": True},
            )
        self.assertEqual(original, existing)

    def test_owned_toml_escaped_quotes_comments_and_marker_strings_are_preserved(self):
        # Arrange
        existing = (
            b'note = "escaped \\\" quote and <!-- codex-game-studios :start -->"\n'
            b"# [agents] max_depth = 99\n"
            b"agents.max_depth = 4\n"
            b"features.hooks = true\n"
        )

        # Act
        result = merge_owned_toml(
            existing,
            {"agents.max_depth": 4, "features.hooks": True},
            {},
        )

        # Assert
        self.assertEqual(existing, result.content)
        self.assertFalse(result.changed)

    def test_owned_toml_matching_values_are_adopted_idempotently(self):
        # Arrange
        existing = (
            b"[agents]\nmax_depth = 4\nmax_threads = 16\n\n"
            b"[features]\nhooks = true\nweb_search = true\n"
        )

        # Act
        result = merge_owned_toml(existing, self.DESIRED, {})

        # Assert
        self.assertEqual(existing, result.content)
        self.assertEqual(self.DESIRED, result.owned_values)
        self.assertFalse(result.changed)

    def test_owned_toml_recorded_values_can_be_updated_without_reformatting(self):
        # Arrange
        existing = (
            b"title = \"game\"\r\n"
            b"[agents]\r\n"
            b"max_depth   = 2 # keep comment\r\n"
            b"max_threads = 8\r\n"
            b"[features]\r\n"
            b"hooks = false\r\n"
        )
        recorded = {
            "agents.max_depth": 2,
            "agents.max_threads": 8,
            "features.hooks": False,
        }

        # Act
        result = merge_owned_toml(existing, self.DESIRED, recorded)

        # Assert
        self.assertEqual(
            b"title = \"game\"\r\n"
            b"[agents]\r\n"
            b"max_depth   = 4 # keep comment\r\n"
            b"max_threads = 16\r\n"
            b"[features]\r\n"
            b"hooks = true\r\n",
            result.content,
        )
        self.assertNotIn(b"\n", result.content.replace(b"\r\n", b""))

    def test_owned_toml_unrecorded_different_value_is_conflict(self):
        # Arrange
        existing = b"[agents]\nmax_depth = 2\n"

        # Act / Assert
        with self.assertRaisesRegex(MergeConflict, "conflicting owned key"):
            merge_owned_toml(existing, {"agents.max_depth": 4}, {})

    def test_owned_toml_customized_recorded_value_is_conflict(self):
        # Arrange
        existing = b"[features]\nhooks = false\n"

        # Act / Assert
        with self.assertRaisesRegex(MergeConflict, "conflicting owned key"):
            merge_owned_toml(
                existing, {"features.hooks": True}, {"features.hooks": True}
            )

    def test_owned_toml_unsupported_keys_types_and_layouts_fail_closed(self):
        # Arrange
        cases = (
            (b"", {"project.name": "game"}, {}),
            (b"", {"agents.max_depth": True}, {}),
            (b"agents = { max_depth = 4 }\n", {"agents.max_depth": 4}, {}),
            (b"[agents]\n\"max_depth\" = 4\n", {"agents.max_depth": 4}, {}),
            (b"[agents]\nmax_depth = 4\nmax_depth = 4\n", {"agents.max_depth": 4}, {}),
        )

        # Act / Assert
        for existing, desired, recorded in cases:
            with self.subTest(existing=existing, desired=desired):
                with self.assertRaisesRegex(MergeConflict, "unsupported TOML layout"):
                    merge_owned_toml(existing, desired, recorded)

    def test_owned_toml_invalid_utf8_and_syntax_fail_closed(self):
        # Arrange
        invalid_values = (b"title = \"\xff\"\n", b"[agents\nmax_depth = 4\n")

        # Act / Assert
        for existing in invalid_values:
            with self.subTest(existing=existing):
                with self.assertRaisesRegex(MergeConflict, "unsupported TOML layout"):
                    merge_owned_toml(existing, self.DESIRED, {})


if __name__ == "__main__":
    unittest.main()
