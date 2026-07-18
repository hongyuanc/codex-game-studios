from pathlib import Path
import importlib
import importlib.util
import shutil
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_GOVERNED_SKILLS = frozenset(
    """architecture-decision architecture-review art-bible asset-spec brainstorm
bug-report bug-triage changelog code-review create-architecture
create-control-manifest create-epics create-stories day-one-patch design-review
design-system dev-story estimate gate-check hotfix launch-checklist localize
map-systems milestone-review onboard patch-notes playtest-report
propagate-design-change prototype qa-plan regression-suite release-checklist
retrospective reverse-document review-all-gdds security-audit skill-improve
skill-test smoke-check soak-test sprint-plan sprint-status story-done
story-readiness team-audio team-combat team-level team-live-ops team-narrative
team-polish team-qa team-release team-ui test-evidence-review test-flakiness
test-helpers test-setup ux-design vertical-slice""".split()
)
MARKER = "<!-- codex-studio-delegation: governed -->"
PREFLIGHT = (
    "Resolve every role through `../../../.codex/docs/plugin-agent-delegation.md`;\n"
    "do not require a repository-local `.codex/agents/` or `.codex/agent-packs/` tree."
)
RESOLVER_INVOCATION = (
    "Before default delegation, run `python3 "
    "../../../tools/codex_studio/agent_delegation.py resolve --project-root "
    "<project-root> --role <role>` and use only its returned role contract."
)


def _delegation_module(test: unittest.TestCase):
    spec = importlib.util.find_spec("tools.codex_studio.agent_delegation")
    test.assertIsNotNone(spec, "production agent delegation interface is missing")
    return importlib.import_module("tools.codex_studio.agent_delegation")


def _write_studio_config(project: Path, engine: str = "unconfigured") -> None:
    active_pack = "none" if engine == "unconfigured" else engine
    version, language = ("", "") if engine == "unconfigured" else ("4.6", "gdscript")
    (project / ".codex").mkdir(parents=True, exist_ok=True)
    (project / ".codex/studio.toml").write_text(
        f'engine = "{engine}"\n'
        f'engine_version = "{version}"\n'
        f'language = "{language}"\n'
        'review_mode = "phase-gated"\n'
        f'active_engine_pack = "{active_pack}"\n'
        'model_policy = "balanced"\n',
        encoding="utf-8",
    )


