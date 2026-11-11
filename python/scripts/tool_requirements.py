# Copyright (c) Microsoft. All rights reserved.

"""Load the pinned requirements used by on-demand development tools."""

from __future__ import annotations

from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_ROOT = WORKSPACE_ROOT / "tooling"


def requirement_file(bundle: str) -> Path:
    """Return the requirement file for a named tool bundle."""
    if not bundle or Path(bundle).name != bundle:
        raise ValueError(f"Invalid tool requirement bundle: {bundle!r}")

    path = REQUIREMENTS_ROOT / f"requirements-{bundle}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"Unknown tool requirement bundle: {bundle}")
    return path


def load_requirements(bundle: str) -> tuple[str, ...]:
    """Return flattened requirements from a named bundle."""
    return _load_requirement_file(requirement_file(bundle), seen=set())


def _load_requirement_file(path: Path, *, seen: set[Path]) -> tuple[str, ...]:
    resolved_path = path.resolve()
    if resolved_path in seen:
        raise ValueError(f"Cyclic tool requirement include: {path}")

    seen.add(resolved_path)
    requirements: list[str] = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "--requirement ")):
            include = line.split(maxsplit=1)[1]
            requirements.extend(_load_requirement_file(path.parent / include, seen=seen))
            continue
        requirements.append(line)
    seen.remove(resolved_path)
    return tuple(requirements)
