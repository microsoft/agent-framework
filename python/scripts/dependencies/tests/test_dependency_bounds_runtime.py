# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.dependencies._dependency_bounds_lower_impl import _select_validation_tasks as _select_lower_tasks
from scripts.dependencies._dependency_bounds_runtime import (
    extend_command_with_task,
    load_workspace_package_configs,
    resolve_internal_editables,
)
from scripts.dependencies._dependency_bounds_upper_impl import _select_validation_tasks as _select_upper_tasks
from scripts.dependencies.validate_dependency_bounds import _build_test_plans


def _write_project(path: Path, content: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text(content)


def test_internal_editables_follow_only_the_selected_target_surface(tmp_path: Path) -> None:
    _write_project(
        tmp_path / "packages/target",
        """
[project]
name = "agent-framework-target"
version = "1.0.0"
dependencies = ["agent-framework-core"]

[project.optional-dependencies]
dev = ["agent-framework-helper"]

[dependency-groups]
test = ["agent-framework-orchestrations"]
""",
    )
    _write_project(
        tmp_path / "packages/core",
        """
[project]
name = "agent-framework-core"
version = "1.0.0"
dependencies = []

[project.optional-dependencies]
all = ["agent-framework-unrelated"]

[dependency-groups]
dev = ["agent-framework-group-only"]
""",
    )
    _write_project(
        tmp_path / "packages/helper",
        """
[project]
name = "agent-framework-helper"
version = "1.0.0"
dependencies = ["agent-framework-core"]
""",
    )
    _write_project(
        tmp_path / "packages/orchestrations",
        """
[project]
name = "agent-framework-orchestrations"
version = "1.0.0"
dependencies = ["agent-framework-core"]
""",
    )
    for package_name in ("unrelated", "group-only"):
        _write_project(
            tmp_path / f"packages/{package_name}",
            f"""
[project]
name = "agent-framework-{package_name}"
version = "1.0.0"
dependencies = []
""",
        )

    packages = load_workspace_package_configs(tmp_path)
    editables = resolve_internal_editables(
        "agent-framework-target",
        packages,
        dependency_groups=["test"],
        optional_extras=["dev"],
    )

    assert editables == sorted([
        (tmp_path / "packages/core").resolve(),
        (tmp_path / "packages/helper").resolve(),
        (tmp_path / "packages/orchestrations").resolve(),
    ])


def test_internal_editables_follow_explicitly_requested_transitive_extras(tmp_path: Path) -> None:
    _write_project(
        tmp_path / "packages/target",
        """
[project]
name = "agent-framework-target"
version = "1.0.0"
dependencies = ["agent-framework-core[all]"]
""",
    )
    _write_project(
        tmp_path / "packages/core",
        """
[project]
name = "agent-framework-core"
version = "1.0.0"
dependencies = []

[project.optional-dependencies]
all = ["agent-framework-connector"]
""",
    )
    _write_project(
        tmp_path / "packages/connector",
        """
[project]
name = "agent-framework-connector"
version = "1.0.0"
dependencies = ["agent-framework-core"]
""",
    )

    packages = load_workspace_package_configs(tmp_path)
    editables = resolve_internal_editables(
        "agent-framework-target",
        packages,
        dependency_groups=[],
        optional_extras=[],
    )

    assert editables == sorted([
        (tmp_path / "packages/connector").resolve(),
        (tmp_path / "packages/core").resolve(),
    ])


@pytest.mark.parametrize("selector", [_select_lower_tasks, _select_upper_tasks])
def test_dependency_pyright_takes_priority_for_bound_validation(
    selector: Callable[[set[str]], list[str]],
) -> None:
    assert selector({"test", "pyright", "dependency-pyright"}) == ["dependency-pyright", "test"]


def test_test_mode_uses_dependency_pyright_when_available(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.uv.workspace]
members = ["packages/*"]
"""
    )
    _write_project(
        tmp_path / "packages/core",
        """
[project]
name = "agent-framework-core"
version = "1.0.0"
dependencies = []

[tool.poe.tasks]
test = "pytest"
pyright = "pyright"
dependency-pyright = "pyright --project pyrightconfig.dependency.json"
""",
    )

    plans = _build_test_plans(tmp_path, "core")

    assert len(plans) == 1
    assert plans[0].typing_task == "dependency-pyright"


def test_dependency_pyright_reuses_root_test_requirements(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[dependency-groups]
test = ["azure-monitor-opentelemetry", "mcp[ws]"]
"""
    )
    command = ["uv", "run"]

    extend_command_with_task(command, "dependency-pyright", workspace_root=tmp_path)

    assert command[:6] == [
        "uv",
        "run",
        "--with",
        "azure-monitor-opentelemetry",
        "--with",
        "mcp[ws]",
    ]
    assert command[-3:-1] == ["python", "-c"]
