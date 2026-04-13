# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import inspect
import textwrap
from collections.abc import Callable, Mapping
from typing import Any

_GOOGLE_SECTION_HEADERS = (
    "Args:",
    "Keyword Args:",
    "Attributes:",
    "Returns:",
    "Raises:",
    "Examples:",
    "Note:",
    "Notes:",
    "Warning:",
    "Warnings:",
)


def _find_section_index(lines: list[str], header: str) -> int | None:
    for index, line in enumerate(lines):
        if line == header:
            return index
    return None


def _find_next_section_index(lines: list[str], start: int) -> int:
    for index in range(start, len(lines)):
        if lines[index] in _GOOGLE_SECTION_HEADERS:
            return index
    return len(lines)


def _format_keyword_arg_lines(extra_keyword_args: Mapping[str, str]) -> list[str]:
    formatted_lines: list[str] = []
    for name, description in extra_keyword_args.items():
        description_lines = inspect.cleandoc(description).splitlines()
        if not description_lines:
            formatted_lines.append(f"    {name}:")
            continue
        formatted_lines.append(f"    {name}: {description_lines[0]}")
        formatted_lines.extend(f"        {line}" for line in description_lines[1:])
    return formatted_lines


def insert_docstring_block(docstring: str | None, *, block: str) -> str | None:
    """Insert a preformatted block before the first Google-style section."""
    cleaned_block = textwrap.dedent(block).strip()
    if not cleaned_block:
        return docstring
    if not docstring:
        return cleaned_block

    lines = inspect.cleandoc(docstring).splitlines()
    block_lines = cleaned_block.splitlines()
    insert_index = _find_next_section_index(lines, 0)

    insertion: list[str] = []
    if insert_index > 0 and lines[insert_index - 1] != "":
        insertion.append("")
    insertion.extend(block_lines)
    if insert_index < len(lines) and insertion[-1] != "":
        insertion.append("")

    lines[insert_index:insert_index] = insertion
    return "\n".join(lines).rstrip()


def build_layered_docstring(
    source: Callable[..., Any],
    *,
    extra_keyword_args: Mapping[str, str] | None = None,
) -> str | None:
    """Build a Google-style docstring from a lower-layer implementation."""
    docstring = inspect.getdoc(source)
    if not docstring:
        return None
    if not extra_keyword_args:
        return docstring

    lines = docstring.splitlines()
    formatted_keyword_arg_lines = _format_keyword_arg_lines(extra_keyword_args)
    keyword_args_index = _find_section_index(lines, "Keyword Args:")

    if keyword_args_index is None:
        args_index = _find_section_index(lines, "Args:")
        if args_index is not None:
            insert_index = _find_next_section_index(lines, args_index + 1)
        else:
            insert_index = _find_next_section_index(lines, 0)
        lines[insert_index:insert_index] = ["", "Keyword Args:", *formatted_keyword_arg_lines]
        return "\n".join(lines).rstrip()

    insert_index = _find_next_section_index(lines, keyword_args_index + 1)
    lines[insert_index:insert_index] = formatted_keyword_arg_lines
    return "\n".join(lines).rstrip()


def apply_layered_docstring(
    target: Callable[..., Any],
    source: Callable[..., Any],
    *,
    extra_keyword_args: Mapping[str, str] | None = None,
) -> None:
    """Copy a lower-layer docstring onto a wrapper and extend it when needed."""
    target.__doc__ = build_layered_docstring(source, extra_keyword_args=extra_keyword_args)
