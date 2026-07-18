"""Shared semantic assertions for public plugin documentation contracts."""

from __future__ import annotations

import re
import unittest


LEGACY_LIFECYCLE = re.compile(
    r"\b(?:manag(?:e[sd]?|ing|ers?)|install(?:s|ed|ing)?|"
    r"updat(?:e[sd]?|ing)|verif(?:y|ies|ied|ying)|repair(?:s|ed|ing)?|"
    r"remov(?:e[sd]?|ing)|migrat(?:e[sd]?|ing)|"
    r"uninstall(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)


def assert_plugin_native_descriptions(
    testcase: unittest.TestCase, data: dict
) -> None:
    """Assert every public description field presents the plugin-native product."""

    descriptions = {
        "description": data["description"],
        "shortDescription": data["interface"]["shortDescription"],
        "longDescription": data["interface"]["longDescription"],
    }
    metadata = " ".join(descriptions.values())
    testcase.assertIn("73", metadata)
    testcase.assertIn("bundled skills", metadata)
    testcase.assertIn("$codex-game-studios:start", metadata)
    testcase.assertIn("bounded", metadata)
    testcase.assertIn("project", metadata)
    for field, value in descriptions.items():
        testcase.assertNotRegex(
            value,
            LEGACY_LIFECYCLE,
            msg=f"{field} must not advertise the legacy lifecycle as fresh",
        )
