# Copyright (c) Microsoft. All rights reserved.
# ruff:file-ignore[suspicious-subprocess-import, subprocess-without-shell-equals-true]

"""Fast, lock-independent dependency-bound probes for Python release cuts."""

from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import tomli
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version
from rich import print

from scripts.task_runner import discover_projects, project_filter_matches

_PROBE_RESULT_PREFIX = "DEPENDENCY_BOUNDS_RELEASE_RESULT="
_RESOLUTION_SCENARIOS = (("lower", "lowest-direct"), ("upper", "highest"))


@dataclass
class ReleaseProject:
    """Published metadata needed to build a release probe."""

    project_path: Path
    package_name: str
    requires_python: str
    dependencies: tuple[str, ...]
    optional_dependencies: dict[str, tuple[str, ...]]
    import_modules: tuple[str, ...]


@dataclass
class ReleaseProbePlan:
    """One changed package and the local projects needed to resolve it."""

    project_path: Path
    package_name: str
    editable_specs: tuple[str, ...]
    import_modules: tuple[str, ...]
    reported_distributions: tuple[str, ...]
    python_version: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False))


def _truncate_error(stdout: str, stderr: str, *, max_chars: int = 3000) -> str:
    combined = "\n".join(part for part in (stderr.strip(), stdout.strip()) if part)
    if len(combined) <= max_chars:
        return combined
    return f"...\n{combined[-max_chars:]}"


def _string_requirements(values: object) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(value for value in cast(list[object], values) if isinstance(value, str))


def _discover_import_modules(project_path: Path, config: dict[str, Any]) -> tuple[str, ...]:
    """Discover top-level import names from the project's build configuration."""
    modules: set[str] = set()
    tool = cast(dict[str, Any], config.get("tool", {}) or {})

    flit = cast(dict[str, Any], tool.get("flit", {}) or {})
    flit_module_config = cast(dict[str, Any], flit.get("module", {}) or {})
    flit_module = flit_module_config.get("name")
    if isinstance(flit_module, str) and flit_module:
        modules.add(flit_module)

    hatch = cast(dict[str, Any], tool.get("hatch", {}) or {})
    hatch_build = cast(dict[str, Any], hatch.get("build", {}) or {})
    hatch_targets = cast(dict[str, Any], hatch_build.get("targets", {}) or {})
    hatch_wheel = cast(dict[str, Any], hatch_targets.get("wheel", {}) or {})
    hatch_packages = hatch_wheel.get("packages", [])
    if isinstance(hatch_packages, list):
        for package in cast(list[object], hatch_packages):
            if isinstance(package, str) and package:
                modules.add(Path(package).name.split(".", 1)[0])

    setuptools = cast(dict[str, Any], tool.get("setuptools", {}) or {})
    setuptools_packages = setuptools.get("packages", [])
    if isinstance(setuptools_packages, list):
        for package in cast(list[object], setuptools_packages):
            if isinstance(package, str) and package:
                modules.add(package.split(".", 1)[0])

    if not modules:
        for candidate in project_path.glob("agent_framework*"):
            if candidate.is_dir() and (candidate / "__init__.py").exists():
                modules.add(candidate.name)
            elif candidate.is_file() and candidate.suffix == ".py":
                modules.add(candidate.stem)

    return tuple(sorted(modules))


def _load_release_project(workspace_root: Path, project_path: Path) -> ReleaseProject:
    pyproject_file = workspace_root / project_path / "pyproject.toml"
    with pyproject_file.open("rb") as file:
        config = tomli.load(file)

    project = cast(dict[str, Any], config.get("project", {}) or {})
    package_name = str(project.get("name", "")).strip()
    if not package_name:
        raise RuntimeError(f"Missing project.name in {pyproject_file}")
    requires_python = str(project.get("requires-python", "")).strip()
    if not requires_python:
        raise RuntimeError(f"Missing project.requires-python in {pyproject_file}")

    optional_dependencies: dict[str, tuple[str, ...]] = {}
    optional_config = cast(dict[str, object], project.get("optional-dependencies", {}) or {})
    for extra_name, requirements in optional_config.items():
        optional_dependencies[extra_name] = _string_requirements(requirements)

    return ReleaseProject(
        project_path=project_path,
        package_name=package_name,
        requires_python=requires_python,
        dependencies=_string_requirements(project.get("dependencies", [])),
        optional_dependencies=optional_dependencies,
        import_modules=_discover_import_modules(pyproject_file.parent, config),
    )


