# Copyright (c) Microsoft. All rights reserved.

"""Dispatch contributor-facing workspace tasks with consistent scope flags.

This script is the single root-task entrypoint used by ``python/pyproject.toml``.
It keeps selector semantics, aggregate-vs-fan-out behaviour, and compatibility
aliases in one place so docs and automation can share the same command surface.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import tomli
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from rich import print
from task_runner import build_work_items, discover_projects, project_filter_matches, run_tasks

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_PYPROJECT = WORKSPACE_ROOT / "pyproject.toml"
CURRENT_PYTHON = Version(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
SAMPLE_EXCLUDES = "samples/autogen-migration,samples/semantic-kernel-migration"
SAMPLE_RUFF_IGNORE = "E501,ASYNC,B901,TD002"
MARKDOWN_EXCLUDES = [
    "cookiecutter-agent-framework-lab",
    "tau2",
    "packages/devui/frontend",
    "context_providers/azure_ai_search",
]
DEFAULT_AGGREGATE_TEST_EXCLUDES = {"devui", "lab"}


@dataclass(frozen=True)
class WorkspaceProject:
    """Metadata about a workspace package."""

    path: Path
    name: str
    distribution_name: str
    requires_python: str | None


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    """Parse the workspace command and return any pass-through arguments."""
    parser = argparse.ArgumentParser(description="Dispatch workspace Poe tasks with consistent scope flags.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_project_option(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "-P",
            "--package",
            dest="project",
            default="*",
            metavar="PACKAGE",
            help="Workspace package selector or glob pattern, such as `core`.",
        )
        # Keep a hidden compatibility alias while old automation and local
        # muscle memory migrate from ``--project`` to ``--package``.
        command.add_argument("--project", dest="project", help=argparse.SUPPRESS)

    def add_syntax_mode_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("-F", "--format", action="store_true", help="Run formatting only.")
        command.add_argument("-C", "--check", action="store_true", help="Run lint checks only.")

    def add_all_option(command: argparse.ArgumentParser) -> None:
        command.add_argument("-A", "--all", action="store_true", help="Run a single aggregate workspace sweep.")

    def add_samples_option(command: argparse.ArgumentParser) -> None:
        command.add_argument("-S", "--samples", action="store_true", help="Target samples/ instead of packages.")

    def add_cov_option(command: argparse.ArgumentParser) -> None:
        command.add_argument("-C", "--cov", action="store_true", help="Enable coverage output.")

    syntax = subparsers.add_parser("syntax")
    add_project_option(syntax)
    add_samples_option(syntax)
    add_syntax_mode_options(syntax)

    for command_name in ("fmt", "build", "clean-dist", "check-packages"):
        command = subparsers.add_parser(command_name)
        add_project_option(command)

    lint = subparsers.add_parser("lint")
    add_project_option(lint)
    add_samples_option(lint)

    pyright = subparsers.add_parser("pyright")
    add_project_option(pyright)
    add_all_option(pyright)
    add_samples_option(pyright)

    mypy = subparsers.add_parser("mypy")
    add_project_option(mypy)
    add_all_option(mypy)

    typing = subparsers.add_parser("typing")
    add_project_option(typing)
    add_all_option(typing)

    test = subparsers.add_parser("test")
    add_project_option(test)
    add_all_option(test)
    add_cov_option(test)

    check = subparsers.add_parser("check")
    add_project_option(check)
    add_samples_option(check)

    prek_check = subparsers.add_parser("prek-check")
    prek_check.add_argument("files", nargs="*", default=["."], help="Files reported by pre-commit.")

    subparsers.add_parser("ci-mypy")

    return parser.parse_known_args(argv)


def load_toml(file_path: Path) -> dict:
    """Load a TOML file."""
    with file_path.open("rb") as file:
        return tomli.load(file)


def discover_workspace_projects() -> list[WorkspaceProject]:
    """Return workspace packages together with their Python-version metadata."""
    projects: list[WorkspaceProject] = []
    for project_path in discover_projects(WORKSPACE_PYPROJECT):
        pyproject = load_toml(WORKSPACE_ROOT / project_path / "pyproject.toml")
        requires_python = pyproject.get("project", {}).get("requires-python")
        distribution_name = str(pyproject.get("project", {}).get("name", "")).strip()
        projects.append(
            WorkspaceProject(
                path=project_path,
                name=project_path.name,
                distribution_name=distribution_name,
                requires_python=requires_python,
            )
        )
    return projects


def supports_current_python(project: WorkspaceProject) -> bool:
    """Return whether the current interpreter satisfies the project's Python requirement."""
    if not project.requires_python:
        return True
    return SpecifierSet(project.requires_python).contains(CURRENT_PYTHON, prereleases=True)


