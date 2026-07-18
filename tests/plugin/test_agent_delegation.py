from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.codex_studio.engine_pack import load_studio_config


ROOT = Path(__file__).resolve().parents[2]
PLUGIN_STUDIO = ROOT / "plugins/codex-game-studios/assets/studio"


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


def _run_resolver(studio: Path, project: Path, role: str) -> subprocess.CompletedProcess[str]:
    script = studio / "tools/codex_studio/agent_delegation.py"
    command = (
        sys.executable,
        str(script),
        "resolve",
        "--project-root",
        str(project),
        "--role",
        role,
    )
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(
        command,
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


class InstalledAgentDelegationTests(unittest.TestCase):
    def test_studio_config_fixture_is_strictly_valid(self):
        # Arrange / Act / Assert
        cases = (
            ("unconfigured", "", "", "none"),
            ("godot", "4.6", "gdscript", "godot"),
        )
        for engine, version, language, active_pack in cases:
            with self.subTest(engine=engine), tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "project"
                project.mkdir()
                _write_studio_config(project, engine)
                try:
                    config = load_studio_config(project)
                except ValueError as error:
                    self.fail(f"studio config fixture must be strictly valid: {error}")
                self.assertEqual((engine, version, language, active_pack), (
                    config.engine,
                    config.engine_version,
                    config.language,
                    config.active_engine_pack,
                ))

    def test_bundled_resolver_loads_core_and_selected_pack_without_project_agents(self):
        # Arrange
        resolver = PLUGIN_STUDIO / "tools/codex_studio/agent_delegation.py"
        self.assertTrue(resolver.is_file(), "bundled resolver is missing")
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            _write_studio_config(project, "godot")

            # Act
            core = _run_resolver(PLUGIN_STUDIO, project, "qa-tester")
            engine = _run_resolver(PLUGIN_STUDIO, project, "godot-specialist")

            # Assert
            self.assertFalse((project / ".codex/agents").exists())
            self.assertFalse((project / ".codex/agent-packs").exists())
            self.assertEqual(0, core.returncode, core.stderr)
            self.assertEqual(0, engine.returncode, engine.stderr)
            core_data = json.loads(core.stdout)
            engine_data = json.loads(engine.stdout)
            self.assertEqual("qa-tester", core_data["name"])
            self.assertEqual("core", core_data["source_kind"])
            self.assertEqual("godot-specialist", engine_data["name"])
            self.assertEqual("godot", engine_data["source_kind"])
            self.assertEqual(
                (PLUGIN_STUDIO / ".codex/agents/qa-tester.toml").resolve(),
                Path(core_data["path"]).resolve(),
            )
            self.assertEqual(
                (
                    PLUGIN_STUDIO
                    / ".codex/agent-packs/godot/godot-specialist.toml"
                ).resolve(),
                Path(engine_data["path"]).resolve(),
            )

    def test_bundled_resolver_rejects_traversal_unknown_and_cross_pack(self):
        self.assertTrue(
            (PLUGIN_STUDIO / "tools/codex_studio/agent_delegation.py").is_file(),
            "bundled resolver is missing",
        )
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            _write_studio_config(project, "godot")
            cases = (
                ("../qa-tester", "safe role slug"),
                ("unknown-role", "unknown role"),
                ("unity-specialist", "inactive engine pack"),
            )
            for role, message in cases:
                with self.subTest(role=role):
                    result = _run_resolver(PLUGIN_STUDIO, project, role)
                    self.assertEqual(2, result.returncode)
                    self.assertIn(message, result.stderr)

    def test_disposable_bundled_resolver_rejects_contract_tampering(self):
        self.assertTrue(
            (PLUGIN_STUDIO / "tools/codex_studio/agent_delegation.py").is_file(),
            "bundled resolver is missing",
        )
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            outside = base / "outside.toml"
            outside.write_text(
                (PLUGIN_STUDIO / ".codex/agents/qa-tester.toml").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            cases = ("missing", "malformed", "name-mismatch", "symlink", "ambiguous")
            for case in cases:
                with self.subTest(case=case):
                    studio = base / f"studio-{case}"
                    shutil.copytree(PLUGIN_STUDIO, studio)
                    project = base / f"project-{case}"
                    project.mkdir()
                    _write_studio_config(project, "godot")
                    target = studio / ".codex/agents/qa-tester.toml"
                    if case == "missing":
                        target.unlink()
                    elif case == "malformed":
                        target.write_text("name = [", encoding="utf-8")
                    elif case == "name-mismatch":
                        target.write_text(
                            target.read_text(encoding="utf-8").replace(
                                'name = "qa-tester"', 'name = "qa-lead"', 1
                            ),
                            encoding="utf-8",
                        )
                    elif case == "symlink":
                        target.unlink()
                        target.symlink_to(outside)
                    else:
                        shutil.copy2(
                            target,
                            studio / ".codex/agent-packs/godot/qa-tester.toml",
                        )

                    result = _run_resolver(studio, project, "qa-tester")

                    self.assertEqual(2, result.returncode, result.stdout)
                    self.assertTrue(result.stderr.strip())


if __name__ == "__main__":
    unittest.main()