def _build_release_project_map(workspace_root: Path) -> dict[str, ReleaseProject]:
    project_paths = [Path("."), *sorted(set(discover_projects(workspace_root / "pyproject.toml")))]
    projects: dict[str, ReleaseProject] = {}
    for project_path in project_paths:
        pyproject_file = workspace_root / project_path / "pyproject.toml"
        if not pyproject_file.exists():
            continue
        project = _load_release_project(workspace_root, project_path)
        projects[canonicalize_name(project.package_name)] = project
    return projects


def _changed_release_project_paths(workspace_root: Path, base_ref: str) -> set[Path]:
    command = [
        "git",
        "diff",
        "--relative",
        "--name-only",
        "--diff-filter=ACMR",
        base_ref,
        "--",
        "pyproject.toml",
        "packages/*/pyproject.toml",
    ]
    result = subprocess.run(command, cwd=workspace_root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        error = _truncate_error(result.stdout, result.stderr)
        raise RuntimeError(f"Unable to compare release metadata with {base_ref}.\n{error}")

    project_paths: set[Path] = set()
    for line in result.stdout.splitlines():
        changed_file = Path(line.strip())
        if changed_file == Path("pyproject.toml"):
            project_paths.add(Path("."))
        elif len(changed_file.parts) == 3 and changed_file.parts[0] == "packages":
            project_paths.add(changed_file.parent)
    return project_paths


def _selected_release_projects(
    *,
    workspace_root: Path,
    projects: dict[str, ReleaseProject],
    base_ref: str,
    package_filter: str | None,
) -> list[ReleaseProject]:
    if package_filter:
        selected = [
            project
            for project in projects.values()
            if project_filter_matches(project.project_path, package_filter, [project.package_name])
        ]
    else:
        changed_paths = _changed_release_project_paths(workspace_root, base_ref)
        selected = [project for project in projects.values() if project.project_path in changed_paths]

    return sorted(selected, key=lambda project: str(project.project_path))


def _requirements_for_extras(project: ReleaseProject, extras: set[str]) -> tuple[str, ...]:
    requirements = list(project.dependencies)
    for extra_name in sorted(extras):
        requirements.extend(project.optional_dependencies.get(extra_name, ()))
    return tuple(requirements)


def _minimum_python_version(projects: list[ReleaseProject]) -> str:
    """Return the lowest Python minor supported by every project in a probe closure."""
    constraints = [project.requires_python for project in projects]
    combined = SpecifierSet(",".join(constraints))
    lower_bounds = [
        Version(specifier.version.rstrip(".*"))
        for specifier in combined
        if specifier.operator in {">", ">=", "~=", "=="} and specifier.version.rstrip(".*")
    ]
    if not lower_bounds:
        package_names = ", ".join(sorted(project.package_name for project in projects))
        raise RuntimeError(f"Unable to derive a Python floor from requires-python for: {package_names}")

    floor = max(lower_bounds)
    python_version = f"{floor.major}.{floor.minor}"
    first_patch = Version(python_version)
    later_patch = Version(f"{python_version}.999999")
    if first_patch not in combined and later_patch not in combined:
        package_names = ", ".join(sorted(project.package_name for project in projects))
        raise RuntimeError(
            f"No Python {python_version} interpreter satisfies the combined requires-python constraints for: "
            f"{package_names}"
        )
    return python_version


def _build_release_probe_plan(
    workspace_root: Path,
    target: ReleaseProject,
    projects: dict[str, ReleaseProject],
) -> ReleaseProbePlan:
    """Build the exact internal editable closure for one changed package."""
    target_name = canonicalize_name(target.package_name)
    # Development extras are contributor tooling, not runtime compatibility surface.
    requested_extras: dict[str, set[str]] = {
        target_name: {extra for extra in target.optional_dependencies if extra != "dev"}
    }
    processed_extras: dict[str, set[str]] = {}
    pending = [target_name]

    while pending:
        package_name = pending.pop()
        project = projects[package_name]
        extras = requested_extras[package_name]
        if processed_extras.get(package_name) == extras:
            continue
        processed_extras[package_name] = set(extras)

        for requirement_text in _requirements_for_extras(project, extras):
            try:
                requirement = Requirement(requirement_text)
            except InvalidRequirement:
                continue
            dependency_name = canonicalize_name(requirement.name)
            if dependency_name not in projects:
                continue
            previous = requested_extras.setdefault(dependency_name, set())
            updated = previous | set(requirement.extras)
            if dependency_name not in processed_extras or updated != previous:
                requested_extras[dependency_name] = updated
                pending.append(dependency_name)

    target_extras = sorted(requested_extras[target_name])
    target_path = (workspace_root / target.project_path).resolve()
    target_spec = str(target_path)
    if target_extras:
        target_spec = f"{target_spec}[{','.join(target_extras)}]"

    editable_specs = [target_spec]
    for package_name in sorted(requested_extras):
        if package_name == target_name:
            continue
        editable_specs.append(str((workspace_root / projects[package_name].project_path).resolve()))

    target_requirements = _requirements_for_extras(target, set(target_extras))
    reported_distributions = {canonicalize_name(target.package_name)}
    for requirement_text in target_requirements:
        try:
            reported_distributions.add(canonicalize_name(Requirement(requirement_text).name))
        except InvalidRequirement:
            continue

    return ReleaseProbePlan(
        project_path=target.project_path,
        package_name=target.package_name,
        editable_specs=tuple(editable_specs),
        import_modules=target.import_modules,
        reported_distributions=tuple(sorted(reported_distributions)),
        python_version=_minimum_python_version([projects[package_name] for package_name in requested_extras]),
    )


def _build_release_probe_command(
    plan: ReleaseProbePlan,
    *,
    resolution: str,
    python_override: str | None = None,
) -> list[str]:
    probe_script = f"""
import importlib
import json
from importlib.metadata import PackageNotFoundError, version

modules = {plan.import_modules!r}
distributions = {plan.reported_distributions!r}
for module_name in modules:
    importlib.import_module(module_name)
versions = {{}}
for distribution_name in distributions:
    try:
        versions[distribution_name] = version(distribution_name)
    except PackageNotFoundError:
        versions[distribution_name] = None
print({_PROBE_RESULT_PREFIX!r} + json.dumps({{"imports": modules, "versions": versions}}, sort_keys=True))
"""
    command = [
        "uv",
        "--no-progress",
        "run",
        "--isolated",
        "--no-project",
        "--python",
        python_override or plan.python_version,
        "--resolution",
        resolution,
        "--prerelease",
        "if-necessary-or-explicit",
        "--quiet",
    ]
    for editable_spec in plan.editable_specs:
        command.extend(["--with-editable", editable_spec])
    command.extend(["python", "-c", probe_script])
    return command


def _parse_probe_payload(stdout: str) -> dict[str, Any] | None:
    for line in reversed(stdout.splitlines()):
        if line.startswith(_PROBE_RESULT_PREFIX):
            try:
                payload = json.loads(line.removeprefix(_PROBE_RESULT_PREFIX))
            except json.JSONDecodeError:
                return None
            return cast(dict[str, Any], payload) if isinstance(payload, dict) else None
    return None


def _run_release_probe(
    plan: ReleaseProbePlan,
    *,
    scenario_name: str,
    resolution: str,
    python_override: str | None,
    deadline: float,
    dry_run: bool,
) -> dict[str, Any]:
    python_version = python_override or plan.python_version
    command = _build_release_probe_command(plan, resolution=resolution, python_override=python_override)
    started = time.monotonic()
    if dry_run:
        print(f"[cyan]DRY RUN[/cyan] {' '.join(command)}")
        return {
            "project_path": str(plan.project_path),
            "package_name": plan.package_name,
            "scenario": scenario_name,
            "resolution": resolution,
            "python": python_version,
            "status": "dry-run",
            "duration_seconds": 0.0,
            "payload": None,
            "error": None,
        }

    remaining_seconds = deadline - started
    if remaining_seconds <= 0:
        return {
            "project_path": str(plan.project_path),
            "package_name": plan.package_name,
            "scenario": scenario_name,
            "resolution": resolution,
            "python": python_version,
            "status": "failed",
            "duration_seconds": 0.0,
            "payload": None,
            "error": "The shared release-validation deadline elapsed before this probe started.",
        }

    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=remaining_seconds,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "project_path": str(plan.project_path),
            "package_name": plan.package_name,
            "scenario": scenario_name,
            "resolution": resolution,
            "python": python_version,
            "status": "failed",
            "duration_seconds": round(time.monotonic() - started, 3),
            "payload": None,
            "error": f"Release probe exceeded the shared deadline.\n{_truncate_error(stdout, stderr)}",
        }

    payload = _parse_probe_payload(result.stdout) if result.returncode == 0 else None
    error = None
    if result.returncode != 0:
        error = _truncate_error(result.stdout, result.stderr)
    elif payload is None:
        error = "Probe completed without emitting its dependency-version payload."

    return {
        "project_path": str(plan.project_path),
        "package_name": plan.package_name,
        "scenario": scenario_name,
        "resolution": resolution,
        "python": python_version,
        "status": "passed" if error is None else "failed",
        "duration_seconds": round(time.monotonic() - started, 3),
        "payload": payload,
        "error": error,
    }


