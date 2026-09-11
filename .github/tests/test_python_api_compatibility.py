# Copyright (c) Microsoft. All rights reserved.

# ruff:file-ignore[implicit-namespace-package, undocumented-public-class, undocumented-public-method]

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).parents[1] / "scripts" / "check_python_api_compatibility.py"
)
SPEC = importlib.util.spec_from_file_location(
    "check_python_api_compatibility", SCRIPT_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
api_checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = api_checker
SPEC.loader.exec_module(api_checker)


class ApiCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        self.run_git("init", "-q")
        self.run_git("config", "user.email", "test@example.com")
        self.run_git("config", "user.name", "Test")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def write_status(self, packages: list[tuple[str, str, str]]) -> None:
        rows = [
            "# Python Package Status",
            "",
            "| Package | Path | State |",
            "| --- | --- | --- |",
        ]
        rows.extend(
            f"| `{name}` | `python/packages/{path}` | `{state}` |"
            for name, path, state in packages
        )
        status_path = self.repo / "python" / "PACKAGE_STATUS.md"
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text("\n".join(rows) + "\n")

    def write_module(self, package: str, module: str, files: dict[str, str]) -> Path:
        module_path = self.repo / "python" / "packages" / package / module
        module_path.mkdir(parents=True, exist_ok=True)
        for relative_path, content in files.items():
            (module_path / relative_path).write_text(content)
        return module_path

    def commit(self) -> str:
        self.run_git("add", ".")
        self.run_git("commit", "-qm", "baseline")
        return self.run_git("rev-parse", "HEAD")

    def run_checker(
        self, base_sha: str, *, acknowledged: bool = False
    ) -> subprocess.CompletedProcess[str]:
        summary_path = self.repo / "summary.md"
        command = [
            sys.executable,
            str(SCRIPT_PATH),
            "--base-sha",
            base_sha,
            "--repo",
            str(self.repo),
        ]
        if acknowledged:
            command.append("--acknowledge-breaking-changes")
        env = {**os.environ, "GITHUB_STEP_SUMMARY": str(summary_path)}
        return subprocess.run(
            command, capture_output=True, text=True, env=env, check=False
        )

    def test_discovers_only_released_non_lab_modules(self) -> None:
        self.write_status(
            [
                ("agent-framework-stable", "stable", "released"),
                ("agent-framework-beta", "beta", "beta"),
                ("agent-framework-lab", "lab", "released"),
            ]
        )
        self.write_module("stable", "stable_api", {"__init__.py": ""})
        self.write_module("beta", "beta_api", {"__init__.py": ""})
        self.write_module("lab", "lab_api", {"__init__.py": ""})
        base_sha = self.commit()

        states = api_checker._package_states(self.repo, base_sha)
        specs = api_checker._module_specs(self.repo, base_sha, states)

        self.assertEqual([spec.module for spec in specs], ["stable_api"])

    def test_filters_base_experimental_apis_but_not_head_only_decorators(self) -> None:
        self.write_status([("agent-framework-core", "core", "released")])
        self.write_module(
            "core",
            "agent_framework",
            {
                "__init__.py": (
                    "from ._api import ExperimentalBase, PublicChild, experimental_function, stable_function\n"
                    '__all__ = ["ExperimentalBase", "PublicChild", "experimental_function", "stable_function"]\n'
                ),
                "_feature_stage.py": "def experimental(*, feature_id):\n    return lambda obj: obj\n",
                "_api.py": (
                    "from ._feature_stage import experimental\n\n"
                    '@experimental(feature_id="TEST")\n'
                    "class ExperimentalBase:\n"
                    "    def inherited(self, value): pass\n\n"
                    "class PublicChild(ExperimentalBase): pass\n\n"
                    '@experimental(feature_id="TEST")\n'
                    "def experimental_function(value): pass\n\n"
                    "def stable_function(value): pass\n"
                ),
            },
        )
        base_sha = self.commit()
        api_path = self.repo / "python/packages/core/agent_framework/_api.py"
        api_path.write_text(
            "from ._feature_stage import experimental\n\n"
            '@experimental(feature_id="TEST")\n'
            "class ExperimentalBase:\n"
            "    def inherited(self): pass\n\n"
            "class PublicChild(ExperimentalBase): pass\n\n"
            '@experimental(feature_id="TEST")\n'
            "def experimental_function(): pass\n\n"
            '@experimental(feature_id="TEST")\n'
            "def stable_function(): pass\n"
        )

        result = self.run_checker(base_sha)

        self.assertEqual(result.returncode, 1)
        warnings = [
            line for line in result.stdout.splitlines() if line.startswith("::warning ")
        ]
        self.assertEqual(len(warnings), 1)
        self.assertIn("stable_function(value)", warnings[0])

    def test_removed_top_level_module_is_reported_and_acknowledgeable(self) -> None:
        self.write_status([("agent-framework-stable", "stable", "released")])
        module_path = self.write_module(
            "stable",
            "stable_api",
            {"__init__.py": "def public_function(value): pass\n"},
        )
        base_sha = self.commit()
        shutil.rmtree(module_path)

        result = self.run_checker(base_sha)
        acknowledged_result = self.run_checker(base_sha, acknowledged=True)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "::warning title=stable_api::Released public import package was removed",
            result.stdout,
        )
        self.assertIn(
            "- Published API breakages: 1", (self.repo / "summary.md").read_text()
        )
        self.assertEqual(acknowledged_result.returncode, 0)

    def test_compatible_api_is_successful_and_writes_summary(self) -> None:
        self.write_status([("agent-framework-stable", "stable", "released")])
        self.write_module(
            "stable",
            "stable_api",
            {"__init__.py": "def public_function(value): pass\n"},
        )
        base_sha = self.commit()

        result = self.run_checker(base_sha)

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "- Published API breakages: 0", (self.repo / "summary.md").read_text()
        )


if __name__ == "__main__":
    unittest.main()
