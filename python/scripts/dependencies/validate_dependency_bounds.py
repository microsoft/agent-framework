# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: S404, S603

"""Unified dependency-bound validation entrypoint.

Modes:
- test: run workspace-wide compatibility gates at lower and upper resolutions.
- lower: run lower-bound expansion for one package.
- upper: run upper-bound expansion for one package.
- both: run lower then upper expansion for one package.

Package filters intentionally reuse the root task selector semantics so the
same short package names (for example ``core``) work in both contributor
commands and direct debugging entrypoints.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import tomli
from rich import print

from scripts.dependencies._dependency_bounds_runtime import (
    extend_command_with_runtime_tools,
    extend_command_with_task,
)
from scripts.dependencies._dependency_bounds_upper_impl import (
    _build_internal_graph,
    _build_workspace_package_map,
    _load_package_name,
    _resolve_internal_editables,
)
from scripts.task_runner import discover_projects, extract_poe_tasks, project_filter_matches

_LOWER_IMPL_MODULE = "scripts.dependencies._dependency_bounds_lower_impl"
_UPPER_IMPL_MODULE = "scripts.dependencies._dependency_bounds_upper_impl"


@dataclass
class PackageTestPlan:
    """Workspace package settings needed for global test-mode validation."""

    project_path: Path
    package_name: str
    include_dev_group: bool
    include_dev_extra: bool
    optional_extras: list[str]
    internal_editables: list[Path]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate_error(stdout: str, stderr: str, *, max_chars: int = 2000) -> str:
    combined = "\n".join(part for part in [stderr.strip(), stdout.strip()] if part)
    if len(combined) <= max_chars:
        return combined
    return f"...\n{combined[-max_chars:]}"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False))


def _coerce_subprocess_output(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode(errors="replace")
    return output


def _build_test_plans(workspace_root: Path, package_filter: str | None) -> list[PackageTestPlan]:
    """Build per-package test plans for the requested workspace selector."""
    workspace_pyproject = workspace_root / "pyproject.toml"
    package_map = _build_workspace_package_map(workspace_root)
    internal_graph = _build_internal_graph(workspace_root, package_map)

    plans: list[PackageTestPlan] = []
    missing_tasks: list[str] = []
    for project_path in sorted(set(discover_projects(workspace_pyproject))):
        pyproject_file = workspace_root / project_path / "pyproject.toml"
        if not pyproject_file.exists():
            continue

        package_name = _load_package_name(pyproject_file)
        # Reuse the shared matcher so dependency-bound test mode accepts the
        # same short names and legacy path-style selectors as the root Poe
        # commands.
        if (
            package_filter
            and package_filter != "*"
            and not project_filter_matches(project_path, package_filter, [package_name])
        ):
            continue

        available_tasks = extract_poe_tasks(pyproject_file)
        required_tasks = {"test", "pyright"}
        if not required_tasks.issubset(available_tasks):
            missing = sorted(required_tasks - available_tasks)
            missing_tasks.append(f"{project_path}: missing {', '.join(missing)}")
            continue
        with pyproject_file.open("rb") as f:
            package_config = tomli.load(f)
        project_section = package_config.get("project", {})
        optional_dependencies = project_section.get("optional-dependencies", {}) or {}
        dependency_groups = package_config.get("dependency-groups", {}) or {}

        plans.append(
            PackageTestPlan(
                project_path=project_path,
                package_name=package_name,
                include_dev_group="dev" in dependency_groups,
                include_dev_extra="dev" in optional_dependencies,
                optional_extras=sorted(name for name in optional_dependencies if name not in {"all", "dev"}),
                internal_editables=_resolve_internal_editables(package_name, package_map, internal_graph),
            )
        )

    if missing_tasks:
        details = "\n".join(missing_tasks)
        raise RuntimeError(f"Test mode requires test+pyright in every package.\n{details}")
    return plans


def _run_package_tasks(
    workspace_root: Path,
    plan: PackageTestPlan,
    *,
    resolution: str,
    timeout_seconds: int,
    dry_run: bool,
) -> tuple[bool, str | None]:
    # Test mode intentionally uses the same isolated uv execution model as the optimizer scripts
    # so the smoke gate matches the environment that lower/upper probes will run in.
    env = dict(os.environ)
    env["UV_PRERELEASE"] = "allow"
    # Avoid letting nested uv commands target the caller's active environment; validation should
    # stay inside uv's isolated throwaway environment instead of mutating `.venv`.
    env.pop("VIRTUAL_ENV", None)

    for task_name in ("test", "pyright"):
        command = [
            "uv",
            "--no-progress",
            "--directory",
            str(workspace_root / plan.project_path),
            "run",
            "--isolated",
            "--resolution",
            resolution,
            "--prerelease",
            "allow",
            "--quiet",
        ]
        extend_command_with_runtime_tools(command, workspace_root)
        if plan.include_dev_group:
            command.extend(["--group", "dev"])
        if plan.include_dev_extra:
            command.extend(["--extra", "dev"])
        for extra_name in plan.optional_extras:
            command.extend(["--extra", extra_name])
        for editable_path in plan.internal_editables:
            command.extend(["--with-editable", str(editable_path)])
        extend_command_with_task(command, task_name)

        if dry_run:
            print(f"[cyan]DRY RUN[/cyan] {' '.join(command)}")
            continue

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            error_message = _truncate_error(
                _coerce_subprocess_output(exc.stdout),
                _coerce_subprocess_output(exc.stderr),
            )
            if not error_message:
                error_message = "Process timed out without additional output."
            return (
                False,
                (
                    f"Task '{task_name}' timed out for {plan.project_path} at resolution '{resolution}' "
                    f"after {timeout_seconds} seconds.\n{error_message}"
                ),
            )
        if result.returncode != 0:
            error_message = _truncate_error(result.stdout, result.stderr)
            return (
                False,
                f"Task '{task_name}' failed for {plan.project_path} at resolution '{resolution}'.\n{error_message}",
            )
    return True, None


def _run_test_mode(
    *,
    workspace_root: Path,
    package_filter: str | None,
    timeout_seconds: int,
    dry_run: bool,
    output_json: Path,
) -> int:
    plans = _build_test_plans(workspace_root, package_filter)
    if not plans:
        print("[yellow]No workspace packages found for test mode.[/yellow]")
        return 0

    report: dict = {
        "started_at": _utc_now(),
        "mode": "test",
        "workspace_root": str(workspace_root),
        "dry_run": dry_run,
        "scenarios": [],
        "summary": {
            "packages_total": len(plans),
            "scenarios_passed": 0,
            "scenarios_failed": 0,
        },
    }
    _write_json(output_json, report)
    print(f"[cyan]Writing dependency-bounds test report to {output_json}[/cyan]")

    # Smoke both ends of the allowed range: `lowest-direct` approximates lower-bound resolution,
    # while `highest` exercises the newest versions currently permitted by each package's specifiers.
    scenario_specs = [("lower", "lowest-direct"), ("upper", "highest")]
    for scenario_name, resolution in scenario_specs:
        print(f"[bold]Running {scenario_name} scenario ({resolution})[/bold]")
        scenario_result: dict = {
            "name": scenario_name,
            "resolution": resolution,
            "status": "passed",
            "packages": [],
        }
        for plan in plans:
            success, error = _run_package_tasks(
                workspace_root,
                plan,
                resolution=resolution,
                timeout_seconds=timeout_seconds,
                dry_run=dry_run,
            )
            scenario_result["packages"].append(
                {
                    "project_path": str(plan.project_path),
                    "package_name": plan.package_name,
                    "status": "passed" if success else "failed",
                    "error": error,
                }
            )
            if success:
                print(f"[green]{plan.project_path}: {scenario_name} passed[/green]")
                continue

            scenario_result["status"] = "failed"
            report["scenarios"].append(scenario_result)
            report["summary"]["scenarios_failed"] += 1
            report["updated_at"] = _utc_now()
            _write_json(output_json, report)
            print(f"[red]{plan.project_path}: {scenario_name} failed[/red]")
            print(f"[red]{error}[/red]")
            return 1

        report["scenarios"].append(scenario_result)
        report["summary"]["scenarios_passed"] += 1
        report["updated_at"] = _utc_now()
        _write_json(output_json, report)

    print("[bold green]Test mode completed successfully.[/bold green]")
    return 0


def _build_optimizer_command(
    *,
    workspace_root: Path,
    module_name: str,
    package: str | None,
    dependencies: list[str] | None,
    parallelism: int,
    max_candidates: int,
    version_source: str,
    timeout_seconds: int,
    dry_run: bool,
    output_json: str | None,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        module_name,
        "--parallelism",
        str(parallelism),
        "--max-candidates",
        str(max_candidates),
        "--version-source",
        version_source,
        "--timeout-seconds",
        str(timeout_seconds),
    ]
    if package:
        command.extend(["--packages", package])
    if dependencies:
        command.extend(["--dependencies", *dependencies])
    if output_json:
        command.extend(["--output-json", output_json])
    if dry_run:
        command.append("--dry-run")
    return command


def _run_optimizer_mode(
    *,
    workspace_root: Path,
    module_name: str,
    package: str | None,
    dependencies: list[str] | None,
    parallelism: int,
    max_candidates: int,
    version_source: str,
    timeout_seconds: int,
    dry_run: bool,
    output_json: str | None,
) -> int:
    command = _build_optimizer_command(
        workspace_root=workspace_root,
        module_name=module_name,
        package=package,
        dependencies=dependencies,
        parallelism=parallelism,
        max_candidates=max_candidates,
        version_source=version_source,
        timeout_seconds=timeout_seconds,
        dry_run=dry_run,
        output_json=output_json,
    )
    print(f"[cyan]Running:[/cyan] {' '.join(command)}")
    result = subprocess.run(command, cwd=workspace_root, check=False)
    return result.returncode


def _with_suffix(path: str | None, suffix: str) -> str | None:
    if path is None:
        return None
    value = Path(path)
    return str(value.with_name(f"{value.stem}-{suffix}{value.suffix}"))


def main() -> None:
    """Parse arguments and run the requested dependency-bound mode."""
    parser = argparse.ArgumentParser(
        description=(
            "Unified dependency-bound workflow. Use mode=test for workspace-wide lower+upper gates, "
            "or lower/upper/both for package-scoped or workspace-wide bound expansion."
        )
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=("test", "lower", "upper", "both"),
        help="Execution mode: test (global) or lower/upper/both (package-scoped).",
    )
    parser.add_argument(
        "--package",
        default=None,
        help=(
            "Optional workspace package selector for all modes, such as `core`. "
            "Use '*' or omit it for the whole workspace."
        ),
    )
    parser.add_argument(
        "--dependencies",
        nargs="*",
        default=None,
        help="Optional dependency-name filters for lower/upper/both. Omit to process all matching dependencies.",
    )
    parser.add_argument(
        "--parallelism",
        type=int,
        default=max(1, min(os.cpu_count() or 4, 8)),
        help="Parallelism forwarded to lower/upper optimizer scripts.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=0,
        help="Maximum candidate bounds per dependency for lower/upper optimizer scripts (0 = no limit).",
    )
    parser.add_argument(
        "--version-source",
        choices=("pypi", "lock"),
        default="pypi",
        help="Version source for candidate bounds.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1200,
        help="Timeout per task command execution.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not execute mutating actions.")
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional output report path for lower/upper modes (both mode appends -lower/-upper).",
    )
    parser.add_argument(
        "--test-output-json",
        default="scripts/dependencies/dependency-bounds-test-results.json",
        help="Output report path for test mode.",
    )
    args = parser.parse_args()

    workspace_root = Path(__file__).resolve().parents[2]
    normalized_package = None if args.package in {None, "", "*"} else args.package

    if args.mode == "test":
        exit_code = _run_test_mode(
            workspace_root=workspace_root,
            package_filter=normalized_package,
            timeout_seconds=args.timeout_seconds,
            dry_run=args.dry_run,
            output_json=(workspace_root / args.test_output_json).resolve(),
        )
        raise SystemExit(exit_code)

    if args.mode == "lower":
        exit_code = _run_optimizer_mode(
            workspace_root=workspace_root,
            module_name=_LOWER_IMPL_MODULE,
            package=normalized_package,
            dependencies=args.dependencies,
            parallelism=args.parallelism,
            max_candidates=args.max_candidates,
            version_source=args.version_source,
            timeout_seconds=args.timeout_seconds,
            dry_run=args.dry_run,
            output_json=args.output_json,
        )
        raise SystemExit(exit_code)

    if args.mode == "upper":
        exit_code = _run_optimizer_mode(
            workspace_root=workspace_root,
            module_name=_UPPER_IMPL_MODULE,
            package=normalized_package,
            dependencies=args.dependencies,
            parallelism=args.parallelism,
            max_candidates=args.max_candidates,
            version_source=args.version_source,
            timeout_seconds=args.timeout_seconds,
            dry_run=args.dry_run,
            output_json=args.output_json,
        )
        raise SystemExit(exit_code)

    # Lower runs first so the subsequent upper pass starts from the widest lower bound that has
    # already been validated; when `--output-json` is supplied, each pass gets its own suffixed report.
    lower_exit = _run_optimizer_mode(
        workspace_root=workspace_root,
        module_name=_LOWER_IMPL_MODULE,
        package=normalized_package,
        dependencies=args.dependencies,
        parallelism=args.parallelism,
        max_candidates=args.max_candidates,
        version_source=args.version_source,
        timeout_seconds=args.timeout_seconds,
        dry_run=args.dry_run,
        output_json=_with_suffix(args.output_json, "lower"),
    )
    if lower_exit != 0:
        raise SystemExit(lower_exit)

    upper_exit = _run_optimizer_mode(
        workspace_root=workspace_root,
        module_name=_UPPER_IMPL_MODULE,
        package=normalized_package,
        dependencies=args.dependencies,
        parallelism=args.parallelism,
        max_candidates=args.max_candidates,
        version_source=args.version_source,
        timeout_seconds=args.timeout_seconds,
        dry_run=args.dry_run,
        output_json=_with_suffix(args.output_json, "upper"),
    )
    raise SystemExit(upper_exit)


if __name__ == "__main__":
    main()