def _refresh_lockfile(
    *,
    workspace_root: Path,
    deadline: float,
    dry_run: bool,
) -> dict[str, Any]:
    command = ["uv", "lock", "--prerelease", "if-necessary-or-explicit"]
    if dry_run:
        print(f"[cyan]DRY RUN[/cyan] {' '.join(command)}")
        return {"status": "dry-run", "duration_seconds": 0.0, "error": None}

    started = time.monotonic()
    remaining_seconds = deadline - started
    if remaining_seconds <= 0:
        return {
            "status": "failed",
            "duration_seconds": 0.0,
            "error": "The shared release-validation deadline elapsed before uv.lock refresh started.",
        }
    try:
        result = subprocess.run(
            command,
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=remaining_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "status": "failed",
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": f"uv.lock refresh exceeded the shared deadline.\n{_truncate_error(stdout, stderr)}",
        }

    error = None if result.returncode == 0 else _truncate_error(result.stdout, result.stderr)
    return {
        "status": "passed" if error is None else "failed",
        "duration_seconds": round(time.monotonic() - started, 3),
        "error": error,
    }


def run_release_mode(
    *,
    workspace_root: Path,
    base_ref: str,
    package_filter: str | None,
    parallelism: int,
    python_override: str | None,
    deadline_seconds: int,
    dry_run: bool,
    output_json: Path,
) -> int:
    """Run fast lower/upper release probes for changed package metadata."""
    deadline = time.monotonic() + deadline_seconds
    projects = _build_release_project_map(workspace_root)
    selected = _selected_release_projects(
        workspace_root=workspace_root,
        projects=projects,
        base_ref=base_ref,
        package_filter=package_filter,
    )
    if not selected:
        print(f"[red]No changed package pyproject.toml files found relative to {base_ref}.[/red]")
        return 1

    lock_result = _refresh_lockfile(workspace_root=workspace_root, deadline=deadline, dry_run=dry_run)
    if lock_result["status"] == "failed":
        print("[red]uv.lock refresh failed.[/red]")
        print(f"[red]{lock_result['error']}[/red]")
        return 1

    plans = [_build_release_probe_plan(workspace_root, project, projects) for project in selected]
    work_items = [
        (plan, scenario_name, resolution) for plan in plans for scenario_name, resolution in _RESOLUTION_SCENARIOS
    ]
    report: dict[str, Any] = {
        "started_at": _utc_now(),
        "mode": "release",
        "workspace_root": str(workspace_root),
        "base_ref": base_ref,
        "python_override": python_override,
        "deadline_seconds": deadline_seconds,
        "dry_run": dry_run,
        "lockfile": lock_result,
        "packages": [str(plan.project_path) for plan in plans],
        "probes": [],
        "summary": {"probes_total": len(work_items), "probes_passed": 0, "probes_failed": 0},
    }
    _write_json(output_json, report)
    print(
        f"[bold]Running {len(work_items)} lock-independent release probes for {len(plans)} package(s) "
        f"with a shared {deadline_seconds}s deadline[/bold]"
    )
    print(f"[cyan]Writing dependency-bounds release report to {output_json}[/cyan]")

    max_workers = max(1, min(parallelism, len(work_items)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _run_release_probe,
                plan,
                scenario_name=scenario_name,
                resolution=resolution,
                python_override=python_override,
                deadline=deadline,
                dry_run=dry_run,
            )
            for plan, scenario_name, resolution in work_items
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            report["probes"].append(result)
            if result["status"] in {"passed", "dry-run"}:
                report["summary"]["probes_passed"] += 1
                print(
                    f"[green]{result['project_path']}: {result['scenario']} passed on Python {result['python']} "
                    f"({result['duration_seconds']:.1f}s)[/green]"
                )
            else:
                report["summary"]["probes_failed"] += 1
                print(f"[red]{result['project_path']}: {result['scenario']} failed[/red]")
                print(f"[red]{result['error']}[/red]")
            report["updated_at"] = _utc_now()
            _write_json(output_json, report)

    if report["summary"]["probes_failed"]:
        print("[bold red]Release dependency-bound validation failed.[/bold red]")
        return 1
    print("[bold green]Release dependency-bound validation completed successfully.[/bold green]")
    return 0
