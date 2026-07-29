# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: INP001

"""Shared runtime helpers for dependency-bound validation commands."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import cast

import tomli
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

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
_DEPENDENCY_PYRIGHT_COMMAND = (
    "import subprocess, sys; "
    "raise SystemExit(subprocess.call(["
    "sys.executable, '-m', 'pyright', '--project', 'pyrightconfig.dependency.json', "
    "'--pythonpath', sys.executable]))"
)


@lru_cache(maxsize=16)
def load_dependency_group_requirements(workspace_root: str, group_name: str) -> tuple[str, ...]:
    """Load string requirements from one root workspace dependency group."""
    pyproject_path = Path(workspace_root) / "pyproject.toml"
    data = cast(dict[str, object], tomli.loads(pyproject_path.read_text()))
    dependency_groups = cast(dict[str, object], data.get("dependency-groups", {}) or {})
    return _string_requirements(dependency_groups.get(group_name, []))


@dataclass(frozen=True)
class WorkspacePackageConfig:
    """Dependency metadata needed to resolve internal editable packages."""

    project_path: Path
    dependencies: tuple[str, ...]
    optional_dependencies: Mapping[str, tuple[str, ...]]
    dependency_groups: Mapping[str, tuple[str, ...]]


def _string_requirements(values: object) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(value for value in cast(list[object], values) if isinstance(value, str))


def load_workspace_package_configs(workspace_root: Path) -> dict[str, WorkspacePackageConfig]:
    """Load workspace package dependency metadata keyed by normalized package name."""
    packages: dict[str, WorkspacePackageConfig] = {}
    for pyproject_file in sorted((workspace_root / "packages").glob("*/pyproject.toml")):
        with pyproject_file.open("rb") as file:
            config = cast(dict[str, object], tomli.load(file))

        project = cast(dict[str, object], config.get("project", {}) or {})
        package_name = str(project.get("name", "")).strip()
        if not package_name:
            continue

        normalized_name = str(canonicalize_name(package_name))
        if normalized_name in packages:
            raise RuntimeError(f"Duplicate workspace package name: {package_name}")

        optional_config = cast(dict[str, object], project.get("optional-dependencies", {}) or {})
        optional_dependencies: dict[str, tuple[str, ...]] = {
            str(canonicalize_name(extra_name)): _string_requirements(requirements)
            for extra_name, requirements in optional_config.items()
        }
        dependency_group_config = cast(dict[str, object], config.get("dependency-groups", {}) or {})
        dependency_groups: dict[str, tuple[str, ...]] = {
            group_name: _string_requirements(requirements)
            for group_name, requirements in dependency_group_config.items()
        }
        packages[normalized_name] = WorkspacePackageConfig(
            project_path=pyproject_file.parent,
            dependencies=_string_requirements(project.get("dependencies", [])),
            optional_dependencies=optional_dependencies,
            dependency_groups=dependency_groups,
        )
    return packages


def resolve_internal_editables(
    package_name: str,
    packages: Mapping[str, WorkspacePackageConfig],
    *,
    dependency_groups: Sequence[str],
    optional_extras: Sequence[str],
) -> list[Path]:
    """Resolve the internal editable closure for the target package's selected dependency surface."""
    target_name = str(canonicalize_name(package_name))
    if target_name not in packages:
        raise ValueError(f"Unknown workspace package: {package_name}")

    requested_extras: dict[str, set[str]] = {
        target_name: {str(canonicalize_name(extra_name)) for extra_name in optional_extras}
    }
    processed_extras: dict[str, set[str]] = {}
    pending = [target_name]
    editables: set[Path] = set()

    while pending:
        current_name = pending.pop()
        current_extras = requested_extras[current_name]
        if processed_extras.get(current_name) == current_extras:
            continue
        processed_extras[current_name] = set(current_extras)

        package = packages[current_name]
        requirements = list(package.dependencies)
        for extra_name in sorted(current_extras):
            requirements.extend(package.optional_dependencies.get(extra_name, ()))
        if current_name == target_name:
            for group_name in dependency_groups:
                requirements.extend(package.dependency_groups.get(group_name, ()))

        for requirement_text in requirements:
            try:
                requirement = Requirement(requirement_text)
            except InvalidRequirement:
                continue

            dependency_name = str(canonicalize_name(requirement.name))
            dependency = packages.get(dependency_name)
            if dependency is None:
                continue

            if dependency_name != target_name:
                editables.add(dependency.project_path.resolve())

            previous_extras = requested_extras.setdefault(dependency_name, set())
            updated_extras = previous_extras | {str(canonicalize_name(extra)) for extra in requirement.extras}
            if dependency_name not in processed_extras or updated_extras != previous_extras:
                requested_extras[dependency_name] = updated_extras
                pending.append(dependency_name)

    return sorted(editables)


@lru_cache(maxsize=8)
def load_runtime_tool_requirements(workspace_root: str) -> list[str]:
    """Load shared tool requirements used by package test and typing tasks."""
    # `uv run --isolated` starts from a clean environment, so the validator has to re-attach the
    # shared tooling that package-level poe tasks expect to find.
    runtime_requirements: list[str] = []
    for requirement in load_dependency_group_requirements(workspace_root, "dev"):
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


def extend_command_with_task(command: list[str], task_name: str, *, workspace_root: Path) -> None:
    """Append the command needed to execute one validation task."""
    if task_name == "pyright":
        command.extend(["python", "-c", _PYRIGHT_COMMAND])
        return
    if task_name == "dependency-pyright":
        for requirement in load_dependency_group_requirements(str(workspace_root.resolve()), "test"):
            command.extend(["--with", requirement])
        command.extend(["python", "-c", _DEPENDENCY_PYRIGHT_COMMAND])
        return

    command.extend(["python", "-m", "poethepoet", task_name])


def next_zero_major_minor_boundary(version_text: str) -> str:
    """Return the exclusive upper bound for the next 0.x minor after the given version."""
    from packaging.version import Version

    version = Version(version_text)
    return f"0.{version.minor + 1}.0"
