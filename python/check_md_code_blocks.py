# Copyright (c) Microsoft. All rights reserved.

"""Check code blocks in Markdown files for syntax errors."""

import argparse
from enum import Enum
import glob
import logging
import tempfile
import subprocess  # nosec

from pygments import highlight  # type: ignore
from pygments.formatters import TerminalFormatter
from pygments.lexers import PythonLexer

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)


class Colors(str, Enum):
    CEND = "\33[0m"
    CRED = "\33[31m"
    CREDBG = "\33[41m"
    CGREEN = "\33[32m"
    CGREENBG = "\33[42m"
    CVIOLET = "\33[35m"
    CGREY = "\33[90m"


def with_color(text: str, color: Colors) -> str:
    """Prints a string with the specified color."""
    return f"{color.value}{text}{Colors.CEND.value}"


def expand_file_patterns(patterns: list[str], skip_glob: bool = False) -> list[str]:
    """Expand glob patterns to actual file paths."""
    all_files: list[str] = []
    for pattern in patterns:
        if skip_glob:
            # When skip_glob is True, treat patterns as literal file paths
            # Only include if it's a markdown file
            if pattern.endswith('.md'):
                matches = glob.glob(pattern, recursive=False)
                all_files.extend(matches)
        else:
            # Handle both relative and absolute paths with glob expansion
            matches = glob.glob(pattern, recursive=True)
            all_files.extend(matches)
    return sorted(set(all_files))  # Remove duplicates and sort


def extract_python_code_blocks(markdown_file_path: str) -> list[tuple[str, int]]:
    """Extract Python code blocks from a Markdown file."""
    with open(markdown_file_path, encoding="utf-8") as file:
        lines = file.readlines()

    code_blocks: list[tuple[str, int]] = []
    in_code_block = False
    current_block: list[str] = []

    for i, line in enumerate(lines):
        if line.strip().startswith("```python"):
            in_code_block = True
            current_block = []
        elif line.strip().startswith("```"):
            in_code_block = False
            code_blocks.append(("\n".join(current_block), i - len(current_block) + 1))
        elif in_code_block:
            current_block.append(line)

    return code_blocks


def check_code_blocks(markdown_file_paths: list[str], exclude_patterns: list[str] | None = None) -> None:
    """Check Python code blocks in a Markdown file for syntax errors."""
    files_with_errors: list[str] = []
    exclude_patterns = exclude_patterns or []

    for markdown_file_path in markdown_file_paths:
        # Skip files that match any exclude pattern
        if any(pattern in markdown_file_path for pattern in exclude_patterns):
            logger.info(f"Skipping {markdown_file_path} (matches exclude pattern)")
            continue
        code_blocks = extract_python_code_blocks(markdown_file_path)
        had_errors = False
        for code_block, line_no in code_blocks:
            markdown_file_path_with_line_no = f"{markdown_file_path}:{line_no}"
            logger.info("Checking a code block in %s...", markdown_file_path_with_line_no)

            # Skip blocks that don't import agent_framework modules or import lab modules
            if (all(
                all(import_code not in code_block for import_code in [f"import {module}", f"from {module}"])
                for module in ["agent_framework"]
            ) or "agent_framework.lab" in code_block):
                logger.info(f' {with_color("OK[ignored]", Colors.CGREENBG)}')
                continue

            with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as temp_file:
                temp_file.write(code_block.encode("utf-8"))
                temp_file.flush()

                # Run pyright on the temporary file using subprocess.run

                result = subprocess.run(["uv", "run", "pyright", temp_file.name], capture_output=True, text=True, cwd=".")  # nosec
                if result.returncode != 0:
                    highlighted_code = highlight(code_block, PythonLexer(), TerminalFormatter())  # type: ignore
                    logger.info(
                        f" {with_color('FAIL', Colors.CREDBG)}\n"
                        f"{with_color('========================================================', Colors.CGREY)}\n"
                        f"{with_color('Error', Colors.CRED)}: Pyright found issues in {with_color(markdown_file_path_with_line_no, Colors.CVIOLET)}:\n"
                        f"{with_color('--------------------------------------------------------', Colors.CGREY)}\n"
                        f"{highlighted_code}\n"
                        f"{with_color('--------------------------------------------------------', Colors.CGREY)}\n"
                        "\n"
                        f"{with_color('pyright output:', Colors.CVIOLET)}\n"
                        f"{with_color(result.stdout, Colors.CRED)}"
                        f"{with_color('========================================================', Colors.CGREY)}\n"
                    )
                    had_errors = True
                else:
                    logger.info(f" {with_color('OK', Colors.CGREENBG)}")

        if had_errors:
            files_with_errors.append(markdown_file_path)

    if files_with_errors:
        raise RuntimeError("Syntax errors found in the following files:\n" + "\n".join(files_with_errors))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check code blocks in Markdown files for syntax errors.")
    # Argument is a list of markdown files containing glob patterns
    parser.add_argument("markdown_files", nargs="+", help="Markdown files to check (supports glob patterns).")
    parser.add_argument("--exclude", action="append", help="Exclude files containing this pattern.")
    parser.add_argument("--no-glob", action="store_true", help="Treat file arguments as literal paths (no glob expansion).")
    args = parser.parse_args()

    # Expand glob patterns to actual file paths (or skip if --no-glob)
    expanded_files = expand_file_patterns(args.markdown_files, skip_glob=args.no_glob)
    check_code_blocks(expanded_files, args.exclude)