def select_projects(pattern: str) -> list[WorkspaceProject]:
    """Select supported workspace projects that match the supplied pattern.

    The shared matcher accepts short names such as ``core``, legacy path-style
    values, and distribution names so every root task family speaks the same
    selector dialect.
    """
    matched_projects = [
        project
        for project in discover_workspace_projects()
        if project_filter_matches(project.path, pattern, aliases=[project.name, project.distribution_name])
    ]
    if not matched_projects:
        print(f"[red]No workspace projects matched pattern '{pattern}'.[/red]")
        raise SystemExit(2)

    supported_projects = [project for project in matched_projects if supports_current_python(project)]
    unsupported_projects = [project.name for project in matched_projects if not supports_current_python(project)]
    if unsupported_projects:
        version = f"{sys.version_info.major}.{sys.version_info.minor}"
        print(
            "[yellow]Skipping packages not supported by "
            f"Python {version}: {', '.join(sorted(unsupported_projects))}[/yellow]"
        )

    return supported_projects


def relative_path(path: Path) -> str:
    """Convert a workspace path to a stable relative string."""
    return path.relative_to(WORKSPACE_ROOT).as_posix()


def collect_source_dirs(projects: list[WorkspaceProject]) -> list[Path]:
    """Collect top-level import package directories for the selected projects."""
    source_dirs: set[Path] = set()
    for project in projects:
        project_root = WORKSPACE_ROOT / project.path
        for init_file in project_root.rglob("__init__.py"):
            package_dir = init_file.parent
            if package_dir.name.startswith("agent_framework"):
                source_dirs.add(package_dir)
    return sorted(source_dirs)


def collect_test_dirs(projects: list[WorkspaceProject]) -> list[Path]:
    """Collect test directories for the selected projects."""
    test_dirs: set[Path] = set()
    for project in projects:
        project_root = WORKSPACE_ROOT / project.path
        for directory_name in ("tests", "ag_ui_tests"):
            for test_dir in project_root.rglob(directory_name):
                relative_test_dir = test_dir.relative_to(project_root)
                # Ignore hidden/generated trees such as ``.mypy_cache`` so the
                # aggregate sweep only targets real repository test directories.
                if test_dir.is_dir() and not any(part.startswith(".") for part in relative_test_dir.parts):
                    test_dirs.add(test_dir)
    return sorted(test_dirs)


def run_command(command: list[str]) -> None:
    """Run a subprocess from the workspace root and stream its output."""
    result = subprocess.run(command, cwd=WORKSPACE_ROOT, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)


def run_fan_out(task_names: list[str], project_pattern: str, task_args: list[str]) -> None:
    """Run package-local Poe tasks across the selected projects."""
    selected_projects = select_projects(project_pattern)
    if not selected_projects:
        print("[yellow]No selected projects support the current Python version, skipping.[/yellow]")
        return

    work_items = build_work_items([project.path for project in selected_projects], task_names)
    run_tasks(work_items, WORKSPACE_ROOT, task_args=task_args)


def sample_pyright_config() -> str:
    """Return the sample Pyright configuration for the current interpreter."""
    if sys.version_info < (3, 11):
        return "pyrightconfig.samples.py310.json"
    return "pyrightconfig.samples.json"


def run_sample_lint(extra_args: list[str]) -> None:
    """Run linting against samples/."""
    command = [
        "uv",
        "run",
        "ruff",
        "check",
        "samples",
        "--fix",
        "--exclude",
        SAMPLE_EXCLUDES,
        "--ignore",
        SAMPLE_RUFF_IGNORE,
        *extra_args,
    ]
    run_command(command)


