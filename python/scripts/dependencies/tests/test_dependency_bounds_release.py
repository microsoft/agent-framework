# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path
from subprocess import CompletedProcess

from scripts.dependencies._dependency_bounds_release_impl import (
    ReleaseProbePlan,
    _build_release_probe_command,
    _build_release_probe_plan,
    _build_release_project_map,
    _changed_release_project_paths,
)


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

    root_plan = _build_release_probe_plan(tmp_path, projects["agent-framework"], projects)
    root_editables = "\n".join(root_plan.editable_specs)
    assert "packages/core" in root_editables
    assert "packages/connector" in root_editables
    assert "pytest" not in root_plan.reported_distributions


def test_release_probe_command_is_lock_independent_and_uses_bound_resolution(tmp_path: Path) -> None:
    plan = ReleaseProbePlan(
        project_path=Path("packages/openai"),
        package_name="agent-framework-openai",
        editable_specs=(str(tmp_path / "packages/openai"), str(tmp_path / "packages/core")),
        import_modules=("agent_framework_openai",),
        reported_distributions=("agent-framework-openai", "openai"),
    )

    command = _build_release_probe_command(plan, resolution="lowest-direct", python_version="3.10")

    assert "--no-project" in command
    assert command[command.index("--resolution") + 1] == "lowest-direct"
    assert command[command.index("--python") + 1] == "3.10"
    assert command[command.index("--prerelease") + 1] == "if-necessary-or-explicit"
    assert command.count("--with-editable") == 2
    assert "pytest" not in command
    assert "pyright" not in command


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
