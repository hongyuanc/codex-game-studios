from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools.codex_studio.engine_pack import load_studio_config
from tools.codex_studio.start_initialization import (
    _real_root,
    _relative_state,
    contract,
    contract_fingerprint,
    contract_summary,
    audit_session,
    detect_project_state,
    ledger_schema,
    ledger_schema_document,
    ledger_schema_fingerprint,
    preflight_session,
    validate_contract,
    validate_documentation,
    validate_session,
)
from tools.codex_studio.validate import validate_skill


ROOT = Path(__file__).resolve().parents[2]
START = ROOT / ".agents/skills/start/SKILL.md"
BUNDLED_START_VALIDATOR = (
    ROOT / "plugins/codex-game-studios/assets/studio/tools/codex_studio/start_initialization.py"
)
def valid_initialization_session(initialization_contract: dict[str, object]) -> dict[str, object]:
    authority_digest = hashlib.sha256(
        initialization_contract["default_authority_toml"].encode("utf-8")
    ).hexdigest()
    action = {
        "path": ".codex/studio.toml",
        "kind": "create",
        "material_change": "write the complete default authority",
        "form": "atomic",
        "expanded_paths": [".codex/studio.toml"],
        "sha256": authority_digest,
    }
    return {
        "authority_state": "missing",
        "events": [
            {"type": "detect"},
            {"type": "select-next-step", "next_step": "brainstorm"},
            {
                "type": "initialization-changeset",
                "authority_toml": initialization_contract["default_authority_toml"],
                "actions": [action],
            },
            {"type": "approval"},
            {
                "type": "write",
                "path": action["path"],
                "kind": action["kind"],
                "material_change": action["material_change"],
                "sha256": action["sha256"],
            },
        ],
    }


def make_git_root(project: Path) -> None:
    subprocess.run(["git", "init", "-q", str(project)], check=True)


def initialized_stage_session(stage_action: dict[str, object]) -> dict[str, object]:
    return {
        "authority_state": "initialized",
        "events": [
            {"type": "detect"},
            {"type": "stage-proposal", "actions": [stage_action]},
            {"type": "stage-approval"},
            {"type": "write", "path": stage_action["path"], "kind": stage_action["kind"], "material_change": stage_action["material_change"], "sha256": stage_action["sha256"]},
        ],
    }


def initialized_review_session(review_action: dict[str, object]) -> dict[str, object]:
    return {
        "authority_state": "initialized",
        "events": [
            {"type": "detect"},
            {"type": "review-mode-proposal", "actions": [review_action]},
            {"type": "review-mode-approval"},
            {"type": "write", "path": review_action["path"], "kind": review_action["kind"], "material_change": review_action["material_change"], "sha256": review_action["sha256"]},
        ],
    }


def review_action(content: str | None, *, kind: str = "modify") -> dict[str, object]:
    return {
        "path": ".codex/studio.toml",
        "kind": kind,
        "material_change": "change the initialized review mode",
        "form": "atomic",
        "expanded_paths": [".codex/studio.toml"],
        "sha256": None if content is None else hashlib.sha256(content.encode()).hexdigest(),
    }


