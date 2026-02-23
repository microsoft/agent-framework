# Copyright (c) Microsoft. All rights reserved.

"""Run poe task(s) across all workspace packages, in parallel by default."""

import argparse
import sys
from pathlib import Path

from task_runner import build_work_items, discover_projects, run_tasks


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run poe task(s) across all workspace packages, in parallel by default."
    )
    parser.add_argument("tasks", nargs="+", help="Task name(s) to run across packages")
    parser.add_argument("--seq", action="store_true", help="Run sequentially instead of in parallel")
    args = parser.parse_args()

    pyproject_file = Path(__file__).parent.parent / "pyproject.toml"
    workspace_root = pyproject_file.parent
    projects = discover_projects(pyproject_file)

    work_items = build_work_items(projects, args.tasks)
    run_tasks(work_items, workspace_root, sequential=args.seq)


if __name__ == "__main__":
    main()