def run_sample_format(extra_args: list[str]) -> None:
    """Run formatting against samples/."""
    command = [
        "uv",
        "run",
        "ruff",
        "format",
        "samples",
        "--exclude",
        SAMPLE_EXCLUDES,
        *extra_args,
    ]
    run_command(command)


def run_sample_pyright(extra_args: list[str]) -> None:
    """Run sample syntax/import validation."""
    command = ["uv", "run", "pyright", "-p", sample_pyright_config(), "--warnings", *extra_args]
    run_command(command)


def run_markdown_code_lint(files: list[str] | None = None) -> None:
    """Run markdown code-block linting globally or for the changed markdown files only."""
    command = [
        "uv",
        "run",
        "python",
        "scripts/check_md_code_blocks.py",
    ]
    if files is None:
        command.extend([
            "README.md",
            "./packages/**/README.md",
            "./samples/**/*.md",
        ])
    else:
        if not files:
            print("[yellow]No markdown files changed, skipping markdown code lint.[/yellow]")
            return
        command.extend(files)
        command.append("--no-glob")

    for excluded_path in MARKDOWN_EXCLUDES:
        command.extend(["--exclude", excluded_path])
    run_command(command)


def run_aggregate_pyright(project_pattern: str, extra_args: list[str]) -> None:
    """Run a single Pyright sweep across the selected project roots."""
    projects = select_projects(project_pattern)
    if not projects:
        print("[yellow]No selected projects support the current Python version, skipping.[/yellow]")
        return

    project_paths = [relative_path(WORKSPACE_ROOT / project.path) for project in projects]
    run_command(["uv", "run", "pyright", *extra_args, *project_paths])


def run_aggregate_mypy(project_pattern: str, extra_args: list[str]) -> None:
    """Run a single MyPy sweep across the selected project import roots."""
    projects = select_projects(project_pattern)
    if not projects:
        print("[yellow]No selected projects support the current Python version, skipping.[/yellow]")
        return

    source_dirs = [relative_path(path) for path in collect_source_dirs(projects)]
    if not source_dirs:
        print("[yellow]No import roots found for the selected projects, skipping MyPy.[/yellow]")
        return

    run_command(["uv", "run", "mypy", "--config-file", "pyproject.toml", *extra_args, *source_dirs])


def run_aggregate_test(project_pattern: str, cov: bool, extra_args: list[str]) -> None:
    """Run a single pytest sweep across the selected project test directories."""
    projects = select_projects(project_pattern)
    if not projects:
        print("[yellow]No selected projects support the current Python version, skipping.[/yellow]")
        return

    if project_pattern == "*":
        # Preserve the legacy ``all-tests`` contract when ``test --all`` runs with
        # the default selector: experimental packages stay opt-in instead of
        # suddenly joining every PR unit-test sweep.
        projects = [project for project in projects if project.name not in DEFAULT_AGGREGATE_TEST_EXCLUDES]
        if not projects:
            print("[yellow]No aggregate-test projects remain after applying default exclusions.[/yellow]")
            return

    test_dirs = [relative_path(path) for path in collect_test_dirs(projects)]
    if not test_dirs:
        print("[yellow]No test directories found for the selected projects, skipping pytest.[/yellow]")
        return

    command = [
        "uv",
        "run",
        "pytest",
        "--import-mode=importlib",
        "-m",
        "not integration",
        "-rs",
        "-n",
        "logical",
        "--dist",
        "worksteal",
    ]
    if cov:
        for source_dir in collect_source_dirs(projects):
            command.append(f"--cov={source_dir.name}")
        command.extend(["--cov-config=pyproject.toml", "--cov-report=term-missing:skip-covered"])

    command.extend(extra_args)
    command.extend(test_dirs)
    run_command(command)


def normalize_changed_file(file_path: str) -> str:
    """Normalize changed-file paths passed from git or pre-commit."""
    normalized = file_path.replace("\\", "/")
    if normalized.startswith("python/"):
        return normalized[7:]
    return normalized


def has_changed_sample_files(files: list[str]) -> bool:
    """Return whether any changed file lives under samples/."""
    return any(normalize_changed_file(file_path).startswith("samples/") for file_path in files)


