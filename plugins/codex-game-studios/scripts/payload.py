"""Deterministic generation and verification for the operational payload."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import stat
import tempfile
from typing import Iterable

from models import (
    PayloadEntry,
    PayloadError,
    PayloadManifest,
    canonical_json,
    normalize_relative_path,
)
from safe_fs import (
    copy_file_secure,
    hash_file_secure,
    inspect_secure,
    is_reparse_point,
    mode_matches,
    read_file_secure,
    set_directory_mode_secure,
    walk_tree_secure,
    write_file_secure,
)


SCHEMA_VERSION = 1
ENTRY_KEYS = {"path", "entry_type", "mode", "sha256", "ownership", "merge", "required"}
POLICY_KEYS = {
    "schema_version",
    "version",
    "dedicated_roots",
    "dedicated_files",
    "nested_instruction_files",
    "shared_files",
    "mapped_files",
    "denied_exact_paths",
    "denied_prefixes",
    "ignored_names",
    "ignored_suffixes",
    "approved_sources",
    "license",
}
APPROVED_SOURCE_KEYS = {
    "source", "target", "category", "provenance", "license",
    "ownership", "merge", "required",
}
SOURCE_CATEGORIES = {"dedicated-root", "standalone", "nested-instruction", "shared", "legal"}
PROVENANCE_VALUES = {"codex-native", "upstream-adapted", "upstream-legal"}
MERGE_VALUES = {"managed-block", "toml-keys"}
_VALIDATOR_PATH = "tools/codex_studio/validate.py"
_ATTESTATION_PATTERN = re.compile(
    rb"# payload-inventory-attestation:start\n"
    rb"_INSTALLED_INVENTORY_ENTRY_COUNT = [0-9]+\n"
    rb'_INSTALLED_INVENTORY_SHA256 = "[0-9a-f]{64}"\n'
    rb"# payload-inventory-attestation:end\n"
)


def _entry_dict(entry: PayloadEntry) -> dict[str, object]:
    return {
        "path": entry.path,
        "entry_type": entry.entry_type,
        "mode": entry.mode,
        "sha256": entry.sha256,
        "ownership": entry.ownership,
        "merge": entry.merge,
        "required": entry.required,
    }


def _manifest_body(
    schema_version: int, version: str, entries: Iterable[PayloadEntry]
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "version": version,
        "entries": [_entry_dict(entry) for entry in entries],
    }


def _manifest_digest(schema_version: int, version: str, entries: Iterable[PayloadEntry]) -> str:
    return hashlib.sha256(canonical_json(_manifest_body(schema_version, version, entries))).hexdigest()


def _manifest_dict(manifest: PayloadManifest) -> dict[str, object]:
    value = _manifest_body(manifest.schema_version, manifest.version, manifest.entries)
    value["digest"] = manifest.digest
    return value


def inventory_attestation(manifest: PayloadManifest) -> tuple[int, str]:
    """Return the non-circular authenticated installed inventory projection."""

    projection = []
    for entry in manifest.entries:
        expected_hash = (
            entry.sha256
            if entry.ownership == "dedicated" and entry.path != _VALIDATOR_PATH
            else None
        )
        projection.append(
            [entry.path, entry.ownership, entry.merge, entry.entry_type, expected_hash]
        )
    return len(projection), hashlib.sha256(canonical_json(projection)).hexdigest()


def _render_inventory_attestation(source: bytes, manifest: PayloadManifest) -> bytes:
    count, digest = inventory_attestation(manifest)
    replacement = (
        "# payload-inventory-attestation:start\n"
        f"_INSTALLED_INVENTORY_ENTRY_COUNT = {count}\n"
        f'_INSTALLED_INVENTORY_SHA256 = "{digest}"\n'
        "# payload-inventory-attestation:end\n"
    ).encode("utf-8")
    rendered, replacements = _ATTESTATION_PATTERN.subn(replacement, source)
    if replacements != 1:
        raise PayloadError("installed inventory attestation block is missing or malformed")
    return rendered


def _verify_inventory_attestation(
    source_root: pathlib.Path, manifest: PayloadManifest
) -> None:
    """Require the reviewed source block to match the generated projection."""

    count, digest = inventory_attestation(manifest)
    expected = f"expected count={count} sha256={digest}"
    current = read_file_secure(source_root, _VALIDATOR_PATH)
    try:
        rendered = _render_inventory_attestation(current, manifest)
    except PayloadError as error:
        raise PayloadError(f"installed inventory attestation is malformed; {expected}") from error
    if rendered != current:
        raise PayloadError(f"installed inventory attestation is stale; {expected}")


def _safe_type(path: pathlib.Path) -> tuple[str, os.stat_result]:
    try:
        file_stat = path.lstat()
    except OSError as error:
        raise PayloadError(f"cannot inspect payload path: {path.name}: {error}") from error
    if stat.S_ISLNK(file_stat.st_mode) or is_reparse_point(file_stat):
        raise PayloadError(f"link or reparse point is forbidden: {path.name}")
    if stat.S_ISDIR(file_stat.st_mode):
        return "directory", file_stat
    if stat.S_ISREG(file_stat.st_mode):
        return "file", file_stat
    raise PayloadError(f"special payload file is forbidden: {path.name}")


def _load_json_path(path: pathlib.Path, label: str) -> tuple[dict[str, object], bytes]:
    raw = read_file_secure(path.parent, path.name)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PayloadError(f"invalid {label}: {error}") from error
    if not isinstance(value, dict):
        raise PayloadError(f"invalid {label}: expected an object")
    return value, raw


def load_manifest(path: pathlib.Path | str) -> PayloadManifest:
    """Load and strictly validate a canonical payload manifest."""

    manifest_path = pathlib.Path(path)
    data, serialized = _load_json_path(manifest_path, "payload manifest")
    if set(data) != {"schema_version", "version", "entries", "digest"}:
        raise PayloadError("invalid payload manifest fields")
    if type(data["schema_version"]) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise PayloadError("unsupported payload manifest schema version")
    if not isinstance(data["version"], str) or not data["version"]:
        raise PayloadError("invalid payload manifest version")
    if not isinstance(data["entries"], list):
        raise PayloadError("invalid payload manifest entries")
    if not isinstance(data["digest"], str) or len(data["digest"]) != 64:
        raise PayloadError("invalid payload manifest digest")

    entries: list[PayloadEntry] = []
    seen_paths: set[str] = set()
    for raw_entry in data["entries"]:
        if not isinstance(raw_entry, dict) or set(raw_entry) != ENTRY_KEYS:
            raise PayloadError("invalid payload entry fields")
        path_value = normalize_relative_path(raw_entry["path"])
        if path_value in seen_paths:
            raise PayloadError(f"duplicate payload path: {path_value}")
        seen_paths.add(path_value)
        entry_type = raw_entry["entry_type"]
        mode = raw_entry["mode"]
        sha256 = raw_entry["sha256"]
        ownership = raw_entry["ownership"]
        merge = raw_entry["merge"]
        required = raw_entry["required"]
        if entry_type not in {"file", "directory"}:
            raise PayloadError(f"invalid payload entry type: {path_value}")
        if type(mode) is not int or mode not in {0o644, 0o755}:
            raise PayloadError(f"invalid payload mode: {path_value}")
        if entry_type == "directory" and (sha256 is not None or mode != 0o755):
            raise PayloadError(f"invalid directory payload entry: {path_value}")
        if entry_type == "file" and (
            not isinstance(sha256, str)
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
        ):
            raise PayloadError(f"invalid file hash: {path_value}")
        if ownership not in {"dedicated", "shared"}:
            raise PayloadError(f"invalid payload ownership: {path_value}")
        if ownership == "shared" and merge not in MERGE_VALUES:
            raise PayloadError(f"invalid shared merge strategy: {path_value}")
        if ownership == "dedicated" and merge is not None:
            raise PayloadError(f"dedicated payload entry cannot define merge: {path_value}")
        if type(required) is not bool:
            raise PayloadError(f"invalid required flag: {path_value}")
        entries.append(PayloadEntry(path_value, entry_type, mode, sha256, ownership, merge, required))
    if entries != sorted(entries, key=lambda entry: entry.path):
        raise PayloadError("payload entries are not canonically sorted")
    digest = _manifest_digest(data["schema_version"], data["version"], entries)
    if digest != data["digest"]:
        raise PayloadError("payload manifest digest mismatch")
    manifest = PayloadManifest(data["schema_version"], data["version"], tuple(entries), digest)
    if serialized != canonical_json(_manifest_dict(manifest)):
        raise PayloadError("payload manifest is not canonical JSON")
    return manifest


def _strict_string_list(policy: dict[str, object], key: str, *, paths: bool = False) -> list[str]:
    values = policy.get(key)
    if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
        raise PayloadError(f"invalid payload policy list: {key}")
    if len(values) != len(set(values)):
        raise PayloadError(f"invalid payload policy duplicate: {key}")
    if paths:
        for value in values:
            normalize_relative_path(value)
    return values


def _validate_policy_parity(policy: dict[str, object]) -> None:
    roots = policy["dedicated_roots"]
    dedicated = set(policy["dedicated_files"])
    nested = set(policy["nested_instruction_files"])
    shared = {item["path"]: item["merge"] for item in policy["shared_files"]}
    mapped = {item["source"]: item["target"] for item in policy["mapped_files"]}
    for item in policy["approved_sources"]:
        source = item["source"]
        target = item["target"]
        category = item["category"]
        expected_provenance = "codex-native"
        if category == "dedicated-root" and source.startswith("Codex Studio Testing Framework/"):
            expected_provenance = "upstream-adapted"
        elif category == "legal" and source == policy["license"]["plugin_source"]:
            expected_provenance = "upstream-legal"
        if item["provenance"] != expected_provenance or item["license"] != "MIT":
            raise PayloadError("invalid payload policy category provenance or license")
        if category != "shared" and (
            item["ownership"] != "dedicated" or item["merge"] is not None
        ):
            raise PayloadError("invalid payload policy category ownership or merge")
        if category == "dedicated-root" and (
            source != target or not any(source.startswith(root + "/") for root in roots)
        ):
            raise PayloadError("invalid payload policy dedicated-root mapping")
        if category == "standalone" and (source != target or source not in dedicated):
            raise PayloadError("invalid payload policy standalone mapping")
        if category == "nested-instruction" and (source != target or source not in nested):
            raise PayloadError("invalid payload policy nested mapping")
        if category == "shared" and (
            source != target or shared.get(source) != item["merge"] or item["ownership"] != "shared"
        ):
            raise PayloadError("invalid payload policy shared mapping or ownership")
        if category == "legal" and mapped.get(source) != target:
            raise PayloadError("invalid payload policy legal mapping")

    by_category = {
        category: {item["source"] for item in policy["approved_sources"] if item["category"] == category}
        for category in SOURCE_CATEGORIES
    }
    if by_category["standalone"] != dedicated:
        raise PayloadError("invalid payload policy standalone coverage")
    if by_category["nested-instruction"] != nested:
        raise PayloadError("invalid payload policy nested coverage")
    if by_category["shared"] != set(shared):
        raise PayloadError("invalid payload policy shared coverage")
    if by_category["legal"] != set(mapped):
        raise PayloadError("invalid payload policy legal coverage")


def _load_policy(path: pathlib.Path) -> dict[str, object]:
    policy, serialized = _load_json_path(path, "payload policy")
    if set(policy) != POLICY_KEYS:
        raise PayloadError("invalid payload policy fields")
    if type(policy["schema_version"]) is not int or policy["schema_version"] != SCHEMA_VERSION:
        raise PayloadError("invalid payload policy schema version")
    if not isinstance(policy["version"], str) or not policy["version"]:
        raise PayloadError("invalid payload policy version")
    for key in ("dedicated_roots", "dedicated_files", "nested_instruction_files"):
        _strict_string_list(policy, key, paths=True)
    _strict_string_list(policy, "denied_exact_paths", paths=True)
    prefixes = _strict_string_list(policy, "denied_prefixes")
    for prefix in prefixes:
        if not prefix.endswith("/"):
            raise PayloadError("invalid payload policy denied prefix")
        normalize_relative_path(prefix[:-1])
    ignored_names = _strict_string_list(policy, "ignored_names")
    if any("/" in name or "\\" in name or name in {".", ".."} for name in ignored_names):
        raise PayloadError("invalid payload policy ignored name")
    ignored_suffixes = _strict_string_list(policy, "ignored_suffixes")
    if any(not suffix.startswith(".") or "/" in suffix for suffix in ignored_suffixes):
        raise PayloadError("invalid payload policy ignored suffix")

    shared = policy["shared_files"]
    if not isinstance(shared, list):
        raise PayloadError("invalid payload policy shared files")
    shared_paths: set[str] = set()
    for item in shared:
        if not isinstance(item, dict) or set(item) != {"path", "merge"}:
            raise PayloadError("invalid payload policy shared file")
        path_value = normalize_relative_path(item["path"])
        if item["merge"] not in MERGE_VALUES or path_value in shared_paths:
            raise PayloadError("invalid payload policy shared file")
        shared_paths.add(path_value)

    mapped = policy["mapped_files"]
    if not isinstance(mapped, list):
        raise PayloadError("invalid payload policy mapped files")
    mapped_sources: set[str] = set()
    mapped_targets: set[str] = set()
    for item in mapped:
        if not isinstance(item, dict) or set(item) != {"source", "target"}:
            raise PayloadError("invalid payload policy mapped file")
        source = normalize_relative_path(item["source"])
        target = normalize_relative_path(item["target"])
        if source in mapped_sources or target in mapped_targets:
            raise PayloadError("invalid payload policy mapped duplicate")
        mapped_sources.add(source)
        mapped_targets.add(target)

    approved = policy["approved_sources"]
    if not isinstance(approved, list) or not approved:
        raise PayloadError("invalid payload policy approved sources")
    sources: set[str] = set()
    targets: set[str] = set()
    for item in approved:
        if not isinstance(item, dict) or set(item) != APPROVED_SOURCE_KEYS:
            raise PayloadError("invalid payload policy approved source")
        if (
            not isinstance(item["category"], str)
            or not isinstance(item["provenance"], str)
            or not isinstance(item["license"], str)
            or not isinstance(item["ownership"], str)
            or (item["merge"] is not None and not isinstance(item["merge"], str))
        ):
            raise PayloadError("invalid payload policy approved source types")
        source = normalize_relative_path(item["source"])
        target = normalize_relative_path(item["target"])
        if source in sources or target in targets:
            raise PayloadError("invalid payload policy approved source duplicate")
        sources.add(source)
        targets.add(target)
        if item["category"] not in SOURCE_CATEGORIES:
            raise PayloadError("invalid payload policy approved category")
        if item["provenance"] not in PROVENANCE_VALUES or item["license"] != "MIT":
            raise PayloadError("invalid payload policy approved provenance")
        if item["ownership"] not in {"dedicated", "shared"}:
            raise PayloadError("invalid payload policy approved ownership")
        if item["ownership"] == "dedicated" and item["merge"] is not None:
            raise PayloadError("invalid payload policy approved merge")
        if item["ownership"] == "shared" and item["merge"] not in MERGE_VALUES:
            raise PayloadError("invalid payload policy approved merge")
        if type(item["required"]) is not bool:
            raise PayloadError("invalid payload policy approved required")
        if source in policy["denied_exact_paths"] or any(
            source.startswith(prefix) for prefix in policy["denied_prefixes"]
        ) or _ignored(source, policy):
            raise PayloadError("invalid payload policy approved source is excluded")

    license_policy = policy["license"]
    if not isinstance(license_policy, dict) or set(license_policy) != {
        "canonical_source", "plugin_source", "sha256"
    }:
        raise PayloadError("invalid payload policy license")
    normalize_relative_path(license_policy["canonical_source"])
    normalize_relative_path(license_policy["plugin_source"])
    digest = license_policy["sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise PayloadError("invalid payload policy license digest")
    _validate_policy_parity(policy)
    if serialized != canonical_json(policy):
        raise PayloadError("payload policy is not canonical JSON")
    return policy


def _ignored(relative: str, policy: dict[str, object]) -> bool:
    parts = pathlib.PurePosixPath(relative).parts
    return any(part in policy["ignored_names"] for part in parts) or any(
        relative.endswith(suffix) for suffix in policy["ignored_suffixes"]
    )


def _discover_root_inventory(
    source_root: pathlib.Path, root: str, policy: dict[str, object]
) -> tuple[set[str], set[str]]:
    source_directory = source_root / pathlib.PurePosixPath(root)
    found: set[str] = set()
    found_directories: set[str] = set()
    for child, (entry_type, _) in walk_tree_secure(source_directory).items():
        relative = f"{root}/{child}"
        if _ignored(relative, policy):
            continue
        if entry_type == "directory":
            found_directories.add(relative)
        else:
            found.add(relative)
    return found, found_directories


def _validate_source_inventory(source_root: pathlib.Path, policy: dict[str, object]) -> None:
    approved_root_sources = {
        item["source"] for item in policy["approved_sources"] if item["category"] == "dedicated-root"
    }
    actual_root_sources: set[str] = set()
    actual_root_directories: set[str] = set()
    for root in policy["dedicated_roots"]:
        files, directories = _discover_root_inventory(source_root, root, policy)
        actual_root_sources.update(files)
        actual_root_directories.update(directories)
    expected_root_directories: set[str] = set()
    for source in approved_root_sources:
        source_path = pathlib.PurePosixPath(source)
        matching_root = next(
            root for root in policy["dedicated_roots"] if source.startswith(root + "/")
        )
        parent = source_path.parent
        while parent.as_posix() != matching_root:
            expected_root_directories.add(parent.as_posix())
            parent = parent.parent
    missing = approved_root_sources - actual_root_sources
    extra = actual_root_sources - approved_root_sources
    missing_directories = expected_root_directories - actual_root_directories
    extra_directories = actual_root_directories - expected_root_directories
    if missing or extra or missing_directories or extra_directories:
        raise PayloadError(
            "source inventory mismatch: "
            f"missing={sorted(missing)}, extra={sorted(extra)}, "
            f"missing_directories={sorted(missing_directories)}, "
            f"extra_directories={sorted(extra_directories)}"
        )
    for item in policy["approved_sources"]:
        if item["category"] != "dedicated-root":
            try:
                inspect_secure(source_root, item["source"], expect="file")
            except PayloadError as error:
                raise PayloadError(f"approved source is missing or unsafe: {item['source']}: {error}") from error


def _verify_license_sources(source_root: pathlib.Path, policy: dict[str, object]) -> None:
    license_policy = policy["license"]
    canonical = read_file_secure(source_root, license_policy["canonical_source"])
    plugin_license = read_file_secure(source_root, license_policy["plugin_source"])
    approved_digest = license_policy["sha256"]
    if canonical != plugin_license or hashlib.sha256(canonical).hexdigest() != approved_digest:
        raise PayloadError("plugin LICENSE is not the complete approved MIT license")


def _load_plugin_version(plugin_root: pathlib.Path) -> str:
    plugin_data, _ = _load_json_path(plugin_root / ".codex-plugin/plugin.json", "plugin manifest")
    version = plugin_data.get("version")
    if not isinstance(version, str) or not version:
        raise PayloadError("invalid plugin version")
    return version


def _materialize(
    source_root: pathlib.Path,
    plugin_root: pathlib.Path,
    destination_assets: pathlib.Path,
) -> PayloadManifest:
    policy_path = plugin_root / "assets/payload-policy.json"
    policy = _load_policy(policy_path)
    version = _load_plugin_version(plugin_root)
    if version != policy["version"]:
        raise PayloadError("plugin, policy, and payload versions must be equal")
    _validate_source_inventory(source_root, policy)
    _verify_license_sources(source_root, policy)
    studio = destination_assets / "studio"
    studio.mkdir(mode=0o755)
    copy_file_secure(plugin_root, "assets/payload-policy.json", destination_assets, "payload-policy.json", 0o644)

    entries: list[PayloadEntry] = []
    directory_paths: set[str] = set()
    for item in policy["approved_sources"]:
        target = item["target"]
        parent = pathlib.PurePosixPath(target).parent
        while parent.parts:
            directory_paths.add(parent.as_posix())
            parent = parent.parent
        _, source_stat = inspect_secure(source_root, item["source"], expect="file")
        mode = 0o755 if stat.S_IMODE(source_stat.st_mode) & 0o111 else 0o644
        digest = copy_file_secure(source_root, item["source"], studio, target, mode)
        entries.append(
            PayloadEntry(target, "file", mode, digest, item["ownership"], item["merge"], item["required"])
        )
    for directory in sorted(directory_paths):
        set_directory_mode_secure(studio, directory, 0o755)
        entries.append(PayloadEntry(directory, "directory", 0o755, None, "dedicated", None, True))
    entries.sort(key=lambda entry: entry.path)
    digest = _manifest_digest(SCHEMA_VERSION, version, entries)
    manifest = PayloadManifest(SCHEMA_VERSION, version, tuple(entries), digest)
    write_file_secure(destination_assets, "payload-manifest.json", canonical_json(_manifest_dict(manifest)))
    reloaded = load_manifest(destination_assets / "payload-manifest.json")
    if reloaded != manifest:
        raise PayloadError("staged manifest reload differs from generated manifest")
    _validate_source_inventory(source_root, policy)
    issues = _verify_materialized(destination_assets, reloaded)
    if issues:
        raise PayloadError("generated payload failed verification: " + "; ".join(issues))
    _verify_legal(studio, policy)
    return manifest


def _walk_payload(root: pathlib.Path) -> dict[str, tuple[str, os.stat_result]]:
    return walk_tree_secure(root)


def _verify_materialized(assets: pathlib.Path, manifest: PayloadManifest) -> list[str]:
    studio = assets / "studio"
    issues: list[str] = []
    try:
        if _safe_type(assets)[0] != "directory":
            return ["payload assets root is not a directory"]
        inspect_secure(assets, "studio", expect="directory")
        actual = _walk_payload(studio)
    except PayloadError as error:
        return [str(error)]
    expected = {entry.path: entry for entry in manifest.entries}
    for path, entry in expected.items():
        actual_value = actual.get(path)
        if actual_value is None:
            issues.append(f"missing payload path: {path}")
            continue
        actual_type, file_stat = actual_value
        if actual_type != entry.entry_type:
            issues.append(f"payload entry type mismatch: {path}")
            continue
        if not mode_matches(file_stat, entry.mode):
            issues.append(f"payload mode mismatch: {path}")
        if entry.entry_type == "file":
            try:
                digest, _ = hash_file_secure(studio, path)
            except PayloadError as error:
                issues.append(str(error))
            else:
                if digest != entry.sha256:
                    issues.append(f"payload sha256 mismatch: {path}")
    for path in sorted(set(actual) - set(expected)):
        issues.append(f"unexpected payload path: {path}")
    return issues


def _verify_legal(studio: pathlib.Path, policy: dict[str, object]) -> None:
    license_target = next(
        item["target"] for item in policy["approved_sources"]
        if item["source"] == policy["license"]["plugin_source"]
    )
    license_bytes = read_file_secure(studio, license_target)
    if hashlib.sha256(license_bytes).hexdigest() != policy["license"]["sha256"]:
        raise PayloadError("payload legal LICENSE differs from the complete approved MIT license")
    attribution_target = next(
        item["target"] for item in policy["approved_sources"]
        if item["category"] == "legal" and item["target"].endswith("ATTRIBUTION.md")
    )
    try:
        attribution = read_file_secure(studio, attribution_target).decode("utf-8")
    except UnicodeError as error:
        raise PayloadError("payload attribution is not UTF-8") from error
    required = (
        "https://github.com/Donchitos/Claude-Code-Game-Studios",
        "independent Codex-native adaptation",
        "Copyright (c) 2026 hongyuanc",
        "not endorsed by Donchitos, Anthropic, or OpenAI",
    )
    if any(needle not in attribution for needle in required):
        raise PayloadError("payload legal attribution is incomplete")


def verify_manifest_snapshot(
    plugin_root: pathlib.Path | str, manifest: PayloadManifest
) -> None:
    """Verify that the manifest path still contains the exact consumed bytes."""

    plugin = pathlib.Path(plugin_root)
    serialized = read_file_secure(plugin, "assets/payload-manifest.json")
    if serialized != canonical_json(_manifest_dict(manifest)):
        raise PayloadError("payload manifest changed during verification")


def verify_payload(
    plugin_root: pathlib.Path | str,
    expected_manifest: PayloadManifest | None = None,
) -> list[str]:
    """Return deterministic findings for an embedded plugin payload."""

    plugin = pathlib.Path(plugin_root)
    try:
        if _safe_type(plugin)[0] != "directory":
            return ["plugin root is not a directory"]
        inspect_secure(plugin, "assets", expect="directory")
        manifest = (
            load_manifest(plugin / "assets/payload-manifest.json")
            if expected_manifest is None
            else expected_manifest
        )
        verify_manifest_snapshot(plugin, manifest)
    except PayloadError as error:
        return [str(error)]
    issues: list[str] = []
    try:
        policy = _load_policy(plugin / "assets/payload-policy.json")
        version = _load_plugin_version(plugin)
        if version != manifest.version or policy["version"] != manifest.version:
            issues.append("plugin, policy, and payload version mismatch")
    except PayloadError as error:
        issues.append(str(error))
        policy = None
    issues.extend(_verify_materialized(plugin / "assets", manifest))
    if policy is not None:
        try:
            _verify_legal(plugin / "assets/studio", policy)
            plugin_license = read_file_secure(plugin, "LICENSE")
            if hashlib.sha256(plugin_license).hexdigest() != policy["license"]["sha256"]:
                issues.append("plugin LICENSE differs from the complete approved MIT license")
        except (OSError, UnicodeError, PayloadError) as error:
            issues.append(str(error))
    try:
        verify_manifest_snapshot(plugin, manifest)
    except PayloadError as error:
        issues.append(str(error))
    return sorted(set(issues))


def load_verified_manifest(plugin_root: pathlib.Path | str) -> PayloadManifest:
    """Load one manifest object and verify the payload against that snapshot."""

    plugin = pathlib.Path(plugin_root)
    manifest = load_manifest(plugin / "assets/payload-manifest.json")
    issues = verify_payload(plugin, expected_manifest=manifest)
    if issues:
        raise PayloadError("invalid plugin payload: " + "; ".join(issues))
    return manifest


def _tree_fingerprint(root: pathlib.Path) -> dict[str, tuple[str, int, str | None]]:
    result: dict[str, tuple[str, int, str | None]] = {}
    for path, (entry_type, file_stat) in _walk_payload(root).items():
        mode = stat.S_IMODE(file_stat.st_mode) if os.name != "nt" else (0o644 if entry_type == "file" else 0o755)
        digest = hash_file_secure(root, path)[0] if entry_type == "file" else None
        result[path] = (entry_type, mode, digest)
    return result


def build_payload(
    source_root: pathlib.Path | str,
    plugin_root: pathlib.Path | str,
    check: bool = False,
) -> PayloadManifest:
    """Build or freshness-check the policy-selected operational payload."""

    source = pathlib.Path(source_root)
    plugin = pathlib.Path(plugin_root)
    if _safe_type(source)[0] != "directory" or _safe_type(plugin)[0] != "directory":
        raise PayloadError("source and plugin roots must be directories")
    assets = plugin / "assets"
    if assets.exists() or assets.is_symlink():
        inspect_secure(plugin, "assets", expect="directory")
    with tempfile.TemporaryDirectory(prefix=".payload-stage-", dir=plugin.parent) as temporary:
        staged_plugin = pathlib.Path(temporary) / "plugin"
        staged_plugin.mkdir(mode=0o755)
        (staged_plugin / ".codex-plugin").mkdir(mode=0o755)
        copy_file_secure(plugin, ".codex-plugin/plugin.json", staged_plugin, ".codex-plugin/plugin.json", 0o644)
        copy_file_secure(plugin, "LICENSE", staged_plugin, "LICENSE", 0o644)
        staged_assets = staged_plugin / "assets"
        staged_assets.mkdir(mode=0o755)
        manifest = _materialize(source, plugin, staged_assets)
        _verify_inventory_attestation(source, manifest)
        staged_issues = verify_payload(staged_plugin)
        if staged_issues:
            raise PayloadError("staged payload failed public verification: " + "; ".join(staged_issues))
        if check:
            current_issues = verify_payload(plugin)
            if current_issues or not assets.is_dir() or _tree_fingerprint(staged_assets) != _tree_fingerprint(assets):
                raise PayloadError("Codex Game Studios payload is stale")
            return manifest
        backup = pathlib.Path(temporary) / "previous-assets"
        if assets.exists() or assets.is_symlink():
            inspect_secure(plugin, "assets", expect="directory")
            os.replace(assets, backup)
        try:
            os.replace(staged_assets, assets)
        except BaseException:
            if backup.exists() and not assets.exists():
                os.replace(backup, assets)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    return manifest
