# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: INP001

"""Shared runtime helpers for dependency-bound validation commands."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import tomli
from packaging.requirements import InvalidRequirement, Requirement

_TOOL_REQUIREMENT_NAMES = {
    "mypy",
    "poethepoet",
    "pyright",
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "pytest-retry",
    "pytest-timeout",
    "pytest-xdist",
    "ruff",
}

_ADDITIONAL_RUNTIME_REQUIREMENTS = (
    "graphviz",
    "opentelemetry-exporter-otlp-proto-grpc",
    "opentelemetry-exporter-otlp-proto-http",
)

# Run pyright through the current interpreter so its import resolution matches the uv-created environment.
_PYRIGHT_COMMAND = (
    "import subprocess, sys; "
    "raise SystemExit(subprocess.call([sys.executable, '-m', 'pyright', '--pythonpath', sys.executable]))"
)


@lru_cache(maxsize=8)
def load_runtime_tool_requirements(workspace_root: str) -> list[str]:
    """Load shared tool requirements used by package test and typing tasks."""
    workspace_path = Path(workspace_root)
    pyproject_path = workspace_path / "pyproject.toml"
    data = tomli.loads(pyproject_path.read_text())
    dev_requirements = data.get("dependency-groups", {}).get("dev", []) or []

    # `uv run --isolated` starts from a clean environment, so the validator has to re-attach the
    # shared tooling that package-level poe tasks expect to find.
    runtime_requirements: list[str] = []
    for requirement in dev_requirements:
        if not isinstance(requirement, str):
            continue
        try:
            parsed = Requirement(requirement)
        except InvalidRequirement:
            continue
        if parsed.name.lower() in _TOOL_REQUIREMENT_NAMES:
            runtime_requirements.append(requirement)
    return runtime_requirements


def extend_command_with_runtime_tools(command: list[str], workspace_root: Path) -> None:
    """Append shared tooling requirements to a uv run command."""
    # Mirror the repo-wide test/lint toolchain inside the temporary environment before adding the task.
    for requirement in load_runtime_tool_requirements(str(workspace_root.resolve())):
        command.extend(["--with", requirement])
    for requirement in _ADDITIONAL_RUNTIME_REQUIREMENTS:
        command.extend(["--with", requirement])


def extend_command_with_task(command: list[str], task_name: str) -> None:
    """Append the command needed to execute one validation task."""
    if task_name == "pyright":
        command.extend(["python", "-c", _PYRIGHT_COMMAND])
        return

    command.extend(["python", "-m", "poethepoet", task_name])


def next_zero_major_minor_boundary(version_text: str) -> str:
    """Return the exclusive upper bound for the next 0.x minor after the given version."""
    from packaging.version import Version

    version = Version(version_text)
    return f"0.{version.minor + 1}.0"
