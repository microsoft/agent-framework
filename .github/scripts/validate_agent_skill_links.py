#!/usr/bin/env python3
# Copyright (c) Microsoft. All rights reserved.
"""Validate local Markdown resources bundled with public Agent Skills."""

from __future__ import annotations

import re
import stat
import sys
from pathlib import Path

LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def validate_agent_skill_links(skills_directory: Path) -> list[str]:
    """Return validation errors for local Markdown links in public Agent Skills."""
    errors: list[str] = []
    skill_roots = sorted(path.parent for path in skills_directory.rglob("SKILL.md"))

    if not skill_roots:
        return [f"No Agent Skills found under {skills_directory}."]

    for skill_root in skill_roots:
        resolved_root = skill_root.resolve(strict=True)
        for markdown_path in skill_root.rglob("*.md"):
            for target in LINK_PATTERN.findall(markdown_path.read_text(encoding="utf-8")):
                if "://" in target or target.startswith(("#", "mailto:")):
                    continue

                relative_target = target.split("#", 1)[0]
                if not relative_target:
                    continue

                target_path = Path(relative_target)
                if target_path.is_absolute():
                    errors.append(f"{markdown_path}: absolute local link is not allowed: {target}")
                    continue

                candidate = markdown_path.parent / target_path
                try:
                    resolved_candidate = candidate.resolve(strict=True)
                except FileNotFoundError:
                    errors.append(f"{markdown_path}: missing local resource: {target}")
                    continue

                try:
                    resolved_candidate.relative_to(resolved_root)
                except ValueError:
                    errors.append(f"{markdown_path}: local resource escapes skill root: {target}")
                    continue

                if not stat.S_ISREG(candidate.lstat().st_mode):
                    errors.append(f"{markdown_path}: local resource is not a regular file: {target}")

    return errors


def main() -> None:
    skills_directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("skills")
    errors = validate_agent_skill_links(skills_directory)
    if errors:
        raise SystemExit("\n".join(errors))


if __name__ == "__main__":
    main()