def changed_markdown_files(files: list[str]) -> list[str]:
    """Return markdown files from the provided change list."""
    markdown_files = [normalize_changed_file(file_path) for file_path in files]
    return sorted({file_path for file_path in markdown_files if file_path.endswith(".md")})


def run_changed_package_tasks(task_names: list[str], files: list[str]) -> None:
    """Run package-local tasks only in packages affected by the provided file list."""
    command = [
        "uv",
        "run",
        "python",
        "scripts/run_tasks_in_changed_packages.py",
        *task_names,
        "--files",
        *files,
    ]
    run_command(command)


def run_prek_check(files: list[str]) -> None:
    """Run the lightweight pre-commit task surface."""
    normalized_files = [normalize_changed_file(file_path) for file_path in files] or ["."]
    run_changed_package_tasks(["fmt", "lint"], normalized_files)
    run_markdown_code_lint(changed_markdown_files(normalized_files))
    if has_changed_sample_files(normalized_files):
        print("[cyan]Sample files changed, running sample checks.[/cyan]")
        run_sample_lint([])
        run_sample_pyright([])
    else:
        print("[yellow]No sample files changed, skipping sample checks.[/yellow]")


def git_diff_name_only(*revisions: str) -> list[str] | None:
    """Try a git diff strategy and return changed files if it succeeds."""
    result = subprocess.run(
        ["git", "diff", "--name-only", *revisions, "--", "."],
        cwd=WORKSPACE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line]


