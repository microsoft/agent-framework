# Copyright (c) Microsoft. All rights reserved.

"""Sample discovery module."""

import ast
import os
from pathlib import Path

from _sample_validation.models import DiscoveryResult, SampleInfo, ValidationConfig
from agent_framework import Executor, WorkflowContext, handler


def _is_main_entrypoint_guard(test: ast.expr) -> bool:
    """Check whether an expression is ``__name__ == '__main__'``."""
    if not isinstance(test, ast.Compare):
        return False

    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False

    if len(test.comparators) != 1:
        return False

    left = test.left
    right = test.comparators[0]

    return (
        isinstance(left, ast.Name)
        and left.id == "__name__"
        and isinstance(right, ast.Constant)
        and right.value == "__main__"
    ) or (
        isinstance(right, ast.Name)
        and right.id == "__name__"
        and isinstance(left, ast.Constant)
        and left.value == "__main__"
    )


def _has_main_entrypoint_guard(path: Path) -> bool:
    """Check whether a Python file defines a top-level main entrypoint guard."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return False

    return any(isinstance(node, ast.If) and _is_main_entrypoint_guard(node.test) for node in tree.body)


def discover_samples(samples_dir: Path, subdir: str | None = None) -> list[SampleInfo]:
    """
    Find all Python sample files in the samples directory.

    Args:
        samples_dir: Root samples directory
        subdir: Optional subdirectory to filter to

    Returns:
        List of SampleInfo objects for each discovered sample
    """
    # Determine the search directory
    if subdir:
        search_dir = samples_dir / subdir
        if not search_dir.exists():
            print(f"Warning: Subdirectory '{subdir}' does not exist in {samples_dir}")
            return []
    else:
        search_dir = samples_dir

    python_files: list[Path] = []

    # Walk through all subdirectories and find .py files
    for root, dirs, files in os.walk(search_dir):
        # Skip directories that start with _ (like _sample_validation)
        dirs[:] = [d for d in dirs if not d.startswith("_") and d != "__pycache__"]

        for file in files:
            # Skip files that start with _ and include only scripts with a main entrypoint guard
            if file.endswith(".py") and not file.startswith("_"):
                file_path = Path(root) / file
                if _has_main_entrypoint_guard(file_path):
                    python_files.append(file_path)

    # Sort files for consistent execution order
    python_files = sorted(python_files)

    # Convert to SampleInfo objects
    samples: list[SampleInfo] = []
    for path in python_files:
        try:
            samples.append(SampleInfo.from_path(path, samples_dir))
        except Exception as e:
            print(f"Warning: Could not read {path}: {e}")

    return samples


class DiscoverSamplesExecutor(Executor):
    """Executor that discovers all samples in the samples directory."""

    def __init__(self, config: ValidationConfig):
        super().__init__(id="discover_samples")
        self.config = config

    @handler
    async def discover(self, _: str, ctx: WorkflowContext[DiscoveryResult]) -> None:
        """Discover all Python samples."""
        print(f"🔍 Discovering samples in {self.config.samples_dir}")
        if self.config.subdir:
            print(f"   Filtering to subdirectory: {self.config.subdir}")

        samples = discover_samples(self.config.samples_dir, self.config.subdir)
        print(f"   Found {len(samples)} samples")

        await ctx.send_message(DiscoveryResult(samples=samples))
