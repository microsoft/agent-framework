# Copyright (c) Microsoft. All rights reserved.

"""Run task(s) only in packages that have changed files, in parallel by default."""

import argparse
from pathlib import Path

from rich import print
from task_runner import build_work_items, discover_projects, run_tasks

# Tasks that need to run in all packages when core changes (type info propagates)
TYPE_CHECK_TASKS = {"pyright", "mypy"}


def get_changed_packages(
    projects: list[Path], changed_files: list[str], workspace_root: Path
) -> tuple[set[Path], bool]:
    """Determine which packages have changed files.

    Returns:
        A tuple of (changed_packages, core_package_changed).
    """
    changed_packages: set[Path] = set()
    core_package_changed = False

    for file_path in changed_files:
        # Strip 'python/' prefix if present (when git diff is run from repo root)
        file_path_str = str(file_path)
        if file_path_str.startswith("python/"):
            file_path_str = file_path_str[7:]  # Remove 'python/' prefix

        # Convert to absolute path if relative
        abs_path = Path(file_path_str)
        if not abs_path.is_absolute():
            abs_path = workspace_root / file_path_str

        # Check which package this file belongs to
        for project in projects:
            project_abs = workspace_root / project
            try:
                # Check if the file is within this project directory
                abs_path.relative_to(project_abs)
                changed_packages.add(project)
                if project == Path("packages/core"):
                    core_package_changed = True
                break
            except ValueError:
                continue

    return changed_packages, core_package_changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Run task(s) in changed packages, in parallel by default.")
    parser.add_argument("tasks", nargs="+", help="Task name(s) to run")
    parser.add_argument("--files", nargs="*", default=None, help="Changed files to determine which packages to run")
    parser.add_argument("--seq", action="store_true", help="Run sequentially instead of in parallel")
    args = parser.parse_args()

    pyproject_file = Path(__file__).parent.parent / "pyproject.toml"
    workspace_root = pyproject_file.parent
    projects = discover_projects(pyproject_file)

    # Determine which packages to check
    if not args.files or args.files == ["."]:
        task_list = ", ".join(args.tasks)
        print(f"[yellow]No specific files provided, running {task_list} in all packages[/yellow]")
        work_items = build_work_items(sorted(set(projects)), args.tasks)
    else:
        changed_packages, core_changed = get_changed_packages(projects, args.files, workspace_root)
        if not changed_packages:
            print("[yellow]No changes detected in any package, skipping[/yellow]")
            return

        print(f"[cyan]Detected changes in packages: {', '.join(str(p) for p in sorted(changed_packages))}[/cyan]")

        # File-local tasks (fmt, lint) only run in packages with actual changes.
        # Type-checking tasks (pyright, mypy) run in all packages when core changes,
        # because type changes in core propagate to downstream packages.
        local_tasks = [t for t in args.tasks if t not in TYPE_CHECK_TASKS]
        type_tasks = [t for t in args.tasks if t in TYPE_CHECK_TASKS]

        work_items = build_work_items(sorted(changed_packages), local_tasks)
        if type_tasks:
            if core_changed:
                print("[yellow]Core package changed - type-checking all packages[/yellow]")
                work_items += build_work_items(sorted(set(projects)), type_tasks)
            else:
                work_items += build_work_items(sorted(changed_packages), type_tasks)

    if not work_items:
        print("[yellow]No matching tasks found in any package[/yellow]")
        return

    run_tasks(work_items, workspace_root, sequential=args.seq)


if __name__ == "__main__":
    main()
