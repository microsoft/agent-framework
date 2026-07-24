# Copyright (c) Microsoft. All rights reserved.

import json
import sys
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from scripts.dependencies._dependency_bounds_release_impl import (
    _PROBE_RESULT_PREFIX,
    ReleaseProbePlan,
    _build_release_probe_command,
    _build_release_probe_plan,
    _build_release_project_map,
    _changed_release_project_paths,
    _parse_probe_payload,
    run_release_mode,
)
from scripts.dependencies.validate_dependency_bounds import main


def _write_project(path: Path, content: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text(content)


def test_release_probe_uses_only_the_required_internal_dependency_closure(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        """
[project]
name = "agent-framework"
version = "1.2.0"
requires-python = ">=3.10"
dependencies = ["agent-framework-core[all]==1.2.0"]

[tool.uv.workspace]
members = ["packages/*"]

[tool.flit.module]
name = "agent_framework_meta"
""",
    )
    _write_project(
        tmp_path / "packages/core",
        """
[project]
name = "agent-framework-core"
version = "1.2.0"
requires-python = ">=3.10"
dependencies = ["pydantic>=2,<3"]

[project.optional-dependencies]
all = ["agent-framework-connector>=1,<2"]
dev = ["pytest>=9"]

[tool.flit.module]
name = "agent_framework"
""",
    )
    _write_project(
        tmp_path / "packages/connector",
        """
[project]
name = "agent-framework-connector"
version = "1.0.0"
requires-python = ">=3.10"
dependencies = ["agent-framework-core>=1,<2", "httpx>=0.27,<1"]

[tool.flit.module]
name = "agent_framework_connector"
""",
    )
    _write_project(
        tmp_path / "packages/provider",
        """
[project]
name = "agent-framework-provider"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = ["agent-framework-core>=1,<2", "openai>=2,<3"]

[tool.flit.module]
name = "agent_framework_provider"
""",
    )

    projects = _build_release_project_map(tmp_path)
    provider_plan = _build_release_probe_plan(tmp_path, projects["agent-framework-provider"], projects)
    provider_editables = "\n".join(provider_plan.editable_specs)

    assert "packages/provider" in provider_editables
    assert "packages/core" in provider_editables
    assert "packages/connector" not in provider_editables
    assert provider_plan.python_version == "3.11"

    root_plan = _build_release_probe_plan(tmp_path, projects["agent-framework"], projects)
    root_editables = "\n".join(root_plan.editable_specs)
    assert "packages/core" in root_editables
    assert "packages/connector" in root_editables
    assert "pytest" not in root_plan.reported_distributions
    assert root_plan.python_version == "3.10"


def test_release_probe_command_is_lock_independent_and_uses_bound_resolution(tmp_path: Path) -> None:
    plan = ReleaseProbePlan(
        project_path=Path("packages/openai"),
        package_name="agent-framework-openai",
        editable_specs=(str(tmp_path / "packages/openai"), str(tmp_path / "packages/core")),
        import_modules=("agent_framework_openai",),
        reported_distributions=("agent-framework-openai", "openai"),
        python_version="3.11",
    )

    command = _build_release_probe_command(plan, resolution="lowest-direct")

    assert "--no-project" in command
    assert command[command.index("--resolution") + 1] == "lowest-direct"
    assert command[command.index("--python") + 1] == "3.11"
    assert command[command.index("--prerelease") + 1] == "if-necessary-or-explicit"
    assert command.count("--with-editable") == 2
    assert "pytest" not in command
    assert "pyright" not in command

    overridden_command = _build_release_probe_command(plan, resolution="highest", python_override="3.12")
    assert overridden_command[overridden_command.index("--python") + 1] == "3.12"


def test_changed_release_projects_are_relative_to_python_workspace(tmp_path: Path, monkeypatch) -> None:
    def fake_run(*args, **kwargs) -> CompletedProcess[str]:
        return CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="pyproject.toml\npackages/core/pyproject.toml\nREADME.md\n",
            stderr="",
        )

    monkeypatch.setattr("scripts.dependencies._dependency_bounds_release_impl.subprocess.run", fake_run)

    assert _changed_release_project_paths(tmp_path, "upstream/main") == {Path("."), Path("packages/core")}


def test_parse_probe_payload_uses_the_last_valid_marker() -> None:
    first_payload = json.dumps({"versions": {"openai": "2.25.0"}})
    last_payload = {"imports": ["agent_framework_openai"], "versions": {"openai": "2.47.0"}}
    stdout = "\n".join((
        f"{_PROBE_RESULT_PREFIX}{first_payload}",
        "unrelated subprocess output",
        f"{_PROBE_RESULT_PREFIX}{json.dumps(last_payload)}",
    ))

    assert _parse_probe_payload(stdout) == last_payload
    assert _parse_probe_payload(f"{_PROBE_RESULT_PREFIX}not-json") is None
    assert _parse_probe_payload(f"{_PROBE_RESULT_PREFIX}[]") is None
    assert _parse_probe_payload("unrelated subprocess output") is None


def test_run_release_mode_dry_run_uses_selected_package_python_floor(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        """
[project]
name = "agent-framework"
version = "1.2.0"
requires-python = ">=3.10"
dependencies = []

[tool.uv.workspace]
members = ["packages/*"]

[tool.flit.module]
name = "agent_framework_meta"
""",
    )
    _write_project(
        tmp_path / "packages/provider",
        """
[project]
name = "agent-framework-provider"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = []

[tool.flit.module]
name = "agent_framework_provider"
""",
    )
    output_json = tmp_path / "release-results.json"

    exit_code = run_release_mode(
        workspace_root=tmp_path,
        base_ref="HEAD",
        package_filter="provider",
        parallelism=2,
        python_override=None,
        deadline_seconds=300,
        dry_run=True,
        output_json=output_json,
    )

    assert exit_code == 0
    report = json.loads(output_json.read_text())
    assert report["python_override"] is None
    assert report["summary"] == {"probes_total": 2, "probes_passed": 2, "probes_failed": 0}
    assert {probe["python"] for probe in report["probes"]} == {"3.11"}
    assert {probe["status"] for probe in report["probes"]} == {"dry-run"}


def test_release_mode_rejects_blank_base_ref(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["validate_dependency_bounds", "--mode", "release", "--base-ref", "   "])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2
    assert "release mode requires --base-ref" in capsys.readouterr().err
