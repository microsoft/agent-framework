# Copyright (c) Microsoft. All rights reserved.

"""Regression tests for literal Markdown file selection."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.check_md_code_blocks import expand_file_patterns


class MarkdownFileSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def markdown(self, name: str) -> str:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("```python\nprint('example')\n```\n", encoding="utf-8")
        return str(path)

    def test_literal_bracketed_filename(self) -> None:
        literal = self.markdown("guide[1].md")
        self.assertEqual(expand_file_patterns([literal], skip_glob=True), [literal])

    def test_literal_filename_does_not_select_glob_match(self) -> None:
        literal = self.markdown("guide[1].md")
        self.markdown("guide1.md")
        self.assertEqual(expand_file_patterns([literal], skip_glob=True), [literal])

    def test_literal_bracketed_directory(self) -> None:
        literal = self.markdown("docs[1]/guide.md")
        self.markdown("docs1/guide.md")
        self.assertEqual(expand_file_patterns([literal], skip_glob=True), [literal])

    def test_literal_mode_preserves_file_filtering(self) -> None:
        ordinary = self.markdown("guide.md")
        non_markdown = self.markdown("notes.txt")
        missing = str(self.root / "missing.md")
        self.assertEqual(
            expand_file_patterns([ordinary, non_markdown, missing], skip_glob=True),
            [ordinary],
        )

    def test_literal_mode_sorts_and_deduplicates(self) -> None:
        first = self.markdown("a.md")
        last = self.markdown("z.md")
        self.assertEqual(expand_file_patterns([last, first, last], skip_glob=True), [first, last])

    def test_default_mode_still_expands_brackets(self) -> None:
        pattern = self.markdown("guide[1].md")
        match = self.markdown("guide1.md")
        self.assertEqual(expand_file_patterns([pattern]), [match])

    def test_default_mode_still_expands_recursive_patterns(self) -> None:
        first = self.markdown("guide.md")
        nested = self.markdown("nested/guide.md")
        pattern = str(self.root / "**" / "*.md")
        self.assertEqual(expand_file_patterns([pattern]), sorted([first, nested]))

    def test_cli_checks_the_literal_file(self) -> None:
        literal = self.markdown("guide[1].md")
        other = self.markdown("guide1.md")
        script = Path(__file__).resolve().parents[1] / "check_md_code_blocks.py"
        result = subprocess.run(
            [sys.executable, "-B", str(script), "--no-glob", literal],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(literal, result.stderr)
        self.assertNotIn(other, result.stderr)


if __name__ == "__main__":
    unittest.main()
