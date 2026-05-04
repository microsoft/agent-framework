# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: S404, S603

"""Raise dependency upper bounds, validate, and persist the latest passing set."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

import tomli
from packaging.requirements import InvalidRequirement, Requirement
from packaging.version import InvalidVersion, Version
from rich import print

from scripts.dependencies._dependency_bounds_runtime import (
    extend_command_with_runtime_tools,
    extend_command_with_task,
    next_zero_major_minor_boundary,
)
from scripts.task_runner import discover_projects, extract_poe_tasks, project_filter_matches

logger = logging.getLogger(__name__)

CHECK_TASK_PRIORITY = ("check", "typing", "pyright", "mypy", "lint")
REQ_PATTERN = r"^\s*([A-Za-z0-9_.-]+(?:\[[^\]]+\])?)\s*(.*?)\s*$"
SECTION_HEADER_PATTERN = re.compile(r"^\s*\[([^\]]+)\]\s*$")
INLINE_ARRAY_ASSIGNMENT_PATTERN = re.compile(
    r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_.-]+)\s*=\s*\[(?P<body>.*)\](?P<suffix>\s*(?:#.*)?)$"
)
QUOTED_STRING_PATTERN = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')


@dataclass
class RequirementEntry:
    """A parsed requirement entry from pyproject dependencies."""

    raw: str
    name: str
    name_extras: str
    marker: str | None
    spec_parts: list[str]
    lower_version: Version | None
    upper_index: int | None
    upper_version: Version | None
    exact_index: int | None = None
    exact_version: Version | None = None

    def with_upper(self, upper: Version) -> str:
        """Return a new requirement with the given exclusive upper bound."""
        updated_parts = list(self.spec_parts)
        if self.exact_index is not None and self.exact_version is not None:
            updated_parts[self.exact_index] = f">={self.exact_version}"
            if self.upper_index is not None:
                updated_parts[self.upper_index] = f"<{upper}"
            else:
                updated_parts.append(f"<{upper}")
        elif self.upper_index is not None:
            updated_parts[self.upper_index] = f"<{upper}"
        else:
            raise ValueError(f"Requirement has no mutable bound information: {self.raw}")
        spec = ",".join(updated_parts)
        requirement = f"{self.name_extras}{spec}"
        if self.marker:
            requirement += f"; {self.marker}"
        return requirement


@dataclass
class DependencyTarget:
    """A dependency to optimize within one package."""

    name: str
    entries: list[RequirementEntry]
    lower_version: Version | None
    upper_version: Version
    allow_prerelease_candidates: bool

    @property
    def original_requirements(self) -> list[str]:
        """Return original requirement strings for this dependency group."""
        return [entry.raw for entry in self.entries]


@dataclass
class DependencyAttempt:
    """A single upper-bound trial for one dependency."""

    trial_upper: str
    status: str
    error: str | None = None


@dataclass
class DependencyOutcome:
    """Final outcome for one dependency optimization."""

    name: str
    changed: bool
    original_requirements: list[str]
    final_requirements: list[str]
    candidate_versions: list[str]
    attempted_versions: list[str]
    attempts: list[DependencyAttempt]
    skipped_reason: str | None = None


@dataclass
class PackagePlan:
    """Execution plan for a package."""

    project_path: Path
    package_name: str
    pyproject_path: Path
    internal_editables: list[Path]
    include_dev_group: bool
    include_dev_extra: bool
    optional_extras: list[str]


@dataclass
class PackageOutcome:
    """Execution outcome for a package."""

    project_path: str
    package_name: str
    tasks: list[str]
    changed: bool
    dependencies: list[DependencyOutcome]
    replacements: dict[str, str]
    skipped: list[str]
    error: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate_error(stdout: str, stderr: str, *, max_chars: int = 2000) -> str:
    combined = "\n".join(part for part in [stderr.strip(), stdout.strip()] if part)
    if len(combined) <= max_chars:
        return combined
    return f"...\n{combined[-max_chars:]}"


def _parse_requirement(requirement: str) -> RequirementEntry | None:
    match = re.match(REQ_PATTERN, requirement)
    if not match:
        return None
    name_extras = match.group(1)
    rest = match.group(2).strip()
    marker = None
    if ";" in rest:
        spec_part, marker_part = rest.split(";", 1)
        spec = spec_part.strip()
        marker = marker_part.strip()
    else:
        spec = rest
    if not spec:
        return None

    spec_parts = [part.strip() for part in spec.split(",") if part.strip()]
    if not spec_parts:
        return None

    lower_version: Version | None = None
    upper_version: Version | None = None
    upper_index: int | None = None
    exact_version: Version | None = None
    exact_index: int | None = None

    for index, part in enumerate(spec_parts):
        if part.startswith((">=", ">")):
            raw_version = part[2:].strip() if part.startswith(">=") else part[1:].strip()
            try:
                parsed = Version(raw_version)
            except InvalidVersion:
                continue
            if lower_version is None or parsed > lower_version:
                lower_version = parsed
        elif part.startswith(("==", "===")):
            raw_version = part[3:].strip() if part.startswith("===") else part[2:].strip()
            try:
                parsed = Version(raw_version)
            except InvalidVersion:
                continue
            exact_version = parsed
            exact_index = index
            if lower_version is None or parsed > lower_version:
                lower_version = parsed
        if part.startswith(("<", "<=")):
            raw_version = part[2:].strip() if part.startswith("<=") else part[1:].strip()
            try:
                parsed = Version(raw_version)
            except InvalidVersion:
                continue
            if upper_version is None or parsed < upper_version:
                upper_version = parsed
                upper_index = index

    if upper_version is None and exact_version is None:
        return None
    name = name_extras.split("[", 1)[0].lower()
    return RequirementEntry(
        raw=requirement,
        name=name,
        name_extras=name_extras,
        marker=marker,
        spec_parts=spec_parts,
        lower_version=lower_version,
        upper_index=upper_index,
        upper_version=upper_version,
        exact_index=exact_index,
        exact_version=exact_version,
    )


def _select_latest_dev_version(versions: list[Version]) -> Version | None:
    if not versions:
        return None
    stable_versions = [version for version in versions if not version.is_prerelease]
    if stable_versions:
        return stable_versions[-1]
    return versions[-1]


@lru_cache(maxsize=8)
def _load_workspace_package_versions(workspace_root: str) -> dict[str, Version]:
    workspace_path = Path(workspace_root)
    versions: dict[str, Version] = {}
    for package_pyproject in sorted((workspace_path / "packages").glob("*/pyproject.toml")):
        with package_pyproject.open("rb") as f:
            package_data = tomli.load(f)
        project_section = package_data.get("project", {}) or {}
        package_name = str(project_section.get("name", "")).strip().lower()
        package_version = project_section.get("version")
        if not package_name or not package_version:
            continue
        try:
            versions[package_name] = Version(str(package_version))
        except InvalidVersion:
            continue
    return versions


def _collect_dev_pin_replacements(
    pyproject_file: Path,
    *,
    catalog: VersionCatalog,
) -> dict[str, str]:
    with pyproject_file.open("rb") as f:
        data = tomli.load(f)
    project = data.get("project", {}) or {}
    optional_dependencies = project.get("optional-dependencies", {}) or {}
    dependency_groups = data.get("dependency-groups", {}) or {}
    logger.debug(
        "Collecting dev dependency replacements from %s with optional_dependencies=%s and dependency_groups=%s",
        pyproject_file,
        optional_dependencies.keys(),
        dependency_groups.keys(),
    )
    workspace_versions = _load_workspace_package_versions(str(pyproject_file.parent.parent.parent.resolve()))

    dev_requirements: list[str] = []
    dev_requirements.extend(
        requirement for requirement in (optional_dependencies.get("dev", []) or []) if isinstance(requirement, str)
    )
    dev_requirements.extend(
        requirement for requirement in (dependency_groups.get("dev", []) or []) if isinstance(requirement, str)
    )
    logger.debug(f"Found {len(dev_requirements)} dev requirements in {pyproject_file}")

    seen_requirements: set[str] = set()
    replacements: dict[str, str] = {}
    for requirement in dev_requirements:
        if requirement in seen_requirements:
            continue
        seen_requirements.add(requirement)

        # Refresh exact dev pins while we already have the file open so outdated test tooling
        # does not masquerade as a runtime dependency compatibility failure.
        try:
            parsed_requirement = Requirement(requirement)
        except InvalidRequirement:
            continue
        if parsed_requirement.url is not None:
            continue
        dependency_name = parsed_requirement.name.lower()
        if dependency_name.startswith("agent-framework"):
            latest_version = workspace_versions.get(dependency_name)
        else:
            # Dev-tool refreshes should follow the selected version source (PyPI by default)
            # instead of being pinned by the current lockfile. VersionCatalog already falls
            # back to lock data when PyPI cannot be reached or --version-source=lock is used.
            latest_version = _select_latest_dev_version(catalog.get(dependency_name))
        if latest_version is None:
            continue

        extras = f"[{','.join(sorted(parsed_requirement.extras))}]" if parsed_requirement.extras else ""
        marker = f"; {parsed_requirement.marker}" if parsed_requirement.marker else ""
        pinned_requirement = f"{parsed_requirement.name}{extras}=={latest_version}{marker}"
        if requirement != pinned_requirement:
            replacements[requirement] = pinned_requirement

    return replacements


def _is_dependency_array_assignment(section: str, key: str) -> bool:
    if section == "project":
        return key == "dependencies"
    return section in {"project.optional-dependencies", "dependency-groups"}


def _extract_inline_array_items(array_body: str) -> list[str] | None:
    items = [match.group(0) for match in QUOTED_STRING_PATTERN.finditer(array_body)]
    remainder = QUOTED_STRING_PATTERN.sub("", array_body)
    if remainder.replace(",", "").strip():
        return None
    return items


def _format_dependency_arrays_multiline(path: Path) -> None:
    original_text = path.read_text()
    lines = original_text.splitlines()
    current_section = ""
    updated_lines: list[str] = []
    changed = False

    for line in lines:
        section_match = SECTION_HEADER_PATTERN.match(line)
        if section_match:
            current_section = section_match.group(1).strip()
            updated_lines.append(line)
            continue

        assignment_match = INLINE_ARRAY_ASSIGNMENT_PATTERN.match(line)
        if assignment_match is None:
            updated_lines.append(line)
            continue

        indent = assignment_match.group("indent")
        key = assignment_match.group("key")
        body = assignment_match.group("body")
        suffix = (assignment_match.group("suffix") or "").rstrip()
        if not _is_dependency_array_assignment(current_section, key):
            updated_lines.append(line)
            continue

        items = _extract_inline_array_items(body)
        if items is None or len(items) == 0:
            updated_lines.append(line)
            continue

        changed = True
        updated_lines.append(f"{indent}{key} = [")
        updated_lines.extend(f"{indent}    {item}," for item in items)
        closing_line = f"{indent}]"
        if suffix:
            closing_line = f"{closing_line}{suffix}"
        updated_lines.append(closing_line)

    if not changed:
        return

    updated_text = "\n".join(updated_lines)
    if original_text.endswith("\n"):
        updated_text += "\n"
    path.write_text(updated_text)


def _replace_requirements(path: Path, replacements: list[tuple[str, str]]) -> None:
    text = path.read_text()
    updated_text = text
    for old, new in replacements:
        replaced = False
        old_double = f'"{old}"'
        old_single = f"'{old}'"
        new_double = f'"{new}"'
        new_single = f"'{new}'"
        if old_double in updated_text:
            updated_text = updated_text.replace(old_double, new_double)
            replaced = True
        if old_single in updated_text:
            updated_text = updated_text.replace(old_single, new_single)
            replaced = True
        if not replaced:
            raise ValueError(f"Could not find dependency string in {path}: {old}")
    if updated_text != text:
        path.write_text(updated_text)


def _load_lock_versions(workspace_root: Path) -> dict[str, list[Version]]:
    lock_file = workspace_root / "uv.lock"
    if not lock_file.exists():
        return {}
    with lock_file.open("rb") as f:
        lock_data = tomli.load(f)
    versions_by_name: dict[str, set[Version]] = {}
    for package_data in lock_data.get("package", []):
        package_name = str(package_data.get("name", "")).lower()
        package_version = package_data.get("version")
        if not package_name or not package_version:
            continue
        try:
            parsed = Version(str(package_version))
        except InvalidVersion:
            continue
        versions_by_name.setdefault(package_name, set()).add(parsed)
    return {name: sorted(values) for name, values in versions_by_name.items()}


class VersionCatalog:
    """Cache and fetch available dependency versions."""

    def __init__(self, lock_versions: dict[str, list[Version]], source: str) -> None:
        """Initialize the catalog with lock-based fallback and fetch source."""
        self._lock_versions = lock_versions
        self._source = source
        self._cache: dict[str, list[Version]] = {}
        self._lock = threading.Lock()

    def get(self, package_name: str) -> list[Version]:
        """Return cached or fetched versions for a package name."""
        with self._lock:
            cached = self._cache.get(package_name)
            if cached is not None:
                return cached
        versions = self._fetch(package_name)
        with self._lock:
            self._cache[package_name] = versions
        return versions

    def get_lock(self, package_name: str) -> list[Version]:
        """Return lockfile versions for a package name."""
        return self._lock_versions.get(package_name, [])

    def _fetch(self, package_name: str) -> list[Version]:
        if self._source == "lock":
            return self._lock_versions.get(package_name, [])

        try:
            url = f"https://pypi.org/pypi/{package_name}/json"
            with urllib_request.urlopen(url, timeout=20) as response:
                payload = json.load(response)
        except (urllib_error.URLError, TimeoutError, json.JSONDecodeError):
            return self._lock_versions.get(package_name, [])

        versions: set[Version] = set()
        for raw_version, files in payload.get("releases", {}).items():
            if not files:
                continue
            non_yanked = any(not bool(file_info.get("yanked", False)) for file_info in files)
            if not non_yanked:
                continue
            try:
                versions.add(Version(raw_version))
            except InvalidVersion:
                continue
        if versions:
            return sorted(versions)
        return self._lock_versions.get(package_name, [])


def _load_package_name(pyproject_file: Path) -> str:
    with pyproject_file.open("rb") as f:
        data = tomli.load(f)
    return str(data["project"]["name"])


def _extract_requirement_name(requirement: str) -> str | None:
    try:
        return Requirement(requirement).name.lower()
    except InvalidRequirement:
        return None


def _select_validation_tasks(available_tasks: set[str]) -> list[str]:
    check_task = next((task for task in CHECK_TASK_PRIORITY if task in available_tasks), None)
    tasks: list[str] = []
    if check_task:
        tasks.append(check_task)
    if "test" in available_tasks and "test" not in tasks:
        tasks.append("test")
    return tasks


def _build_workspace_package_map(workspace_root: Path) -> dict[str, Path]:
    package_map: dict[str, Path] = {}
    for pyproject_file in sorted((workspace_root / "packages").glob("*/pyproject.toml")):
        with pyproject_file.open("rb") as f:
            data = tomli.load(f)
        package_name = str(data.get("project", {}).get("name", "")).strip()
        if package_name:
            package_map[package_name] = pyproject_file.parent
    return package_map


def _build_internal_graph(workspace_root: Path, package_map: dict[str, Path]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for package_name, package_path in package_map.items():
        pyproject_file = package_path / "pyproject.toml"
        with pyproject_file.open("rb") as f:
            data = tomli.load(f)
        project = data.get("project", {}) or {}
        dependencies: list[str] = list(project.get("dependencies", []) or [])
        for values in (project.get("optional-dependencies", {}) or {}).values():
            dependencies.extend([value for value in (values or []) if isinstance(value, str)])
        for values in (data.get("dependency-groups", {}) or {}).values():
            dependencies.extend([value for value in (values or []) if isinstance(value, str)])
        internal = set()
        for dependency in dependencies:
            dependency_name = _extract_requirement_name(dependency)
            if dependency_name is None:
                continue
            if dependency_name.startswith("agent-framework"):
                for candidate_name in package_map:
                    if candidate_name.lower() == dependency_name:
                        internal.add(candidate_name)
                        break
        graph[package_name] = internal
    return graph


def _resolve_internal_editables(
    package_name: str, package_map: dict[str, Path], graph: dict[str, set[str]]
) -> list[Path]:
    visited: set[str] = set()
    stack = [package_name]
    results: set[Path] = set()
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for dependency_name in graph.get(current, set()):
            dependency_path = package_map.get(dependency_name)
            if dependency_path and dependency_name != package_name:
                results.add(dependency_path.resolve())
            stack.append(dependency_name)
    return sorted(results)


def _collect_targets(
    pyproject_file: Path,
    *,
    dependency_filters: set[str] | None,
) -> tuple[list[DependencyTarget], list[str]]:
    with pyproject_file.open("rb") as f:
        data = tomli.load(f)
    project = data.get("project", {})
    dependencies: list[str] = list(project.get("dependencies", []) or [])

    grouped: dict[str, list[RequirementEntry]] = {}
    skipped: list[str] = []

    for dependency in dependencies:
        parsed = _parse_requirement(dependency)
        if not parsed:
            continue
        if parsed.name.startswith("agent-framework"):
            continue
        if dependency_filters and parsed.name not in dependency_filters:
            continue
        grouped.setdefault(parsed.name, []).append(parsed)

    targets: list[DependencyTarget] = []
    for dependency_name, entries in sorted(grouped.items()):
        if not entries:
            continue
        # A dependency can be repeated across sections/extras. Only optimize it when every
        # occurrence agrees on the current bound shape so we never rewrite inconsistent specs.
        allow_prerelease_candidates = any(
            (
                (entry.lower_version is not None and entry.lower_version.is_prerelease)
                or (entry.upper_version is not None and entry.upper_version.is_prerelease)
                or (entry.exact_version is not None and entry.exact_version.is_prerelease)
            )
            for entry in entries
        )
        upper_entries = [entry for entry in entries if entry.upper_version is not None]
        exact_entries = [entry for entry in entries if entry.exact_version is not None]

        if upper_entries:
            if len(upper_entries) != len(entries):
                skipped.append(f"{dependency_name}: mixed bounded and unbounded/exact requirements in package")
                continue
            first_upper = upper_entries[0].upper_version
            if first_upper is None:
                skipped.append(f"{dependency_name}: missing upper bound value")
                continue
            if any(entry.upper_version != first_upper for entry in upper_entries[1:]):
                skipped.append(f"{dependency_name}: conflicting upper bounds in package")
                continue
            lower_versions = [entry.lower_version for entry in entries if entry.lower_version is not None]
            lower = max(lower_versions) if lower_versions else None
            targets.append(
                DependencyTarget(
                    name=dependency_name,
                    entries=entries,
                    lower_version=lower,
                    upper_version=first_upper,
                    allow_prerelease_candidates=allow_prerelease_candidates,
                )
            )
            continue

        if exact_entries and len(exact_entries) == len(entries):
            first_exact = exact_entries[0].exact_version
            if first_exact is None:
                skipped.append(f"{dependency_name}: missing exact version value")
                continue
            if any(entry.exact_version != first_exact for entry in exact_entries[1:]):
                skipped.append(f"{dependency_name}: conflicting exact pins in package")
                continue
            targets.append(
                DependencyTarget(
                    name=dependency_name,
                    entries=entries,
                    lower_version=first_exact,
                    upper_version=first_exact,
                    allow_prerelease_candidates=allow_prerelease_candidates,
                )
            )
            continue

        skipped.append(f"{dependency_name}: no usable upper or exact bound to optimize")
    return targets, skipped


def _build_trial_bounds(
    versions: list[Version],
    *,
    lower: Version | None,
    current_upper: Version,
    allow_prerelease: bool,
    max_candidates: int,
) -> list[Version]:
    # Candidate generation mirrors the policy encoded in pyproject bounds:
    # prerelease tracks only advance one prerelease step, any 0.x dependency may
    # span multiple validated minor lines, and stable tracks probe newer versions
    # from highest to lowest.
    if lower is not None and lower.is_prerelease:
        if lower.pre is not None:
            pre_tag, pre_num = lower.pre
            next_prerelease = Version(f"{lower.base_version}{pre_tag}{pre_num + 1}")
        elif lower.dev is not None:
            next_prerelease = Version(f"{lower.base_version}.dev{lower.dev + 1}")
        else:
            next_prerelease = None
        if next_prerelease is None:
            return []
        return [version for version in versions if version == next_prerelease and version > current_upper]

    if lower is not None and lower.major == 0:
        candidates = [version for version in versions if version.major == 0 and version > lower]
        if not allow_prerelease:
            candidates = [version for version in candidates if not version.is_prerelease]
        candidate_bounds = sorted(
            {
                Version(next_zero_major_minor_boundary(str(version)))
                for version in candidates
                if version >= current_upper
            },
            reverse=True,
        )
        if max_candidates > 0:
            return candidate_bounds[:max_candidates]
        return candidate_bounds

    candidates = [version for version in versions if version > current_upper and (lower is None or version > lower)]
    # `packaging` treats .dev/.a/.b/.rc as prereleases; only probe them when current spec already uses them.
    if not allow_prerelease:
        candidates = [version for version in candidates if not version.is_prerelease]
    candidates.sort(reverse=True)
    if max_candidates > 0:
        return candidates[:max_candidates]
    return candidates


def _select_upper_probe_version(
    versions: list[Version],
    *,
    lower: Version | None,
    upper_bound: Version,
    allow_prerelease: bool,
) -> Version | None:
    """Return the newest concrete version that would be allowed by a candidate upper bound."""
    probe_versions = [
        version for version in versions if version < upper_bound and (lower is None or version >= lower)
    ]
    if not allow_prerelease:
        probe_versions = [version for version in probe_versions if not version.is_prerelease]
    return probe_versions[-1] if probe_versions else None


def _run_tasks(
    project_dir: Path,
    *,
    workspace_root: Path,
    tasks: list[str],
    internal_editables: list[Path],
    resolution: str,
    dependency_pin: tuple[str, Version] | None,
    include_dev_group: bool,
    include_dev_extra: bool,
    optional_extras: list[str],
    timeout_seconds: int,
) -> tuple[bool, str | None]:
    # Every probe runs inside a fresh isolated uv environment. Clearing VIRTUAL_ENV avoids
    # leaking the caller's active environment into the subprocess and keeps validation from
    # mutating the repo's active `.venv`.
    env = dict(os.environ)
    env["UV_PRERELEASE"] = "allow"
    env.pop("VIRTUAL_ENV", None)
    for task_name in tasks:
        command = [
            "uv",
            "--no-progress",
            "--directory",
            str(project_dir),
            "run",
            "--isolated",
            "--resolution",
            resolution,
            "--prerelease",
            "allow",
            "--quiet",
        ]
        extend_command_with_runtime_tools(command, workspace_root)
        if include_dev_group:
            command.extend(["--group", "dev"])
        if include_dev_extra:
            command.extend(["--extra", "dev"])
        for extra_name in optional_extras:
            command.extend(["--extra", extra_name])
        for editable_path in internal_editables:
            command.extend(["--with-editable", str(editable_path)])
        if dependency_pin is not None:
            dependency_name, dependency_version = dependency_pin
            command.extend(["--with", f"{dependency_name}=={dependency_version}"])
        extend_command_with_task(command, task_name)
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return False, f"Timeout while running task '{task_name}'."
        if result.returncode != 0:
            return (
                False,
                f"Task '{task_name}' failed.\n{_truncate_error(result.stdout, result.stderr)}",
            )
    return True, None


def _optimize_dependency(
    *,
    temp_pyproject: Path,
    dependency: DependencyTarget,
    available_versions: list[Version],
    tasks: list[str],
    internal_editables: list[Path],
    dry_run: bool,
    max_candidates: int,
    timeout_seconds: int,
    package_label: str,
    include_dev_group: bool,
    include_dev_extra: bool,
    optional_extras: list[str],
) -> DependencyOutcome:
    # Build descending candidate trial bounds from the current constraint window.
    candidates = _build_trial_bounds(
        available_versions,
        lower=dependency.lower_version,
        current_upper=dependency.upper_version,
        allow_prerelease=dependency.allow_prerelease_candidates,
        max_candidates=max_candidates,
    )
    candidate_versions = [str(candidate) for candidate in candidates]
    attempted_versions: list[str] = []
    attempts: list[DependencyAttempt] = []
    final_requirements = dependency.original_requirements

    # Baselines answer two questions before the script widens any range:
    # does the current floor still work, and does the newest version already in range still work?
    in_range_versions = [
        version
        for version in available_versions
        if (dependency.lower_version is None or version >= dependency.lower_version)
        and (dependency.upper_version is None or version < dependency.upper_version)
    ]
    if not dependency.allow_prerelease_candidates:
        in_range_versions = [version for version in in_range_versions if not version.is_prerelease]
    baseline_trials: list[tuple[str, Version, str]] = []
    if dependency.upper_version is not None and dependency.lower_version == dependency.upper_version:
        baseline_trials.append(("current_fixed", dependency.upper_version, "highest"))
    else:
        if dependency.lower_version is not None:
            lower_probe = next(
                (version for version in in_range_versions if version >= dependency.lower_version),
                dependency.lower_version,
            )
            baseline_trials.append(("current_lower", lower_probe, "lowest-direct"))
        if dependency.upper_version is not None:
            upper_probe = in_range_versions[-1] if in_range_versions else dependency.upper_version
            baseline_trials.append(("current_upper", upper_probe, "highest"))

    for baseline_name, baseline_version, baseline_resolution in baseline_trials:
        attempted_versions.append(str(baseline_version))
        print(
            f"[cyan]{package_label} :: {dependency.name} :: baseline {baseline_name} "
            f"({baseline_resolution}) [{baseline_version}] [/cyan]"
        )
        success, error = _run_tasks(
            temp_pyproject.parent,
            workspace_root=temp_pyproject.parent.parent.parent,
            tasks=tasks,
            internal_editables=internal_editables,
            resolution=baseline_resolution,
            dependency_pin=(dependency.name, baseline_version),
            include_dev_group=include_dev_group,
            include_dev_extra=include_dev_extra,
            optional_extras=optional_extras,
            timeout_seconds=timeout_seconds,
        )
        if success:
            attempts.append(
                DependencyAttempt(
                    trial_upper=str(baseline_version),
                    status=f"{baseline_name}_passed",
                )
            )
            continue

        attempts.append(
            DependencyAttempt(
                trial_upper=str(baseline_version),
                status="failed",
                error=error,
            )
        )
        return DependencyOutcome(
            name=dependency.name,
            changed=False,
            original_requirements=dependency.original_requirements,
            final_requirements=dependency.original_requirements,
            candidate_versions=candidate_versions,
            attempted_versions=attempted_versions,
            attempts=attempts,
            skipped_reason=f"Baseline validation failed at {baseline_name}.",
        )

    if not candidates:
        return DependencyOutcome(
            name=dependency.name,
            changed=False,
            original_requirements=dependency.original_requirements,
            final_requirements=dependency.original_requirements,
            candidate_versions=[],
            attempted_versions=attempted_versions,
            attempts=attempts,
            skipped_reason="No higher candidate bounds found.",
        )

    # Probe candidates from highest to lowest; keep the first passing upper-bound rewrite.
    for candidate in candidates:
        probe_version = _select_upper_probe_version(
            available_versions,
            lower=dependency.lower_version,
            upper_bound=candidate,
            allow_prerelease=dependency.allow_prerelease_candidates,
        )
        if probe_version is None:
            attempts.append(
                DependencyAttempt(
                    trial_upper=str(candidate),
                    status="skipped",
                    error="No concrete version available within the candidate upper bound.",
                )
            )
            continue
        attempted_versions.append(str(probe_version))

        print(f"[cyan]{package_label} :: {dependency.name} -> <{candidate} (probe {probe_version})[/cyan]")
        success, error = _run_tasks(
            temp_pyproject.parent,
            workspace_root=temp_pyproject.parent.parent.parent,
            tasks=tasks,
            internal_editables=internal_editables,
            resolution="highest",
            dependency_pin=(dependency.name, probe_version),
            include_dev_group=include_dev_group,
            include_dev_extra=include_dev_extra,
            optional_extras=optional_extras,
            timeout_seconds=timeout_seconds,
        )
        if success:
            attempts.append(DependencyAttempt(trial_upper=str(candidate), status="passed"))
            final_requirements = [entry.with_upper(candidate) for entry in dependency.entries]
            break

        attempts.append(DependencyAttempt(trial_upper=str(candidate), status="failed", error=error))
        continue

    changed = final_requirements != dependency.original_requirements
    return DependencyOutcome(
        name=dependency.name,
        changed=changed,
        original_requirements=dependency.original_requirements,
        final_requirements=final_requirements,
        candidate_versions=candidate_versions,
        attempted_versions=attempted_versions,
        attempts=attempts,
    )


def _process_package(
    plan: PackagePlan,
    *,
    workspace_root: Path,
    catalog: VersionCatalog,
    dependency_filters: set[str] | None,
    dry_run: bool,
    max_candidates: int,
    timeout_seconds: int,
) -> PackageOutcome:
    pyproject_file = plan.pyproject_path
    source_workspace_root = workspace_root.resolve()
    available_tasks = extract_poe_tasks(pyproject_file)
    tasks = _select_validation_tasks(available_tasks)
    if not tasks:
        return PackageOutcome(
            project_path=str(plan.project_path),
            package_name=plan.package_name,
            tasks=[],
            changed=False,
            dependencies=[],
            replacements={},
            skipped=["No check/test task combination found."],
        )

    with tempfile.TemporaryDirectory(prefix=f"dep-range-{plan.project_path.name}-") as temp_dir:
        temp_root = Path(temp_dir)
        temp_workspace_root = temp_root / source_workspace_root.name
        # Copy the whole workspace so uv workspace sources and editable internal packages resolve
        # the same way they do in the real checkout while keeping trial rewrites fully isolated.
        shutil.copytree(
            source_workspace_root,
            temp_workspace_root,
            ignore=shutil.ignore_patterns(
                ".git",
                ".venv",
                "__pycache__",
                ".pytest_cache",
                ".mypy_cache",
                ".ruff_cache",
                "node_modules",
                "dist",
            ),
        )

        temp_packages_dir = temp_workspace_root / "packages"
        if temp_packages_dir.exists():
            for package_dir in temp_packages_dir.iterdir():
                if package_dir.is_dir() and not (package_dir / "pyproject.toml").exists():
                    shutil.rmtree(package_dir)

        temp_project_dir = temp_workspace_root / plan.project_path
        temp_pyproject = temp_project_dir / "pyproject.toml"
        temp_internal_editables: list[Path] = []
        for editable in plan.internal_editables:
            try:
                relative_editable = editable.resolve().relative_to(source_workspace_root)
            except ValueError:
                continue
            candidate = temp_workspace_root / relative_editable
            if candidate.exists():
                temp_internal_editables.append(candidate)

        dev_replacements = _collect_dev_pin_replacements(temp_pyproject, catalog=catalog)
        if dev_replacements:
            _replace_requirements(temp_pyproject, list(dev_replacements.items()))
            print(
                f"[cyan]{plan.project_path}: refreshed {len(dev_replacements)} dev dependency pin(s) to latest[/cyan]"
            )

        targets, skipped = _collect_targets(temp_pyproject, dependency_filters=dependency_filters)

        dependency_results: list[DependencyOutcome] = []
        replacements: dict[str, str] = dict(dev_replacements)
        package_label = f"{plan.project_path} ({plan.package_name})"

        if not targets:
            skipped.append("No eligible dependencies with upper bounds in project.dependencies.")

        # Run per-dependency trial generation + validation in the isolated temp workspace.
        for target in targets:
            versions = catalog.get(target.name)
            outcome = _optimize_dependency(
                temp_pyproject=temp_pyproject,
                dependency=target,
                available_versions=versions,
                tasks=tasks,
                internal_editables=temp_internal_editables,
                dry_run=dry_run,
                max_candidates=max_candidates,
                timeout_seconds=timeout_seconds,
                package_label=package_label,
                include_dev_group=plan.include_dev_group,
                include_dev_extra=plan.include_dev_extra,
                optional_extras=plan.optional_extras,
            )
            dependency_results.append(outcome)
            if outcome.changed:
                for old, new in zip(outcome.original_requirements, outcome.final_requirements, strict=True):
                    replacements[old] = new

        return PackageOutcome(
            project_path=str(plan.project_path),
            package_name=plan.package_name,
            tasks=tasks,
            changed=bool(replacements),
            dependencies=dependency_results,
            replacements=replacements,
            skipped=skipped,
        )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False))


def _to_json(package_outcome: PackageOutcome) -> dict:
    return {
        "project_path": package_outcome.project_path,
        "package_name": package_outcome.package_name,
        "tasks": package_outcome.tasks,
        "changed": package_outcome.changed,
        "skipped": package_outcome.skipped,
        "error": package_outcome.error,
        "dependencies": [
            {
                "name": dependency.name,
                "changed": dependency.changed,
                "original_requirements": dependency.original_requirements,
                "final_requirements": dependency.final_requirements,
                "candidate_versions": dependency.candidate_versions,
                "attempted_versions": dependency.attempted_versions,
                "skipped_reason": dependency.skipped_reason,
                "attempts": [
                    {
                        "trial_upper": attempt.trial_upper,
                        "status": attempt.status,
                        "error": attempt.error,
                    }
                    for attempt in dependency.attempts
                ],
            }
            for dependency in package_outcome.dependencies
        ],
    }


def _apply_package_replacements(path: Path, replacements: dict[str, str]) -> None:
    if not replacements:
        return
    _replace_requirements(path, list(replacements.items()))
    _format_dependency_arrays_multiline(path)


def main() -> None:
    """Run package-by-package dependency upper-bound discovery and updates."""
    parser = argparse.ArgumentParser(
        description=(
            "Raise dependency upper bounds per package, refresh dev pins to latest exact versions, "
            "run check+test in isolated uv envs, and write a JSON report while updating pyproject files."
        )
    )
    parser.add_argument(
        "--packages",
        nargs="*",
        default=None,
        help="Optional package filters by short name (for example core), workspace path, or package name.",
    )
    parser.add_argument(
        "--dependencies",
        nargs="*",
        default=None,
        help="Optional dependency-name filters (normalized to lowercase).",
    )
    parser.add_argument(
        "--parallelism",
        type=int,
        default=max(1, min(os.cpu_count() or 4, 8)),
        help="Number of packages to process concurrently.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=0,
        help="Maximum candidate upper bounds per dependency (0 = no limit).",
    )
    parser.add_argument(
        "--output-json",
        default="scripts/dependencies/dependency-range-results.json",
        help="Path to incremental JSON output report.",
    )
    parser.add_argument(
        "--version-source",
        choices=("pypi", "lock"),
        default="pypi",
        help="Version source for candidate upper bounds.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1200,
        help="Timeout per task command execution.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate candidates but do not update pyprojects.")
    args = parser.parse_args()

    # Preparation/target collection: resolve workspace metadata and package execution plans
    # up front so each worker can operate independently on a package-local temp copy.
    workspace_pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    workspace_root = workspace_pyproject.parent
    package_filters = {value for value in (args.packages or []) if value and value != "*"} or None
    dependency_filters = {name.lower() for name in args.dependencies} if args.dependencies else None
    output_json_path = (workspace_root / args.output_json).resolve()

    package_map = _build_workspace_package_map(workspace_root)
    internal_graph = _build_internal_graph(workspace_root, package_map)
    lock_versions = _load_lock_versions(workspace_root)
    catalog = VersionCatalog(lock_versions=lock_versions, source=args.version_source)

    plans: list[PackagePlan] = []
    for project_path in sorted(set(discover_projects(workspace_pyproject))):
        pyproject_file = workspace_root / project_path / "pyproject.toml"
        if not pyproject_file.exists():
            print(f"[yellow]Skipping {project_path}: missing pyproject.toml[/yellow]")
            continue
        package_name = _load_package_name(pyproject_file)
        with pyproject_file.open("rb") as f:
            package_config = tomli.load(f)
        project_section = package_config.get("project", {})
        optional_dependencies = project_section.get("optional-dependencies", {}) or {}
        dependency_groups = package_config.get("dependency-groups", {}) or {}
        # Reuse the shared selector matcher so direct optimizer runs accept the
        # same short-name package filters as the contributor-facing Poe tasks.
        if package_filters and not any(
            project_filter_matches(project_path, package_filter, [package_name]) for package_filter in package_filters
        ):
            continue
        plans.append(
            PackagePlan(
                project_path=project_path,
                package_name=package_name,
                pyproject_path=pyproject_file,
                internal_editables=_resolve_internal_editables(package_name, package_map, internal_graph),
                include_dev_group="dev" in dependency_groups,
                include_dev_extra="dev" in optional_dependencies,
                optional_extras=sorted(name for name in optional_dependencies if name not in {"all", "dev"}),
            )
        )

    root_package_name = _load_package_name(workspace_pyproject)
    with workspace_pyproject.open("rb") as f:
        root_config = tomli.load(f)
    root_project_section = root_config.get("project", {})
    root_optional_dependencies = root_project_section.get("optional-dependencies", {}) or {}
    root_dependency_groups = root_config.get("dependency-groups", {}) or {}
    if (
        not package_filters
        or "." in package_filters
        or "./" in package_filters
        or "root" in package_filters
        or root_package_name in package_filters
    ):
        plans.append(
            PackagePlan(
                project_path=Path("."),
                package_name=root_package_name,
                pyproject_path=workspace_pyproject,
                internal_editables=[],
                include_dev_group="dev" in root_dependency_groups,
                include_dev_extra="dev" in root_optional_dependencies,
                optional_extras=sorted(name for name in root_optional_dependencies if name not in {"all", "dev"}),
            )
        )

    if not plans:
        print("[yellow]No packages matched the selection.[/yellow]")
        return

    # Aggregation + persistence/reporting: initialize the incremental JSON report.
    report: dict = {
        "started_at": _utc_now(),
        "workspace_root": str(workspace_root),
        "version_source": args.version_source,
        "dry_run": args.dry_run,
        "packages": [],
        "summary": {
            "packages_total": len(plans),
            "packages_changed": 0,
            "dependencies_changed": 0,
        },
    }
    _write_json(output_json_path, report)
    print(f"[cyan]Writing dependency-range report to {output_json_path}[/cyan]")

    package_outcomes: list[PackageOutcome] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.parallelism)) as executor:
        future_to_plan = {
            executor.submit(
                _process_package,
                plan,
                workspace_root=workspace_root,
                catalog=catalog,
                dependency_filters=dependency_filters,
                dry_run=args.dry_run,
                max_candidates=args.max_candidates,
                timeout_seconds=args.timeout_seconds,
            ): plan
            for plan in plans
        }

        for future in concurrent.futures.as_completed(future_to_plan):
            plan = future_to_plan[future]
            try:
                outcome = future.result()
            except Exception as exc:
                outcome = PackageOutcome(
                    project_path=str(plan.project_path),
                    package_name=plan.package_name,
                    tasks=[],
                    changed=False,
                    dependencies=[],
                    replacements={},
                    skipped=[],
                    error=str(exc),
                )
            package_outcomes.append(outcome)

            if outcome.changed and not args.dry_run:
                _apply_package_replacements(plan.pyproject_path, outcome.replacements)

            # Persist each completed package outcome so long runs keep a live report.
            report["packages"].append(_to_json(outcome))
            report["summary"]["packages_changed"] = sum(1 for value in package_outcomes if value.changed)
            report["summary"]["dependencies_changed"] = sum(
                1 for value in package_outcomes for dependency in value.dependencies if dependency.changed
            )
            report["updated_at"] = _utc_now()
            _write_json(output_json_path, report)

            if outcome.error:
                print(f"[red]{plan.project_path}: package execution error[/red]")
            elif outcome.changed:
                print(f"[green]{plan.project_path}: updated dependency bounds[/green]")
            else:
                print(f"[yellow]{plan.project_path}: no changes[/yellow]")

    print(
        "[bold]Done.[/bold] "
        f"packages_changed={report['summary']['packages_changed']}, "
        f"dependencies_changed={report['summary']['dependencies_changed']}"
    )


if __name__ == "__main__":
    main()