class StartSkillTests(unittest.TestCase):
    def test_start_preflights_truly_fresh_real_git_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"; make_git_root(project)
            authority = valid_initialization_session(contract())
            parent = {"path": ".codex", "kind": "directory-create", "material_change": "create authority parent", "form": "atomic", "expanded_paths": [".codex"], "required_by": ".codex/studio.toml", "sha256": None}
            action = authority["events"][2]["actions"][0]
            authority["events"][2]["actions"] = [parent, action]
            authority["events"].extend([])
            authority["events"][-1:] = [{"type":"write","path":parent["path"],"kind":parent["kind"],"material_change":parent["material_change"],"sha256":None}, authority["events"][-1]]
            self.assertEqual("missing", detect_project_state(project)["authority_state"])
            self.assertEqual("ok", preflight_session(authority, project)["status"])

    def test_start_rejects_fake_and_nested_git_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            for kind in ("directory", "file"):
                fake = Path(directory) / f"fake-{kind}"
                fake.mkdir()
                if kind == "directory":
                    (fake / ".git").mkdir()
                else:
                    (fake / ".git").write_text("gitdir: ../missing\n", encoding="utf-8")
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    detect_project_state(fake)
            real = Path(directory) / "real"; make_git_root(real); nested = real / "nested"; nested.mkdir()
            with self.assertRaises(ValueError): detect_project_state(nested)

    def test_start_accepts_real_linked_worktree_git_file(self):
        with tempfile.TemporaryDirectory() as directory:
            primary = Path(directory) / "primary"
            linked = Path(directory) / "linked"
            make_git_root(primary)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(primary),
                    "-c",
                    "user.name=Start Tests",
                    "-c",
                    "user.email=start-tests@example.invalid",
                    "commit",
                    "--allow-empty",
                    "-q",
                    "-m",
                    "fixture",
                ],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(primary), "worktree", "add", "-q", "-b", "linked-fixture", str(linked)],
                check=True,
            )

            self.assertTrue((linked / ".git").is_file())
            self.assertEqual("missing", detect_project_state(linked)["authority_state"])

    def test_start_rejects_swappable_symlink_in_project_root_ancestry(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            first_parent = base / "first-parent"
            second_parent = base / "second-parent"
            first = first_parent / "project"
            second = second_parent / "project"
            first.mkdir(parents=True)
            (second / ".codex").mkdir(parents=True)
            make_git_root(first)
            make_git_root(second)
            (second / ".codex/studio.toml").write_text(
                contract()["default_authority_toml"], encoding="utf-8"
            )
            parent_link = base / "parent-link"
            os.symlink(first_parent, parent_link)
            original_samefile = os.path.samefile

            def swap_after_identity_check(left: object, right: object) -> bool:
                matched = original_samefile(left, right)
                parent_link.unlink()
                os.symlink(second_parent, parent_link)
                return matched

            with mock.patch(
                "tools.codex_studio.start_initialization.os.path.samefile",
                side_effect=swap_after_identity_check,
            ), self.assertRaises(ValueError):
                detect_project_state(parent_link / "project")

    def test_start_missing_ancestry_is_limited_to_approved_target_parents(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            make_git_root(project)
            root = _real_root(project)

            self.assertEqual("missing", _relative_state(root, ".codex/studio.toml")[0])
            self.assertEqual("missing", _relative_state(root, "production/stage.txt")[0])
            for relative in ("other/child", ".codex/agents/file"):
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    _relative_state(root, relative)

    def test_start_selection_schema_and_stage_requirement_are_closed(self):
        session = valid_initialization_session(contract())
        session["events"][1]["extra"] = True
        with self.assertRaises(ValueError): validate_session(session)
        text = START.read_text(encoding="utf-8")
        self.assertIn('"examples"', text)
        self.assertIn('"initialization-changeset"', text)

    def test_start_selection_stage_matrix_enforces_setup_engine_if_and_only_if(self):
        authority = valid_initialization_session(contract())
        authority_action = authority["events"][2]["actions"][0]
        authority_write = authority["events"][4]
        stage_digest = hashlib.sha256(b"Concept\n").hexdigest()
        stage_action = {
            "path": "production/stage.txt",
            "kind": "create",
            "material_change": "write the selected initial stage",
            "form": "atomic",
            "expanded_paths": ["production/stage.txt"],
            "sha256": stage_digest,
        }
        stage_write = {
            "type": "write",
            "path": stage_action["path"],
            "kind": stage_action["kind"],
            "material_change": stage_action["material_change"],
            "sha256": stage_action["sha256"],
        }

        for next_step, includes_stage, accepted in (
            ("brainstorm", False, True),
            ("project-stage-detect", False, True),
            ("setup-engine", True, True),
            ("setup-engine", False, False),
            ("brainstorm", True, False),
            ("project-stage-detect", True, False),
        ):
            actions = [authority_action, *([stage_action] if includes_stage else [])]
            writes = [authority_write, *([stage_write] if includes_stage else [])]
            session = {
                "authority_state": "missing",
                "events": [
                    {"type": "detect"},
                    {"type": "select-next-step", "next_step": next_step},
                    {
                        "type": "initialization-changeset",
                        "authority_toml": contract()["default_authority_toml"],
                        "actions": actions,
                    },
                    {"type": "approval"},
                    *writes,
                ],
            }
            with self.subTest(next_step=next_step, includes_stage=includes_stage):
                if accepted:
                    validate_session(session)
                else:
                    with self.assertRaises(ValueError):
                        validate_session(session)
    def test_start_initialized_groups_reject_cross_target_smuggling(self):
        digest = hashlib.sha256(b"stage\n").hexdigest()
        stage = {"path": "production/stage.txt", "kind": "create", "material_change": "write stage", "form": "atomic", "expanded_paths": ["production/stage.txt"], "sha256": digest}
        authority = valid_initialization_session(contract())["events"][2]["actions"][0]
        for proposal, actions in (("stage-proposal", [stage, authority]), ("review-mode-proposal", [authority, stage])):
            writes = [{"type": "write", "path": action["path"], "kind": action["kind"], "material_change": action["material_change"], "sha256": action["sha256"]} for action in actions]
            session = {"authority_state": "initialized", "events": [{"type": "detect"}, {"type": proposal, "actions": actions}, {"type": "stage-approval" if proposal == "stage-proposal" else "review-mode-approval"}, *writes]}
            with self.subTest(proposal=proposal), self.assertRaises(ValueError):
                validate_session(session)

    def test_start_preflight_rejects_unsafe_roots_and_parent_links(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for root in (base / "absent", base / "regular"):
                if root.name == "regular":
                    root.write_text("not a directory", encoding="utf-8")
                with self.subTest(root=root), self.assertRaises(ValueError):
                    detect_project_state(root)
            project = base / "project"
            (project / ".codex").mkdir(parents=True)
            make_git_root(project)
            link_root = base / "linked-project"
            os.symlink(project, link_root)
            with self.assertRaises(ValueError):
                preflight_session(valid_initialization_session(contract()), link_root)
            (project / ".codex/studio.toml").write_text(contract()["default_authority_toml"], encoding="utf-8")
            external = base / "external"
            external.mkdir()
            os.symlink(external, project / "production")
            stage = {"path": "production/stage.txt", "kind": "create", "material_change": "write stage", "form": "atomic", "expanded_paths": ["production/stage.txt"], "sha256": hashlib.sha256(b"stage\n").hexdigest()}
            with self.assertRaises(ValueError):
                preflight_session(initialized_stage_session(stage), project)

    def test_start_cli_closes_non_object_and_control_event_schemas(self):
        with tempfile.TemporaryDirectory() as directory:
            external, project = Path(directory) / "external", Path(directory) / "project"
            (project / ".codex").mkdir(parents=True)
            make_git_root(project)
            external.mkdir()
            environment = {**os.environ, "PYTHONPATH": ""}
            for payload in ("[]", "null", "1", '"ledger"', "{"):
                ledger = external / "ledger.json"
                ledger.write_text(payload, encoding="utf-8")
                result = subprocess.run([sys.executable, "-B", str(BUNDLED_START_VALIDATOR), "--preflight", str(ledger), "--project-root", str(project)], cwd=external, env=environment, text=True, capture_output=True, check=False)
                with self.subTest(payload=payload):
                    self.assertEqual(2, result.returncode)
                    self.assertNotIn("Traceback", result.stderr)
            hidden = valid_initialization_session(contract())
            hidden["events"][0]["hidden"] = True
            with self.assertRaises(ValueError):
                validate_session(hidden)
            help_result = subprocess.run([sys.executable, "-B", str(BUNDLED_START_VALIDATOR), "--help"], cwd=external, env=environment, text=True, capture_output=True, check=False)
            self.assertEqual(0, help_result.returncode)
            self.assertIn("ledger schema version", help_result.stdout.lower())

    def test_start_docs_publish_complete_versioned_ledger_schema(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("start-initialization-ledger-schema:sha256=", text)
        self.assertIn('"ledger_schema_version":1', text)
        self.assertIn('"required_by":"string (directory-create only)"', text)

    def test_start_docs_embed_exact_fingerprinted_ledger_schema_body(self):
        framework = ROOT / "Codex Studio Testing Framework/skills/utility/start.md"
        runtime_text = START.read_text(encoding="utf-8")
        framework_text = framework.read_text(encoding="utf-8")
        schema_body = ledger_schema_document()

        self.assertEqual(hashlib.sha256(schema_body.encode()).hexdigest(), ledger_schema_fingerprint())
        self.assertEqual(1, runtime_text.count(schema_body))
        self.assertEqual(1, framework_text.count(schema_body))
        validate_documentation(runtime_text, framework_text)

    def test_start_documentation_rejects_every_material_schema_section_mutation(self):
        framework = ROOT / "Codex Studio Testing Framework/skills/utility/start.md"
        runtime_text = START.read_text(encoding="utf-8")
        framework_text = framework.read_text(encoding="utf-8")
        schema_body = ledger_schema_document()
        schema = ledger_schema()

        for section in schema:
            mutated = json.loads(json.dumps(schema))
            value = mutated[section]
            if isinstance(value, dict):
                value["wave_6_mutation"] = True
            elif isinstance(value, list):
                value.append("wave-6-mutation")
            elif isinstance(value, int):
                mutated[section] = value + 1
            else:
                mutated[section] = f"{value}-wave-6-mutation"
            mutated_body = json.dumps(mutated, sort_keys=True, separators=(",", ":"))
            with self.subTest(section=section), self.assertRaises(ValueError):
                validate_documentation(
                    runtime_text.replace(schema_body, mutated_body),
                    framework_text,
                )

        for label, mutated_runtime in (
            ("missing body", runtime_text.replace(schema_body, "")),
            ("duplicate body", runtime_text.replace(schema_body, schema_body + "\n" + schema_body)),
        ):
            with self.subTest(label=label), self.assertRaises(ValueError):
                validate_documentation(mutated_runtime, framework_text)

    def test_start_canonical_ledger_examples_execute_against_declared_repository_state(self):
        examples = ledger_schema()["examples"]

        self.assertEqual(
            {
                "first_run_brainstorm",
                "first_run_project_stage_detect",
                "first_run_setup_engine",
                "initialized_review_mode",
                "initialized_stage",
                "initialized_stage_and_review_mode",
            },
            set(examples),
        )
        for name, example in examples.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                self.assertEqual(
                    {"initial_state", "session", "write_contents"}, set(example)
                )
                initial_state = example["initial_state"]
                self.assertEqual({"directories", "files"}, set(initial_state))
                directories = initial_state["directories"]
                self.assertEqual({".codex", "production"}, set(directories))
                self.assertTrue(all(state in {"directory", "missing"} for state in directories.values()))
                session = example["session"]
                write_contents = example["write_contents"]
                validate_session(session, directories=directories)

                project = Path(directory) / "project"
                make_git_root(project)
                for relative, state in directories.items():
                    if state == "directory":
                        (project / relative).mkdir(parents=True)
                for relative, content in initial_state["files"].items():
                    target = project / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8")

                self.assertEqual("ok", preflight_session(session, project)["status"])
                for event in session["events"]:
                    if event["type"] not in {"initialization-changeset", "stage-proposal", "review-mode-proposal"}:
                        continue
                    for action in event["actions"]:
                        target = project / action["path"]
                        if action["kind"] == "directory-create":
                            target.mkdir()
                        elif action["kind"] == "delete":
                            target.unlink()
                        else:
                            target.write_text(write_contents[action["path"]], encoding="utf-8")

                self.assertEqual("ok", audit_session(session, project)["status"])
                self.assertEqual("initialized", detect_project_state(project)["authority_state"])
                load_studio_config(project)

    def test_start_initialized_review_mode_rejects_delete_action(self):
        session = initialized_review_session(review_action(None, kind="delete"))

        with self.assertRaises(ValueError):
            validate_session(session)

    def test_start_initialized_review_mode_preflight_rejects_noncanonical_post_images(self):
        authority = contract()["default_authority_toml"]
        valid_example = ledger_schema()["examples"]["initialized_review_mode"]
        cases = {
            "truncated authority": 'review_mode = "full"\n',
            "other field changed": authority.replace(
                'review_mode = "phase-gated"', 'review_mode = "full"'
            ).replace('model_policy = "balanced"', 'model_policy = "thorough"'),
        }

        for name, post_image in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "project"
                (project / ".codex").mkdir(parents=True)
                make_git_root(project)
                (project / ".codex/studio.toml").write_text(authority, encoding="utf-8")
                session = json.loads(json.dumps(valid_example["session"]))
                digest = hashlib.sha256(post_image.encode()).hexdigest()
                session["events"][1]["actions"][0]["sha256"] = digest
                session["events"][3]["sha256"] = digest

                with self.assertRaises(ValueError):
                    preflight_session(session, project)

    def test_start_initialized_review_mode_preflight_binds_exact_current_authority(self):
        authority = contract()["default_authority_toml"]
        valid_example = ledger_schema()["examples"]["initialized_review_mode"]
        session = json.loads(json.dumps(valid_example["session"]))
        proposal = session["events"][1]
        proposal["authority_before"]["model_policy"] = "thorough"
        broadened = valid_example["write_contents"][".codex/studio.toml"].replace(
            'model_policy = "balanced"', 'model_policy = "thorough"'
        )
        digest = hashlib.sha256(broadened.encode()).hexdigest()
        proposal["actions"][0]["sha256"] = digest
        session["events"][3]["sha256"] = digest
        validate_session(session)

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            (project / ".codex").mkdir(parents=True)
            make_git_root(project)
            (project / ".codex/studio.toml").write_text(authority, encoding="utf-8")

            with self.assertRaises(ValueError):
                preflight_session(session, project)

    def test_start_initialized_review_mode_audit_rejects_invalid_or_broadened_results(self):
        authority = contract()["default_authority_toml"]
        cases = {
            "deleted authority": (None, "delete"),
            "truncated authority": ('review_mode = "full"\n', "modify"),
            "other field changed": (
                authority.replace(
                    'review_mode = "phase-gated"', 'review_mode = "full"'
                ).replace('model_policy = "balanced"', 'model_policy = "thorough"'),
                "modify",
            ),
        }

        for name, (post_image, kind) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "project"
                (project / ".codex").mkdir(parents=True)
                make_git_root(project)
                target = project / ".codex/studio.toml"
                target.write_text(authority, encoding="utf-8")
                if kind == "delete":
                    session = initialized_review_session(review_action(None, kind="delete"))
                else:
                    session = json.loads(json.dumps(
                        ledger_schema()["examples"]["initialized_review_mode"]["session"]
                    ))
                if post_image is None:
                    target.unlink()
                else:
                    target.write_text(post_image, encoding="utf-8")

                with self.assertRaises(ValueError):
                    audit_session(session, project)

    def test_start_audit_rejects_links_and_detects_target_identity_swap(self):
        with tempfile.TemporaryDirectory() as directory:
            project, external = Path(directory) / "project", Path(directory) / "external"
            (project / ".codex").mkdir(parents=True); (project / "production").mkdir(); external.mkdir(); make_git_root(project)
            authority = contract()["default_authority_toml"]
            (project / ".codex/studio.toml").write_text(authority, encoding="utf-8")
            digest = hashlib.sha256(b"stage\n").hexdigest()
            stage = {"path": "production/stage.txt", "kind": "create", "material_change": "write stage", "form": "atomic", "expanded_paths": ["production/stage.txt"], "sha256": digest}
            session = initialized_stage_session(stage)
            (external / "stage.txt").write_text("stage\n", encoding="utf-8")
            os.symlink(external / "stage.txt", project / "production/stage.txt")
            with self.assertRaises(ValueError):
                audit_session(session, project)
            (project / "production/stage.txt").unlink()
            os.symlink(external / "missing.txt", project / "production/stage.txt")
            delete = {**stage, "kind": "delete", "sha256": None}
            with self.assertRaises(ValueError):
                audit_session(initialized_stage_session(delete), project)

    def test_start_audit_rejects_descriptor_target_replacement_during_secure_read(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            (project / ".codex").mkdir(parents=True)
            (project / "production").mkdir()
            make_git_root(project)
            (project / ".codex/studio.toml").write_text(
                contract()["default_authority_toml"], encoding="utf-8"
            )
            target = project / "production/stage.txt"
            target.write_text("Concept\n", encoding="utf-8")
            digest = hashlib.sha256(b"Concept\n").hexdigest()
            action = {
                "path": "production/stage.txt",
                "kind": "create",
                "material_change": "write stage",
                "form": "atomic",
                "expanded_paths": ["production/stage.txt"],
                "sha256": digest,
            }
            original_read = os.read
            original_identity = (target.stat().st_dev, target.stat().st_ino)
            replaced = False

            def replace_target(descriptor: int, size: int) -> bytes:
                nonlocal replaced
                opened = os.fstat(descriptor)
                if not replaced and (opened.st_dev, opened.st_ino) == original_identity:
                    replaced = True
                    target.rename(project / "production/original-stage.txt")
                    target.write_text("Concept\n", encoding="utf-8")
                return original_read(descriptor, size)

            with mock.patch(
                "tools.codex_studio.start_initialization.os.read",
                side_effect=replace_target,
            ), self.assertRaises(ValueError):
                audit_session(initialized_stage_session(action), project)

    def test_start_initialization_rejects_wave_three_ledger_bypasses(self):
        # Arrange
        initialization_contract = contract()
        valid = valid_initialization_session(initialization_contract)
        authority_action = valid["events"][2]["actions"][0]
        authority_write = valid["events"][4]
        stage_digest = hashlib.sha256(b"stage: concept\n").hexdigest()
        stage_action = {
            "path": "production/stage.txt",
            "kind": "create",
            "material_change": "write the selected initial stage",
            "form": "atomic",
            "expanded_paths": ["production/stage.txt"],
            "sha256": stage_digest,
        }
        stage_write = {
            "type": "write",
            "path": stage_action["path"],
            "kind": stage_action["kind"],
            "material_change": stage_action["material_change"],
            "sha256": stage_digest,
        }
        production_parent = {
            "path": "production",
            "kind": "directory-create",
            "material_change": "create the parent for the selected stage",
            "form": "atomic",
            "expanded_paths": ["production"],
            "required_by": "production/stage.txt",
            "sha256": None,
        }
        parent_write = {
            "type": "write",
            "path": production_parent["path"],
            "kind": production_parent["kind"],
            "material_change": production_parent["material_change"],
            "sha256": None,
        }
        duplicate_initialized_group = [
            {"type": "stage-proposal", "actions": [stage_action]},
            {"type": "stage-approval"},
            stage_write,
        ]
        cases = {
            "duplicate action and write": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {**valid["events"][2], "actions": [authority_action, authority_action]},
                    *valid["events"][3:4],
                    authority_write,
                    authority_write,
                ],
            },
            "unknown action field": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [{**authority_action, "hidden_expanded_paths": ["production/stage.txt"]}],
                    },
                    *valid["events"][3:],
                ],
            },
            "missing authority action": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {**valid["events"][2], "actions": [stage_action]},
                    *valid["events"][3:4],
                    stage_write,
                ],
            },
            "child before parent": ({
                **valid,
                "events": [
                    *valid["events"][:2],
                    {**valid["events"][2], "actions": [authority_action, stage_action, production_parent]},
                    *valid["events"][3:4],
                    authority_write,
                    stage_write,
                    parent_write,
                ],
            }, {".codex": True, "production": False}),
            "parent paired with delete": ({
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [authority_action, {**stage_action, "kind": "delete", "sha256": None}, production_parent],
                    },
                    *valid["events"][3:4],
                    authority_write,
                    {**stage_write, "kind": "delete", "sha256": None},
                    parent_write,
                ],
            }, {".codex": True, "production": False}),
            "duplicate initialized proposal": ({
                "authority_state": "initialized",
                "events": [{"type": "detect"}, *duplicate_initialized_group, *duplicate_initialized_group],
            }, {".codex": True, "production": True}),
        }

        # Act / Assert
        for name, candidate in cases.items():
            with self.subTest(name=name):
                session, directories = candidate if isinstance(candidate, tuple) else (candidate, None)
                with self.assertRaises(ValueError):
                    validate_session(session, directories=directories)

    def test_start_detect_project_state_blocks_every_invalid_authority_shape(self):
        # Arrange
        complete = contract()["default_authority_toml"]
        cases = {
            "unreadable": None,
            "malformed": 'engine = [',
            "unknown key": complete + 'unknown = "value"\n',
            "missing key": complete.replace('model_policy = "balanced"\n', ""),
            "invalid enum": complete.replace('engine = "unconfigured"', 'engine = "mystery"'),
            "cross field": complete.replace('active_engine_pack = "none"', 'active_engine_pack = "godot"'),
        }

        # Act / Assert
        for name, content in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "project"
                control = project / ".codex"
                control.mkdir(parents=True)
                make_git_root(project)
                studio = control / "studio.toml"
                if content is None:
                    studio.mkdir()
                else:
                    studio.write_text(content, encoding="utf-8")
                try:
                    state = detect_project_state(project)
                except Exception:
                    state = {"authority_state": "exception"}
                self.assertEqual("repair-block", state["authority_state"])
                with self.assertRaises(ValueError):
                    preflight_session(valid_initialization_session(contract()), project)

    def test_start_bundled_validator_executes_preflight_from_empty_consumer_cwd(self):
        # Arrange
        initialization_contract = contract()
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory) / "external"
            project = external / "project"
            (project / ".codex").mkdir(parents=True)
            make_git_root(project)
            ledger = external / "ledger.json"
            ledger.write_text(json.dumps(valid_initialization_session(initialization_contract)), encoding="utf-8")
            environment = {**os.environ, "PYTHONPATH": ""}

            # Act
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(BUNDLED_START_VALIDATOR),
                    "--preflight",
                    str(ledger),
                    "--project-root",
                    str(project),
                ],
                cwd=external,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            # Assert
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("ok", json.loads(result.stdout)["status"])
            (project / ".codex/studio.toml").write_text(
                initialization_contract["default_authority_toml"], encoding="utf-8"
            )
            audit = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(BUNDLED_START_VALIDATOR),
                    "--audit",
                    str(ledger),
                    "--project-root",
                    str(project),
                ],
                cwd=external,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, audit.returncode, audit.stderr)
            self.assertEqual("ok", json.loads(audit.stdout)["status"])

    def test_start_initialization_rejects_reviewed_bypass_sessions(self):
        # Arrange
        initialization_contract = contract()
        valid = valid_initialization_session(initialization_contract)
        bypasses = {
            "unlisted post-approval write": {
                **valid,
                "events": [
                    *valid["events"],
                    {
                        "type": "write",
                        "path": "production/stage.txt",
                        "kind": "create",
                        "material_change": "write an unlisted stage",
                    },
                ],
            },
            "exact forbidden directory": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": ".agents/skills",
                                "kind": "directory-create",
                                "material_change": "create a forbidden directory",
                                "form": "atomic",
                                "expanded_paths": [".agents/skills"],
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "repository escape": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "../outside.txt",
                                "kind": "create",
                                "material_change": "escape the project",
                                "form": "atomic",
                                "expanded_paths": ["../outside.txt"],
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "absolute target": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "/tmp/outside.txt",
                                "kind": "create",
                                "material_change": "escape with an absolute path",
                                "form": "atomic",
                                "expanded_paths": ["/tmp/outside.txt"],
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "path alias": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "./.codex/studio.toml",
                                "kind": "create",
                                "material_change": "use a path alias",
                                "form": "atomic",
                                "expanded_paths": ["./.codex/studio.toml"],
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "speculative directory": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "production",
                                "kind": "directory-create",
                                "material_change": "create an empty directory",
                                "form": "atomic",
                                "expanded_paths": ["production"],
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "hidden bulk action": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": ".codex/studio.toml",
                                "kind": "create",
                                "material_change": "write the selected authority artifacts",
                                "form": "atomic",
                                "expanded_paths": [
                                    ".codex/studio.toml",
                                    "production/stage.txt",
                                ],
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "initialized repository write": {
                "authority_state": "initialized",
                "events": [{"type": "write", "path": "production/stage.txt"}],
            },
        }

        # Act / Assert
        for name, session in bypasses.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    validate_session(session)

    def test_start_initialization_contract_loads_complete_default_authority(self):
        # Arrange
        initialization_contract = contract()

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            control = project / ".codex"
            control.mkdir(parents=True)

            # Act
            (control / "studio.toml").write_text(
                initialization_contract["default_authority_toml"], encoding="utf-8"
            )
            config = load_studio_config(project)

            # Assert
            self.assertEqual("unconfigured", config.engine)
            self.assertEqual("", config.engine_version)
            self.assertEqual("", config.language)
            self.assertEqual("phase-gated", config.review_mode)
            self.assertEqual("none", config.active_engine_pack)
            self.assertEqual("balanced", config.model_policy)

    def test_start_initialization_contract_executes_missing_authority_read_only_until_approval(self):
        # Arrange
        initialization_contract = contract()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            for path in (
                ".codex",
                "src",
                "design/gdd",
                "prototypes",
                "production/sprints",
                "production/milestones",
            ):
                (project / path).mkdir(parents=True, exist_ok=True)
            make_git_root(project)
            before = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))

            # Act
            state = detect_project_state(project)
            validate_session(valid_initialization_session(initialization_contract))
            after = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))

            # Assert
            self.assertEqual("missing", state["authority_state"])
            self.assertTrue(state["fresh"])
            self.assertEqual(before, after)

    def test_start_initialization_contract_rejects_invalid_sessions(self):
        # Arrange
        initialization_contract = contract()
        valid = valid_initialization_session(initialization_contract)
        eleven_actions = [
            {
                "path": f"production/path-{index}.txt",
                "kind": "create",
                "material_change": "create one explicit file",
            }
            for index in range(11)
        ]
        cases = {
            "pre-approval write": {
                **valid,
                "events": [
                    {"type": "detect"},
                    {"type": "write", "path": ".codex/studio.toml"},
                    *valid["events"][1:],
                ],
            },
            "zero changesets": {
                **valid,
                "events": [{"type": "detect"}, {"type": "approval"}],
            },
            "multiple changesets": {
                **valid,
                "events": [
                    *valid["events"][:3],
                    valid["events"][2],
                    *valid["events"][3:],
                ],
            },
            "eleven paths": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": eleven_actions,
                    },
                    *valid["events"][3:],
                ],
            },
            "glob action": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "production/*.txt",
                                "kind": "create",
                                "material_change": "bulk glob",
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "recursive action": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "production/recurse",
                                "kind": "recursive",
                                "material_change": "recursive mutation",
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "tree action": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "production/tree",
                                "kind": "tree-copy",
                                "material_change": "copy a tree",
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "bulk action": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "production/bulk",
                                "kind": "bulk",
                                "material_change": "bulk mutation",
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "global target": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": ".agents/skills/start/SKILL.md",
                                "kind": "create",
                                "material_change": "install a global skill",
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "unselected engine reference": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "docs/engine-reference/unreal/VERSION.md",
                                "kind": "create",
                                "material_change": "initialize an unselected reference",
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "incomplete authority": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "authority_toml": 'engine = "unconfigured"\n',
                    },
                    *valid["events"][3:],
                ],
            },
            "invalid authority": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "authority_toml": (
                            'engine = "unconfigured"\n'
                            'engine_version = ""\n'
                            'language = ""\n'
                            'review_mode = "phase-gated"\n'
                            'active_engine_pack = "none"\n'
                            'model_policy = ""\n'
                        ),
                    },
                    *valid["events"][3:],
                ],
            },
        }

        # Act / Assert
        for name, session in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    validate_session(session)

    def test_start_initialization_contract_preserves_initialized_repositories(self):
        # Arrange
        initialization_contract = contract()

        # Act / Assert
        validate_session(
            {
                "authority_state": "initialized",
                "events": [{"type": "detect"}],
            }
        )
        with self.assertRaises(ValueError):
            validate_session(
                {
                    "authority_state": "initialized",
                    "events": valid_initialization_session(initialization_contract)["events"],
                }
            )

    def test_start_initialization_reconciles_missing_duplicate_and_reordered_actions(self):
        # Arrange
        initialization_contract = contract()
        valid = valid_initialization_session(initialization_contract)
        action = valid["events"][2]["actions"][0]
        stage_action = {
            "path": "production/stage.txt",
            "kind": "create",
            "material_change": "write the selected initial stage",
            "form": "atomic",
            "expanded_paths": ["production/stage.txt"],
        }
        stage_write = {
            "type": "write",
            "path": stage_action["path"],
            "kind": stage_action["kind"],
            "material_change": stage_action["material_change"],
        }
        cases = {
            "missing action": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {**valid["events"][2], "actions": []},
                    *valid["events"][3:],
                ],
            },
            "duplicated action": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {**valid["events"][2], "actions": [action, action]},
                    *valid["events"][3:],
                ],
            },
            "reordered writes": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {**valid["events"][2], "actions": [action, stage_action]},
                    *valid["events"][3:4],
                    stage_write,
                    valid["events"][4],
                ],
            },
        }

        # Act / Assert
        for name, session in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    validate_session(session)

    def test_start_initialization_contract_binds_production_docs_and_rejects_mutation(self):
        # Arrange
        framework = ROOT / "Codex Studio Testing Framework/skills/utility/start.md"
        runtime_text = START.read_text(encoding="utf-8")
        framework_text = framework.read_text(encoding="utf-8")
        mutated_contract = contract()
        mutated_contract["first_run"]["max_path_mutations"] = 11

        # Act / Assert
        validate_contract(contract())
        validate_documentation(runtime_text, framework_text)
        self.assertIn(contract_fingerprint(), runtime_text)
        self.assertIn(contract_summary(), framework_text)
        with self.assertRaises(ValueError):
            validate_contract(mutated_contract)
        with self.assertRaises(ValueError):
            validate_documentation(
                runtime_text.replace("at most 10 unique path mutations", "at most 11 unique path mutations"),
                framework_text,
            )

    def test_start_initialized_repository_requires_separate_approved_write(self):
        # Arrange
        action = {
            "path": "production/stage.txt",
            "kind": "create",
            "material_change": "write the selected initial stage",
            "form": "atomic",
            "expanded_paths": ["production/stage.txt"],
            "sha256": hashlib.sha256(b"Concept\n").hexdigest(),
        }
        session = {
            "authority_state": "initialized",
            "events": [
                {"type": "detect"},
                {"type": "stage-proposal", "actions": [action]},
                {"type": "stage-approval"},
                {
                    "type": "write",
                    "path": action["path"],
                    "kind": action["kind"],
                    "material_change": action["material_change"],
                    "sha256": action["sha256"],
                },
            ],
        }

        # Act / Assert
        validate_session(session)

    def test_start_initialized_repository_allows_missing_production_parent_before_stage(self):
        # Arrange
        stage_digest = hashlib.sha256(b"Concept\n").hexdigest()
        parent = {
            "path": "production",
            "kind": "directory-create",
            "material_change": "create the missing stage parent",
            "form": "atomic",
            "expanded_paths": ["production"],
            "required_by": "production/stage.txt",
            "sha256": None,
        }
        stage = {
            "path": "production/stage.txt",
            "kind": "create",
            "material_change": "write the selected initial stage",
            "form": "atomic",
            "expanded_paths": ["production/stage.txt"],
            "sha256": stage_digest,
        }
        session = {
            "authority_state": "initialized",
            "events": [
                {"type": "detect"},
                {"type": "stage-proposal", "actions": [parent, stage]},
                {"type": "stage-approval"},
                {"type": "write", "path": parent["path"], "kind": parent["kind"], "material_change": parent["material_change"], "sha256": None},
                {"type": "write", "path": stage["path"], "kind": stage["kind"], "material_change": stage["material_change"], "sha256": stage["sha256"]},
            ],
        }

        # Act / Assert
        validate_session(session, directories={".codex": True, "production": False})

    def test_clean_template_heuristic_ignores_instruction_only_files(self):
        state = detect_project_state(ROOT)
        self.assertEqual("unconfigured", state["engine"])
        self.assertEqual([], state["source_files"])
        self.assertEqual([], state["design_docs"])
        self.assertEqual([], state["prototypes"])
        self.assertEqual([], state["production_files"])
        self.assertTrue(state["fresh"])
        text = START.read_text(encoding="utf-8")
        self.assertIn("exclude every nested `AGENTS.md`", text)
        self.assertIn("instruction-only files such as `.gitkeep`", text)

    def test_start_supports_plugin_native_uninitialized_repository(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("$codex-game-studios:start", text)
        self.assertIn("Initialization changeset", text)
        self.assertIn("at most 10 unique path mutations", text)
        self.assertIn("No writes precede approval", text)
        self.assertIn("Forbidden roots and every descendant", text)
        self.assertIn("tools.codex_studio.start_initialization", text)
        self.assertIn('engine = "unconfigured"', text)
        self.assertIn('engine_version = ""', text)
        self.assertIn('language = ""', text)
        self.assertIn('review_mode = "phase-gated"', text)
        self.assertIn('active_engine_pack = "none"', text)
        self.assertIn('model_policy = "balanced"', text)
        self.assertIn("continue read-only project detection", text)
        self.assertIn(
            "Initialization changeset replaces the separate persistent", text
        )
        self.assertNotIn("do not continue to onboarding", text)

    def test_start_is_native_and_detects_unconfigured_fresh_projects(self):
        text = START.read_text(encoding="utf-8")
        self.assertEqual([], validate_skill(START))
        self.assertIn(".codex/studio.toml", text)
        self.assertIn('engine = "unconfigured"', text)
        self.assertIn("No concept, source, prototype, design, or production artifacts", text)
        self.assertIn("route to `$brainstorm`", text)

    def test_start_questions_fit_native_schema(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("Ask one decision per turn", text)
        self.assertIn("2-3 mutually exclusive options", text)
        self.assertIn("New or exploratory", text)
        self.assertIn("Defined or existing", text)
        self.assertNotIn("these exact options", text)
        self.assertNotIn("- `D) Existing work`", text)

    def test_start_uses_actual_project_state_and_orders_persistent_decisions(self):
        text = START.read_text(encoding="utf-8")
        ordered_contract = (
            "Read `.codex/studio.toml`",
            "Check for `design/gdd/game-concept.md`",
            "repository file search for source files in `src/`",
            "Check for subdirectories in `prototypes/`",
            "Check for files in `production/sprints/` or `production/milestones/`",
            "## Phase 2: Confirm the Detected Starting Point",
            "## Phase 3: Confirm the Workflow Path",
            "## Phase 4: Propose the Initial Stage Artifact",
            "## Phase 5: Select Review Depth",
            "## Phase 6: Approve the Studio Configuration Changeset",
            "## Phase 7: Confirm Before Proceeding",
        )
        positions = [text.index(marker) for marker in ordered_contract]
        self.assertEqual(sorted(positions), positions)
        self.assertIn("show the concrete evidence you found", text)
        self.assertIn("production/stage.txt", text)
        self.assertIn('review_mode = "phase-gated"', text)
        self.assertIn("exact `.codex/studio.toml` diff", text)
        self.assertIn("explicit approval", text)

    def test_start_never_creates_a_competing_review_mode_authority(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("`.codex/studio.toml` is the sole persistent review-mode authority", text)
        self.assertIn("Never create a separate review-mode file", text)
        self.assertNotIn("production/review-mode.txt", text)
        self.assertNotIn("production/session-state/review-mode.txt", text)

    def test_all_runtime_skills_use_only_studio_toml_for_persistent_review_mode(self):
        failures = []
        for path in sorted((ROOT / ".agents/skills").glob("*/SKILL.md")):
            text = path.read_text(encoding="utf-8")
            for legacy in (
                "production/review-mode.txt",
                "production/session-state/review-mode.txt",
            ):
                if legacy in text:
                    failures.append(f"{path.relative_to(ROOT)}: {legacy}")
        self.assertEqual([], failures)

    def test_phase_gated_mode_keeps_mandatory_director_gates(self):
        gates = (ROOT / ".codex/docs/director-gates.md").read_text(encoding="utf-8")
        self.assertIn("lean optional-review depth", gates)
        self.assertIn("mandatory director gates still run", gates)
        self.assertIn('review_mode = "phase-gated"', gates)

    def test_returning_engine_and_concept_skip_onboarding(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("engine configured, concept exists", text)
        self.assertIn("Skip onboarding entirely", text)


if __name__ == "__main__":
    unittest.main()