class DelegationGovernanceTests(unittest.TestCase):
    def test_authoritative_inventory_matches_independently_derived_union(self):
        # Arrange / Act
        delegation = _delegation_module(self)

        # Assert
        self.assertEqual(EXPECTED_GOVERNED_SKILLS, delegation.DELEGATING_SKILL_NAMES)
        self.assertEqual(59, len(delegation.DELEGATING_SKILL_NAMES))

    def test_every_governed_skill_has_exact_marker_preflight_and_resolver(self):
        # Arrange / Act / Assert
        for name in sorted(EXPECTED_GOVERNED_SKILLS):
            text = (ROOT / ".agents/skills" / name / "SKILL.md").read_text(
                encoding="utf-8"
            )
            with self.subTest(skill=name):
                self.assertEqual(1, text.count(MARKER))
                self.assertEqual(1, text.count(PREFLIGHT))
                self.assertEqual(1, text.count(RESOLVER_INVOCATION))

    def test_actual_instruction_detection_handles_case_inflection_and_plural(self):
        delegation = _delegation_module(self)
        cases = (
            "Delegate to `qa-tester` for review.",
            "This workflow Spawns the named specialist.",
            "The parent is delegating a bounded task to an agent.",
            "Use Codex custom agents by role and profile when delegation is useful.",
            "Issue all custom-agent delegations together.",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertTrue(delegation.contains_delegation_instruction(text))

    def test_detection_ignores_fenced_examples_and_html_comments(self):
        delegation = _delegation_module(self)
        text = """
## Example

```markdown
Delegate to `qa-tester` and spawn custom agents.
```

<!-- Use Codex custom agents by role. -->
Ordinary analysis remains single-agent.
"""
        self.assertFalse(delegation.contains_delegation_instruction(text))

    def test_governance_rejects_actual_addition_and_removal(self):
        delegation = _delegation_module(self)
        ungoverned = "---\nname: adopt\ndescription: Use when adopting.\n---\n\n# Adopt\n"
        governed = (
            "---\nname: code-review\ndescription: Use when reviewing.\n---\n\n"
            f"{MARKER}\n{PREFLIGHT}\n{RESOLVER_INVOCATION}\n\n"
            "Delegate to `qa-tester` for bounded review.\n"
        )

        added = delegation.validate_delegation_skill(
            "adopt", ungoverned + "\nDelegate to `qa-tester`.\n"
        )
        removed = delegation.validate_delegation_skill(
            "code-review", governed.replace("Delegate to `qa-tester` for bounded review.\n", "")
        )

        self.assertTrue(any("ungoverned delegation instruction" in issue for issue in added))
        self.assertTrue(any("no delegation instruction" in issue for issue in removed))

    def test_governance_rejects_marker_and_preflight_mismatch(self):
        delegation = _delegation_module(self)
        base = (
            "---\nname: code-review\ndescription: Use when reviewing.\n---\n\n"
            f"{MARKER}\n{PREFLIGHT}\n{RESOLVER_INVOCATION}\n\n"
            "Delegate to `qa-tester`.\n"
        )
        mutations = {
            "missing marker": base.replace(f"{MARKER}\n", ""),
            "duplicate marker": base.replace(MARKER, f"{MARKER}\n{MARKER}"),
            "missing preflight": base.replace(f"{PREFLIGHT}\n", ""),
            "duplicate preflight": base.replace(PREFLIGHT, f"{PREFLIGHT}\n{PREFLIGHT}"),
            "missing resolver": base.replace(f"{RESOLVER_INVOCATION}\n", ""),
        }
        for label, text in mutations.items():
            with self.subTest(label=label):
                self.assertTrue(delegation.validate_delegation_skill("code-review", text))


class RoleResolverTests(unittest.TestCase):
    def test_studio_config_fixture_is_strictly_valid(self):
        # Arrange
        delegation = _delegation_module(self)
        cases = (
            ("unconfigured", "", "", "none"),
            ("godot", "4.6", "gdscript", "godot"),
        )

        # Act / Assert
        for engine, version, language, active_pack in cases:
            with self.subTest(engine=engine), tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "project"
                project.mkdir()
                _write_studio_config(project, engine)
                try:
                    config = delegation.load_studio_config(project)
                except ValueError as error:
                    self.fail(f"studio config fixture must be strictly valid: {error}")
                self.assertEqual((engine, version, language, active_pack), (
                    config.engine,
                    config.engine_version,
                    config.language,
                    config.active_engine_pack,
                ))

    def test_core_and_selected_engine_roles_resolve_from_bundle(self):
        delegation = _delegation_module(self)
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            _write_studio_config(project, "godot")

            core = delegation.resolve_role(ROOT, project, "qa-tester")
            engine = delegation.resolve_role(ROOT, project, "godot-specialist")

        self.assertEqual("qa-tester", core.name)
        self.assertEqual("core", core.source_kind)
        self.assertEqual("godot-specialist", engine.name)
        self.assertEqual("godot", engine.source_kind)
        self.assertTrue(str(core.path).startswith(str(ROOT / ".codex/agents")))
        self.assertTrue(str(engine.path).startswith(str(ROOT / ".codex/agent-packs/godot")))

    def test_resolver_rejects_unsafe_unknown_and_cross_pack_roles(self):
        delegation = _delegation_module(self)
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            _write_studio_config(project, "godot")
            cases = (
                ("../qa-tester", "safe role slug"),
                ("qa_tester", "safe role slug"),
                ("unknown-role", "unknown role"),
                ("unity-specialist", "inactive engine pack"),
            )
            for role, message in cases:
                with self.subTest(role=role), self.assertRaisesRegex(ValueError, message):
                    delegation.resolve_role(ROOT, project, role)

    def test_resolver_ignores_project_local_role_tree(self):
        delegation = _delegation_module(self)
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            _write_studio_config(project)
            (project / ".codex/agents").mkdir()
            (project / ".codex/agents/qa-tester.toml").write_text(
                'name = "attacker"\n', encoding="utf-8"
            )

            contract = delegation.resolve_role(ROOT, project, "qa-tester")

        self.assertEqual("qa-tester", contract.name)
        self.assertNotIn(str(project), str(contract.path))

    def test_resolver_rejects_missing_malformed_nonregular_symlink_and_name_mismatch(self):
        delegation = _delegation_module(self)
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "studio"
            shutil.copytree(ROOT / ".codex", fixture / ".codex")
            project = Path(directory) / "project"
            project.mkdir()
            _write_studio_config(project)
            target = fixture / ".codex/agents/qa-tester.toml"
            original = target.read_text(encoding="utf-8")
            outside = Path(directory) / "outside.toml"
            outside.write_text(original, encoding="utf-8")

            mutations = {
                "missing": lambda: target.unlink(),
                "malformed": lambda: target.write_text("name = [", encoding="utf-8"),
                "name mismatch": lambda: target.write_text(
                    original.replace('name = "qa-tester"', 'name = "qa-lead"', 1),
                    encoding="utf-8",
                ),
                "non-regular": lambda: (target.unlink(), target.mkdir()),
                "symlink": lambda: (target.unlink(), target.symlink_to(outside)),
            }
            for label, mutate in mutations.items():
                with self.subTest(label=label):
                    if target.exists() or target.is_symlink():
                        if target.is_dir() and not target.is_symlink():
                            target.rmdir()
                        else:
                            target.unlink()
                    target.write_text(original, encoding="utf-8")
                    mutate()
                    with self.assertRaises(ValueError):
                        delegation.resolve_role(fixture, project, "qa-tester")

    def test_resolver_rejects_ambiguous_core_and_active_pack_candidate(self):
        delegation = _delegation_module(self)
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "studio"
            shutil.copytree(ROOT / ".codex", fixture / ".codex")
            project = Path(directory) / "project"
            project.mkdir()
            _write_studio_config(project, "godot")
            duplicate = fixture / ".codex/agent-packs/godot/qa-tester.toml"
            shutil.copy2(fixture / ".codex/agents/qa-tester.toml", duplicate)

            with self.assertRaisesRegex(ValueError, "ambiguous"):
                delegation.resolve_role(fixture, project, "qa-tester")

    def test_resolver_detects_ancestor_replacement_after_validation(self):
        delegation = _delegation_module(self)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            fixture = base / "studio"
            shutil.copytree(ROOT / ".codex", fixture / ".codex")
            project = base / "project"
            project.mkdir()
            _write_studio_config(project)
            agents = fixture / ".codex/agents"
            retained = fixture / ".codex/agents-retained"
            outside = base / "outside-agents"
            outside.mkdir()
            outside_contract = (
                agents / "qa-tester.toml"
            ).read_text(encoding="utf-8").replace(
                "Create detailed test cases, bug reports, and test checklists.",
                "OUTSIDE CONTROLLED INSTRUCTIONS",
                1,
            )
            (outside / "qa-tester.toml").write_text(
                outside_contract, encoding="utf-8"
            )
            real_open = delegation.os.open
            real_metadata = delegation._safe_metadata
            replaced = False

            def replace_before_contract_metadata(path, label, *, missing_ok=False):
                nonlocal replaced
                if label == "role contract" and not replaced:
                    replaced = True
                    agents.rename(retained)
                    agents.symlink_to(outside, target_is_directory=True)
                return real_metadata(path, label, missing_ok=missing_ok)

            def replace_before_final(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal replaced
                final_component = Path(path).name == "qa-tester.toml"
                if final_component and not replaced:
                    replaced = True
                    agents.rename(retained)
                    agents.symlink_to(outside, target_is_directory=True)
                if dir_fd is None:
                    return real_open(path, flags, mode)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with mock.patch.object(
                delegation,
                "_safe_metadata",
                side_effect=replace_before_contract_metadata,
            ), mock.patch.object(delegation.os, "open", side_effect=replace_before_final):
                with self.assertRaisesRegex(ValueError, "ancestor.*changed|identity"):
                    delegation.resolve_role(fixture, project, "qa-tester")

    def test_windows_resolver_pins_ancestor_identity_through_role_read(self):
        delegation = _delegation_module(self)

        class FakeWindowsApi:
            FILE_SHARE_READ = 0x1
            FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
            FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

            def __init__(self, contract):
                self.contract = contract
                self.calls = []
                self.closed = []
                self.handles = {}
                self.next_handle = 1
                self.replaced = False

            def open(self, path, *, flags, share):
                normalized = str(path).replace("/", "\\")
                handle = self.next_handle
                self.next_handle += 1
                name = normalized.rsplit("\\", 1)[-1]
                if name == "qa-tester.toml":
                    self.replaced = True
                identity = (1, 3)
                if name == ".codex":
                    identity = (1, 2)
                elif name == "agents":
                    identity = (1, 30 if self.replaced else 3)
                elif name == "qa-tester.toml":
                    identity = (1, 4)
                elif normalized.endswith("studio"):
                    identity = (1, 1)
                kind = "file" if name.endswith(".toml") else "directory"
                self.handles[handle] = (normalized, identity, kind)
                self.calls.append((normalized, flags, share, handle))
                return handle

            def info(self, handle):
                _, identity, kind = self.handles[handle]
                return types.SimpleNamespace(
                    identity=identity,
                    kind=kind,
                    reparse=False,
                    disk=True,
                    size=len(self.contract) if kind == "file" else 0,
                    write_time=1,
                )

            def final_path(self, handle):
                return self.handles[handle][0]

            def read(self, handle):
                return self.contract

            def close(self, handle):
                self.closed.append(handle)

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            _write_studio_config(project)
            raw = (ROOT / ".codex/agents/qa-tester.toml").read_bytes().replace(
                b"Create detailed test cases, bug reports, and test checklists.",
                b"OUTSIDE CONTROLLED INSTRUCTIONS",
                1,
            )
            api = FakeWindowsApi(raw)
            with mock.patch.object(
                delegation, "_is_windows", return_value=True, create=True
            ), mock.patch.object(
                delegation, "_windows_api_factory", return_value=api, create=True
            ):
                with self.assertRaisesRegex(ValueError, "ancestor.*changed|identity"):
                    delegation.resolve_role(
                        Path("C:/plugin/studio"), project, "qa-tester"
                    )

        self.assertTrue(api.calls)
        self.assertTrue(
            all(
                flags & api.FILE_FLAG_OPEN_REPARSE_POINT
                for _, flags, _, _ in api.calls
            )
        )
        self.assertEqual(
            {handle for *_, handle in api.calls}, set(api.closed)
        )


class DelegationRoutingTests(unittest.TestCase):
    def test_closed_route_table(self):
        delegation = _delegation_module(self)
        cases = (
            ("success", "not-attempted", True, ("native", "SUCCESS", None)),
            ("blocked", "not-attempted", True, ("native", "BLOCKED", None)),
            ("absent", "success", True, ("default", "SUCCESS", None)),
            ("unavailable", "success", True, ("default", "SUCCESS", None)),
            ("absent", "blocked", True, ("default", "BLOCKED", None)),
            ("absent", "absent", True, ("single-agent", "FALLBACK", "single-agent fallback")),
            ("unavailable", "unavailable", True, ("single-agent", "FALLBACK", "single-agent fallback")),
            ("absent", "absent", False, ("single-agent", "FALLBACK", "single-agent fallback")),
            ("absent", "unavailable", False, ("single-agent", "FALLBACK", "single-agent fallback")),
            ("unavailable", "absent", False, ("single-agent", "FALLBACK", "single-agent fallback")),
            ("unavailable", "unavailable", False, ("single-agent", "FALLBACK", "single-agent fallback")),
            ("absent", "not-attempted", False, ("approval-required", "BLOCKED", None)),
        )
        for native, default, model_supported, expected in cases:
            with self.subTest(native=native, default=default, model_supported=model_supported):
                decision = delegation.decide_route(
                    native_result=native,
                    default_result=default,
                    model_supported=model_supported,
                )
                self.assertEqual(expected, (decision.route, decision.status, decision.evidence_label))

    def test_closed_route_table_rejects_impossible_state_combinations(self):
        delegation = _delegation_module(self)
        cases = (
            ("success", "success", True),
            ("blocked", "absent", True),
            ("absent", "not-attempted", True),
            ("absent", "success", False),
            ("unavailable", "blocked", False),
        )
        for native, default, model_supported in cases:
            with self.subTest(
                native=native,
                default=default,
                model_supported=model_supported,
            ), self.assertRaisesRegex(ValueError, "impossible route state"):
                delegation.decide_route(
                    native_result=native,
                    default_result=default,
                    model_supported=model_supported,
                )

    def test_default_request_maps_model_fields_and_complete_bounded_prompt(self):
        delegation = _delegation_module(self)
        contract = delegation.RoleContract(
            name="qa-tester",
            description="QA role description",
            developer_instructions="Perform the QA checklist.",
            model="gpt-5.6-luna",
            model_reasoning_effort="medium",
            source_kind="core",
            path=ROOT / ".codex/agents/qa-tester.toml",
        )
        task = delegation.BoundedTask(
            objective="Review one change",
            owned_paths=("tests/example.py",),
            inputs=("approved diff",),
            acceptance_criteria=("report exact failures",),
            required_evidence=("test output",),
            prohibited_actions=("do not edit", "do not delegate"),
        )

        request = delegation.build_default_agent_request(
            contract,
            task,
            supported_models={"gpt-5.6-luna"},
            supported_reasoning_efforts={"medium"},
        )

        self.assertEqual("default", request["agent_type"])
        self.assertEqual("none", request["fork_turns"])
        self.assertEqual("gpt-5.6-luna", request["model"])
        self.assertEqual("medium", request["reasoning_effort"])
        for token in (
            "qa-tester",
            "QA role description",
            "Perform the QA checklist.",
            "Model: gpt-5.6-luna",
            "Reasoning effort: medium",
            "Review one change",
            "tests/example.py",
            "approved diff",
            "report exact failures",
            "test output",
            "do not edit",
            "direct child",
            "Parent synthesis",
        ):
            with self.subTest(token=token):
                self.assertIn(token, request["message"])

    def test_unsupported_model_blocks_for_approval_without_fallback(self):
        delegation = _delegation_module(self)
        contract = delegation.RoleContract(
            name="producer",
            description="Producer",
            developer_instructions="Coordinate.",
            model="gpt-5.6",
            model_reasoning_effort="high",
            source_kind="core",
            path=ROOT / ".codex/agents/producer.toml",
        )
        task = delegation.BoundedTask(
            objective="Plan",
            owned_paths=(),
            inputs=("brief",),
            acceptance_criteria=("bounded plan",),
            required_evidence=("plan",),
            prohibited_actions=("do not edit",),
        )

        with self.assertRaisesRegex(delegation.ModelApprovalRequired, "approval"):
            delegation.build_default_agent_request(
                contract,
                task,
                supported_models={"gpt-5.6-terra"},
                supported_reasoning_efforts={"high"},
            )

        decision = delegation.decide_route(
            native_result="absent", default_result="not-attempted", model_supported=False
        )
        self.assertEqual("approval-required", decision.route)
        self.assertIsNone(decision.evidence_label)


if __name__ == "__main__":
    unittest.main()
