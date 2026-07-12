from pathlib import Path
import json
import re
import tomllib
import unittest

from tools.codex_studio.validate import validate_skill


ROOT = Path(__file__).resolve().parents[2]
NEW = ROOT / "Codex Studio Testing Framework"
OLD = ROOT / "CCGS Skill Testing Framework"


def catalog_names(text: str, section: str) -> set[str]:
    block = text.split(f"{section}:\n", 1)[1]
    if section == "skills":
        block = block.split("\nagents:\n", 1)[0]
    return set(re.findall(r"^  - name: ([a-z0-9-]+)$", block, re.MULTILINE))


class TestingFrameworkTests(unittest.TestCase):
    def test_catalog_and_native_guidance_exist(self):
        self.assertTrue((NEW / "catalog.yaml").is_file())
        self.assertTrue((NEW / "README.md").is_file())
        self.assertTrue((NEW / "AGENTS.md").is_file())

    def test_migrated_tree_has_durable_source_parity(self):
        evidence = json.loads(
            (ROOT / "production/migration/testing-framework-parity.json").read_text(encoding="utf-8")  # enforcement-literal
        )
        sources = {entry["source"] for entry in evidence["entries"]}
        for directory in ("agents", "skills", "templates"):
            old_files = {
                Path(source).relative_to(directory)
                for source in sources
                if source.startswith(f"{directory}/")
            }
            new_files = {
                path.relative_to(NEW / directory)
                for path in (NEW / directory).rglob("*")
                if path.is_file()
            }
            expected_additions = (
                {Path("utility/vertical-slice.md")} if directory == "skills" else set()
            )
            self.assertEqual(old_files | expected_additions, new_files)

    def test_catalog_covers_runtime_inventory_exactly(self):
        text = (NEW / "catalog.yaml").read_text(encoding="utf-8")
        runtime_skills = {
            path.parent.name for path in (ROOT / ".agents/skills").glob("*/SKILL.md")
        }
        runtime_agents = set()
        for path in [
            *sorted((ROOT / ".codex/agents").glob("*.toml")),
            *sorted((ROOT / ".codex/agent-packs").glob("*/*.toml")),
        ]:
            match = re.search(r'^name = "([a-z0-9-]+)"$', path.read_text(encoding="utf-8"), re.MULTILINE)
            self.assertIsNotNone(match, path)
            runtime_agents.add(match.group(1))
        self.assertEqual(runtime_skills, catalog_names(text, "skills"))
        self.assertEqual(runtime_agents, catalog_names(text, "agents"))
        self.assertEqual(73, len(runtime_skills))
        self.assertEqual(49, len(runtime_agents))

    def test_framework_is_codex_native(self):
        # enforcement-literal-start
        forbidden = (
            "Claude Code", "AskUserQuestion", "Task tool", "subagent_type",
            "Task call", "Task invocation", "model: opus", "model: sonnet",
            "model: haiku", "claude-opus", "claude-sonnet", "claude-haiku",
            "Opus model", "Sonnet model", "Haiku model", "Opus", "Sonnet",
            "Haiku", "CLAUDE.md", "parallel Task protocol", ".claude/",
            "allowed-tools", "argument-hint", "user-invocable",
            "May I apply the proposed changeset", "May I ",
        )
        # enforcement-literal-end
        failures = []
        for path in NEW.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                for token in forbidden:
                    if token in text:
                        failures.append(f"{path.relative_to(ROOT)}: {token}")
        self.assertEqual([], failures)

    def test_framework_uses_canonical_runtime_paths_and_phase_gated_authority(self):
        forbidden_patterns = {
            "legacy review-mode file": r"(?i)(?:production/(?:session-state/)?review-mode\.txt|review-mode\.txt)",
            "legacy session state": r"production/session-state/(?!active\.md)",
            "nonexistent skill-test tree": r"tests/skills(?:/|\b)",
            "nonexistent agent-test tree": r"tests/agents(?:/|\b)",
            "nonexistent status line": r"(?i)statusline|status line",
            "nonexistent sprint status": r"production/sprint-status\.yaml",
            "bare technical preferences": r"(?<!\.codex/docs/)technical-preferences\.md",
        }
        failures = []
        combined = []
        for path in NEW.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            combined.append(text)
            for label, pattern in forbidden_patterns.items():
                if re.search(pattern, text):
                    failures.append(f"{path.relative_to(ROOT)}: {label}")
        self.assertEqual([], failures)
        corpus = "\n".join(combined)
        self.assertIn("`.codex/studio.toml`", corpus)
        self.assertIn('`review_mode = "phase-gated"`', corpus)

    def test_all_agent_specs_match_their_runtime_toml_contract(self):
        runtime = {}
        for path in [
            *sorted((ROOT / ".codex/agents").glob("*.toml")),
            *sorted((ROOT / ".codex/agent-packs").glob("*/*.toml")),
        ]:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            runtime[data["name"]] = (path.relative_to(ROOT), data)

        specs = {path.stem: path for path in (NEW / "agents").rglob("*.md")}
        self.assertEqual(set(runtime), set(specs))
        self.assertEqual(49, len(specs))

        labels = {
            "gpt-5.6": "Sol",
            "gpt-5.6-terra": "Terra",
            "gpt-5.6-luna": "Luna",
        }
        required_keys = {
            "name", "description", "model", "model_reasoning_effort",
            "developer_instructions",
        }
        for name, spec_path in specs.items():
            runtime_path, data = runtime[name]
            text = spec_path.read_text(encoding="utf-8")
            self.assertEqual(required_keys, set(data), runtime_path)
            self.assertIn(f"Runtime profile: `{runtime_path}`", text, spec_path)
            self.assertIn(
                "Required TOML keys: `name`, `description`, `model`, "
                "`model_reasoning_effort`, `developer_instructions`",
                text,
                spec_path,
            )
            self.assertIn(
                f"Model route: **{labels[data['model']]}** (`{data['model']}`)",
                text,
                spec_path,
            )
            self.assertIn(
                f"Reasoning effort: `{data['model_reasoning_effort']}`",
                text,
                spec_path,
            )
            self.assertNotRegex(text, r"\.codex/(?:agents|agent-packs)/[^`\s]+\.md")
            self.assertNotRegex(text, r"(?i)Verified.*frontmatter|runtime capabilities.*list")

    def test_all_skill_specs_match_runtime_discovery_and_interaction_contracts(self):
        runtime = {
            path.parent.name: path
            for path in (ROOT / ".agents/skills").glob("*/SKILL.md")
        }
        specs = {path.stem: path for path in (NEW / "skills").rglob("*.md")}
        self.assertEqual(set(runtime), set(specs))
        self.assertEqual(73, len(specs))

        for name, spec_path in specs.items():
            skill_text = runtime[name].read_text(encoding="utf-8")
            frontmatter = skill_text.split("---", 2)[1]
            runtime_name = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
            description = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
            self.assertIsNotNone(runtime_name, runtime[name])
            self.assertIsNotNone(description, runtime[name])

            text = spec_path.read_text(encoding="utf-8")
            self.assertIn(f"# Skill Test Spec: ${name}", text, spec_path)
            self.assertIn(f"Runtime skill: `.agents/skills/{name}/SKILL.md`", text, spec_path)
            self.assertIn(f"Runtime name: `{runtime_name.group(1).strip()}`", text, spec_path)
            self.assertIn(
                f"Runtime trigger description: `{description.group(1).strip()}`",
                text,
                spec_path,
            )
            self.assertIn(f"Native invocation: `${name}`", text, spec_path)
            self.assertIn("1–3 questions", text, spec_path)
            self.assertIn("2–3 options", text, spec_path)
            self.assertIn("one decision per turn", text, spec_path)
            self.assertIn("maximum delegation depth is 1", text, spec_path)
            self.assertIn("parent agent synthesizes", text, spec_path)
            self.assertNotIn("Has required frontmatter fields", text, spec_path)
            for case in range(1, 6):
                self.assertRegex(text, rf"(?m)^### Case {case}:", spec_path)

    def test_all_runtime_skills_satisfy_documented_static_discovery_contract(self):
        skill_test = (NEW / "skills/utility/skill-test.md").read_text(encoding="utf-8")
        self.assertIn(
            "exactly `name` and `description`; `name` equals the skill directory",
            skill_test,
        )
        self.assertIn("description is nonblank", skill_test)
        self.assertIn("does not require a literal `Use when` prefix", skill_test)
        self.assertIn("does not evaluate whether prose is trigger-oriented", skill_test)

        failures = []
        for path in sorted((ROOT / ".agents/skills").glob("*/SKILL.md")):
            for issue in validate_skill(path):
                failures.append(f"{path}: validator: {issue.message}")
            parts = path.read_text(encoding="utf-8").split("---", 2)
            if len(parts) != 3:
                failures.append(f"{path}: missing frontmatter")
                continue
            fields = {}
            for line in parts[1].splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    fields[key.strip()] = value.strip().strip('"')
            if set(fields) != {"name", "description"}:
                failures.append(f"{path}: fields={sorted(fields)}")
            if fields.get("name") != path.parent.name:
                failures.append(f"{path}: name does not match directory")
            if not fields.get("description", "").strip():
                failures.append(f"{path}: blank description")
        self.assertEqual([], failures)

    def test_start_spec_matches_runtime_project_state_routing(self):
        text = (NEW / "skills/utility/start.md").read_text(encoding="utf-8")
        runtime = (ROOT / ".agents/skills/start/SKILL.md").read_text(encoding="utf-8")
        required = (
            "`.codex/studio.toml`",
            '`engine = "unconfigured"`',
            "`design/gdd/game-concept.md`",
            "`src/`",
            "`prototypes/`",
            "`design/gdd/`",
            "`production/sprints/`",
            "`production/milestones/`",
            "`production/stage.txt`",
            '"Which broad starting point best describes this project?"',
            "New or exploratory",
            "Defined or existing",
            "No idea yet (Path A)",
            "Vague idea (Path B)",
            "Clear concept (Path C)",
            "Existing work (Path D)",
            "Wait for the first answer before asking the path follow-up",
            "Full",
            "Phase-gated (recommended)",
            "Solo",
            '`review_mode = "full"`',
            '`review_mode = "phase-gated"`',
            '`review_mode = "solo"`',
            "one complete proposed changeset",
            "before any write",
        )
        for token in required:
            self.assertIn(token, text)
        shared_runtime_contract = (
            "`.codex/studio.toml`",
            '`engine = "unconfigured"`',
            "`design/gdd/game-concept.md`",
            "`src/`",
            "`prototypes/`",
            "`design/gdd/`",
            "`production/sprints/`",
            "`production/milestones/`",
            "`production/stage.txt`",
            '"Which broad starting point best describes this project?"',
            "New or exploratory",
            "Defined or existing",
            "No idea yet (Path A)",
            "Vague idea (Path B)",
            "Clear concept (Path C)",
            "Existing work (Path D)",
            "Phase-gated (recommended)",
            '`review_mode = "full"`',
            '`review_mode = "phase-gated"`',
            '`review_mode = "solo"`',
        )
        for token in shared_runtime_contract:
            self.assertIn(token, runtime)
            self.assertIn(token, text)
        forbidden = (
            "project name", "3 engine options", "directory structure",
            "$setup-engine godot", "initial stubs", "restart from scratch",
        )
        for token in forbidden:
            self.assertNotIn(token, text)

        correspondence = (
            "exclude every nested `AGENTS.md`",
            "instruction-only files such as `.gitkeep`",
            "missing, unreadable, or invalid TOML",
            "Verdict: **BLOCKED**",
            "engine configured, concept exists",
            "Skip onboarding entirely",
        )
        for token in correspondence:
            self.assertIn(token, runtime)
            self.assertIn(token, text)

    def test_incremental_authoring_specs_match_runtime_section_approval(self):
        incremental = (
            "Draft and present one section, obtain approval, then write that approved "
            "section to the already identified artifact path"
        )
        boundary = (
            "No write occurs before that section approval, and no per-file reapproval "
            "is required inside the approved section"
        )
        runtime_markers = {
            "design-system": ("Approval  ->  Write", "After writing each section"),
            "art-bible": ("Write the approved section to file immediately",),
            "ux-design": ("Approval  ->  Write", "After writing each section"),
            "create-architecture": ("Incremental writing", "write each approved section immediately"),
        }
        failures = []
        for name, markers in runtime_markers.items():
            runtime = (ROOT / f".agents/skills/{name}/SKILL.md").read_text(encoding="utf-8")
            spec = next((NEW / "skills/authoring").glob(f"{name}.md")).read_text(encoding="utf-8")
            for marker in markers:
                if marker not in runtime:
                    failures.append(f"{name}: runtime marker missing: {marker}")
            if incremental not in spec:
                failures.append(f"{name}: framework lacks incremental section cycle")
            if boundary not in spec:
                failures.append(f"{name}: framework lacks section approval boundary")
            if "write once" in spec.lower() or "single write" in spec.lower():
                failures.append(f"{name}: framework incorrectly requires atomic write")

        full_changeset = (
            "The parent presents one complete proposed changeset containing every "
            "target path and material edit, then obtains approval before any write"
        )
        for path in sorted((NEW / "skills/authoring").glob("*.md")):
            if path.stem not in runtime_markers and full_changeset not in path.read_text(encoding="utf-8"):
                failures.append(f"{path.name}: full-changeset workflow lost its gate")
        self.assertEqual([], failures)

    def test_gate_specs_match_runtime_mode_contracts(self):
        rubric = (NEW / "quality-rubric.md").read_text(encoding="utf-8")
        gate_check = (NEW / "skills/gate/gate-check.md").read_text(encoding="utf-8")
        for text in (rubric, gate_check):
            self.assertIn(
                "mandatory `*-PHASE-GATE` directors run in `full`, `phase-gated`, and `solo`",
                text,
            )
            self.assertIn("only optional gates vary by review mode", text)

        pairs = {
            "create-control-manifest": (
                "Read and resolve `review_mode` from `.codex/studio.toml`",
                "TD-MANIFEST is optional: run it only in `full`; skip it in `phase-gated` and `solo`",
            ),
            "prototype": (
                "game pillars not yet defined",
                "CD-PLAYTEST is optional: run it only in `full` when game pillars exist",
            ),
            "playtest-report": (
                "CD-PLAYTEST skipped — Solo mode",
                "CD-PLAYTEST is optional: run it only in `full`",
            ),
            "propagate-design-change": (
                "TD-CHANGE-IMPACT is required in full, lean, and solo modes",
                "TD-CHANGE-IMPACT is mandatory in `full`, `phase-gated`, and `solo`",
            ),
        }
        locations = {
            "create-control-manifest": "pipeline",
            "prototype": "utility",
            "playtest-report": "utility",
            "propagate-design-change": "pipeline",
        }
        for name, (runtime_token, spec_token) in pairs.items():
            runtime = (ROOT / f".agents/skills/{name}/SKILL.md").read_text(encoding="utf-8")
            spec = (NEW / f"skills/{locations[name]}/{name}.md").read_text(encoding="utf-8")
            self.assertIn(runtime_token, runtime, name)
            self.assertIn(spec_token, spec, name)

    def test_map_systems_spec_matches_runtime_gate_order_and_write_boundaries(self):
        runtime = (ROOT / ".agents/skills/map-systems/SKILL.md").read_text(encoding="utf-8")
        spec = (NEW / "skills/pipeline/map-systems.md").read_text(encoding="utf-8")

        runtime_order = (
            "After dependency mapping is approved",
            "After priorities are approved",
            "### Initial systems-index changeset",
            "After the initial systems index write",
        )
        spec_order = (
            "TD-SYSTEM-BOUNDARY after dependency-map approval",
            "PR-SCOPE after priority approval",
            "initial two-file changeset",
            "CD-SYSTEMS after the initial index write",
        )
        for text, markers in ((runtime, runtime_order), (spec, spec_order)):
            for marker in markers:
                self.assertIn(marker, text)
            positions = [text.index(marker) for marker in markers]
            self.assertEqual(sorted(positions), positions)

        for gate in ("TD-SYSTEM-BOUNDARY", "PR-SCOPE", "CD-SYSTEMS"):
            self.assertIn(f"{gate} skipped — Phase-gated mode.", runtime)
            self.assertIn(f"{gate} skipped — Solo mode.", runtime)
            self.assertIn(f"{gate} skipped — Phase-gated mode.", spec)
            self.assertIn(f"{gate} skipped — Solo mode.", spec)

        for text in (runtime, spec):
            self.assertIn("`design/gdd/systems-index.md`", text)
            self.assertIn("`production/session-state/active.md`", text)
            self.assertIn("one complete proposed changeset", text)
            self.assertIn("exact revision changeset", text)
            self.assertIn("approval before modifying", text)
            self.assertNotIn("`design/systems-index.md`", text)
            self.assertNotIn("spawn in parallel", text)
            self.assertNotIn("both gates", text)

    def test_authoring_specs_match_exact_gate_roles_modes_paths_and_finalization(self):
        architecture = (NEW / "skills/authoring/create-architecture.md").read_text(encoding="utf-8")
        self.assertIn(
            "TD-ARCHITECTURE is mandatory in `full`, `phase-gated`, and `solo`",
            architecture,
        )
        self.assertIn(
            "LP-FEASIBILITY is optional: run it only in `full`",
            architecture,
        )
        self.assertIn("read back and finalize the already assembled document", architecture)
        self.assertIn("No second whole-document write approval", architecture)

        design = (NEW / "skills/authoring/design-system.md").read_text(encoding="utf-8")
        self.assertIn(
            "CD-GDD-ALIGN is optional: run it only in `full`; skip it in `phase-gated` and `solo`",
            design,
        )
        self.assertNotIn("explicitly part of a phase transition", design)
        self.assertNotIn("limited to an explicit phase transition", design)

        art = (NEW / "skills/authoring/art-bible.md").read_text(encoding="utf-8")
        self.assertIn(
            "AD-ART-BIBLE delegates to `art-director` and is optional: run it only in `full`",
            art,
        )
        self.assertNotIn("design/art-bible.md", art)
        self.assertIn("design/art/art-bible.md", art)
        asset_spec = (NEW / "skills/utility/asset-spec.md").read_text(encoding="utf-8")
        self.assertNotIn("design/art-bible.md", asset_spec)
        self.assertIn("design/art/art-bible.md", asset_spec)

        adr_runtime = (ROOT / ".agents/skills/architecture-decision/SKILL.md").read_text(encoding="utf-8")
        adr_spec = (NEW / "skills/authoring/architecture-decision.md").read_text(encoding="utf-8")
        self.assertIn("TD-ADR is required in full, lean, and solo modes", adr_runtime)
        self.assertIn(
            "TD-ADR is required in `full`, `phase-gated`, and `solo`",
            adr_spec,
        )
        self.assertNotIn("LP-FEASIBILITY", adr_spec)
        self.assertNotIn("TD-ADR skipped", adr_spec)

    def test_skill_test_spec_and_rubric_accept_both_approval_workflow_shapes(self):
        runtime = (ROOT / ".agents/skills/skill-test/SKILL.md").read_text(encoding="utf-8")
        spec = (NEW / "skills/utility/skill-test.md").read_text(encoding="utf-8")
        rubric = (NEW / "quality-rubric.md").read_text(encoding="utf-8")
        for text in (runtime, spec, rubric):
            self.assertIn("complete approved changeset", text)
            self.assertIn("sequential bounded section", text)
            self.assertIn("write only that approved section", text)
            self.assertIn("per-file or per-line reapproval", text)

    def test_framework_core_documents_define_codex_native_protocol(self):
        combined = "\n".join(
            (NEW / name).read_text(encoding="utf-8")
            for name in ("README.md", "AGENTS.md", "quality-rubric.md")
        )
        self.assertIn("Sol (`gpt-5.6`)", combined)
        self.assertIn("Terra (`gpt-5.6-terra`)", combined)
        self.assertIn("Luna (`gpt-5.6-luna`)", combined)
        self.assertIn("maximum delegation depth is 1", combined)
        self.assertIn("parent agent synthesizes", combined)
        self.assertIn("1–3 questions", combined)
        self.assertIn("2–3 options", combined)

    def test_vertical_slice_and_skill_test_have_complete_native_cases(self):
        vertical = (NEW / "skills/utility/vertical-slice.md").read_text(encoding="utf-8")
        self.assertIn("### Case 1: Happy Path", vertical)
        self.assertIn("### Case 2: Blocked Preconditions", vertical)
        self.assertIn("### Case 3: Scope Boundary", vertical)
        self.assertIn("### Case 4: Evidence Failure", vertical)
        self.assertIn("### Case 5: Final Gate", vertical)
        self.assertIn("PROCEED", vertical)
        self.assertIn("PIVOT", vertical)
        self.assertIn("KILL", vertical)

        skill_test = (NEW / "skills/utility/skill-test.md").read_text(encoding="utf-8")
        self.assertIn("exactly 73 runtime skills", skill_test)
        self.assertIn("exactly 49 runtime agents", skill_test)
        self.assertIn("optionally offers one complete approved changeset", skill_test)


if __name__ == "__main__":
    unittest.main()