def detect_ci_changed_files() -> list[str]:
    """Detect changed files for change-based mypy runs."""
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if base_ref:
        subprocess.run(
            ["git", "fetch", "origin", base_ref, "--depth=1"],
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        strategies = [
            (f"origin/{base_ref}...HEAD",),
            ("FETCH_HEAD...HEAD",),
            ("HEAD^...HEAD",),
        ]
    else:
        strategies = [
            ("origin/main...HEAD",),
            ("main...HEAD",),
            ("HEAD~1",),
        ]

    for strategy in strategies:
        changed_files = git_diff_name_only(*strategy)
        if changed_files is not None:
            return changed_files or ["."]

    return ["."]


def run_ci_mypy() -> None:
    """Run MyPy only where changes require it, mirroring CI behaviour."""
    changed_files = detect_ci_changed_files()
    print("[cyan]Changed files for CI mypy:[/cyan]")
    for file_path in changed_files:
        print(f"  {file_path}")
    run_changed_package_tasks(["mypy"], changed_files)


def ensure_no_extra_args(command_name: str, extra_args: list[str]) -> None:
    """Reject unsupported pass-through arguments for commands that do not forward them."""
    if extra_args:
        joined_args = " ".join(extra_args)
        print(f"[red]Command '{command_name}' does not accept extra arguments: {joined_args}[/red]")
        raise SystemExit(2)


def resolve_syntax_modes(*, format_selected: bool, check_selected: bool) -> tuple[bool, bool]:
    """Resolve which syntax steps to run."""
    if not format_selected and not check_selected:
        return True, True
    return format_selected, check_selected


def run_syntax(
    *,
    project_pattern: str,
    samples: bool,
    format_selected: bool,
    check_selected: bool,
    extra_args: list[str],
) -> None:
    """Run formatting and/or lint checking for packages or samples.

    Combined package mode deliberately dispatches ``fmt`` and ``lint`` together
    so the shared task runner can start both legs in parallel.
    """
    run_format, run_check = resolve_syntax_modes(
        format_selected=format_selected,
        check_selected=check_selected,
    )
    if run_format and run_check and extra_args:
        joined_args = " ".join(extra_args)
        print(
            "[red]Extra arguments are only supported when syntax runs a single mode; "
            f"use either --format or --check with: {joined_args}[/red]"
        )
        raise SystemExit(2)

    if samples and project_pattern != "*":
        print("[red]--samples cannot be combined with --package.[/red]")
        raise SystemExit(2)

    format_args = extra_args if run_format and not run_check else []
    check_args = extra_args if run_check and not run_format else []

    if samples:
        if run_format:
            run_sample_format(format_args)
        if run_check:
            run_sample_lint(check_args)
        return

    if run_format and run_check:
        # Fan out both legs in one call so task_runner can parallelize format
        # and lint work across the same selected package set.
        run_fan_out(["fmt", "lint"], project_pattern, [])
        return

    if run_format:
        run_fan_out(["fmt"], project_pattern, format_args)
    if run_check:
        run_fan_out(["lint"], project_pattern, check_args)


def main() -> None:
    """Dispatch the requested workspace task."""
    args, extra_args = parse_args(sys.argv[1:])

    if args.command == "syntax":
        run_syntax(
            project_pattern=args.project,
            samples=args.samples,
            format_selected=args.format,
            check_selected=args.check,
            extra_args=extra_args,
        )
        return

    if args.command == "fmt":
        run_syntax(
            project_pattern=args.project,
            samples=False,
            format_selected=True,
            check_selected=False,
            extra_args=extra_args,
        )
        return

    if args.command == "lint":
        if args.samples:
            run_syntax(
                project_pattern=args.project,
                samples=True,
                format_selected=False,
                check_selected=True,
                extra_args=extra_args,
            )
            return
        run_syntax(
            project_pattern=args.project,
            samples=False,
            format_selected=False,
            check_selected=True,
            extra_args=extra_args,
        )
        return

    if args.command == "pyright":
        if args.samples:
            if args.all or args.project != "*":
                print("[red]--samples cannot be combined with --all or --package.[/red]")
                raise SystemExit(2)
            run_sample_pyright(extra_args)
            return
        if args.all:
            run_aggregate_pyright(args.project, extra_args)
            return
        run_fan_out(["pyright"], args.project, extra_args)
        return

    if args.command == "mypy":
        if args.all:
            run_aggregate_mypy(args.project, extra_args)
            return
        run_fan_out(["mypy"], args.project, extra_args)
        return

    if args.command == "typing":
        ensure_no_extra_args(args.command, extra_args)
        if args.all:
            # Start MyPy first so combined typing runs follow the requested
            # ordering even though completion still depends on runtime duration.
            run_aggregate_mypy(args.project, [])
            run_aggregate_pyright(args.project, [])
            return
        # Preserve the same "MyPy first" ordering for the per-package fan-out
        # path as well.
        run_fan_out(["mypy", "pyright"], args.project, [])
        return

    if args.command == "test":
        if args.all:
            run_aggregate_test(args.project, args.cov, extra_args)
            return
        run_fan_out(["test"], args.project, extra_args)
        return

    if args.command == "build":
        ensure_no_extra_args(args.command, extra_args)
        run_fan_out(["build"], args.project, [])
        return

    if args.command == "clean-dist":
        ensure_no_extra_args(args.command, extra_args)
        run_fan_out(["clean-dist"], args.project, [])
        return

    if args.command == "check-packages":
        ensure_no_extra_args(args.command, extra_args)
        run_syntax(
            project_pattern=args.project,
            samples=False,
            format_selected=False,
            check_selected=False,
            extra_args=[],
        )
        run_fan_out(["pyright"], args.project, [])
        return

    if args.command == "check":
        ensure_no_extra_args(args.command, extra_args)
        if args.samples:
            if args.project != "*":
                print("[red]--samples cannot be combined with --package.[/red]")
                raise SystemExit(2)
            run_syntax(
                project_pattern="*",
                samples=True,
                format_selected=False,
                check_selected=False,
                extra_args=[],
            )
            run_sample_pyright([])
            return
        run_syntax(
            project_pattern=args.project,
            samples=False,
            format_selected=False,
            check_selected=False,
            extra_args=[],
        )
        run_fan_out(["pyright"], args.project, [])
        run_fan_out(["test"], args.project, [])
        # Sample validation and markdown lint are intentionally workspace-wide;
        # a package-scoped check should stay focused on the selected package set.
        if args.project == "*":
            run_syntax(
                project_pattern="*",
                samples=True,
                format_selected=False,
                check_selected=False,
                extra_args=[],
            )
            run_sample_pyright([])
            run_markdown_code_lint()
        return

    if args.command == "prek-check":
        ensure_no_extra_args(args.command, extra_args)
        run_prek_check(args.files)
        return

    if args.command == "ci-mypy":
        ensure_no_extra_args(args.command, extra_args)
        run_ci_mypy()
        return

    print(f"[red]Unsupported command: {args.command}[/red]")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
