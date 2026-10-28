# Copyright (c) Microsoft. All rights reserved.

"""Exercise workspace checker selection through the command entrypoint."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import workspace_poe_tasks as workspace


class CheckerSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        project = self.root / "packages" / "core"
        (project / "tests").mkdir(parents=True)
        (self.root / "pyproject.toml").write_text('[tool.uv.workspace]\nmembers = ["packages/*"]\n', encoding="utf-8")
        (project / "pyproject.toml").write_text(
            '[project]\nname = "agent-framework-core"\nrequires-python = ">=3.10"\n',
            encoding="utf-8",
        )
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(workspace, "WORKSPACE_ROOT", self.root))
        stack.enter_context(patch.object(workspace, "WORKSPACE_PYPROJECT", self.root / "pyproject.toml"))

    def dispatch(self, *arguments: str) -> list[tuple[str, list[str]]]:
        recorded: list[tuple[str, list[str]]] = []
        with (
            patch.object(sys, "argv", ["workspace_poe_tasks.py", "test-typing", *arguments]),
            patch.object(workspace, "run_command_items", side_effect=lambda items, *_: recorded.extend(items)),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            workspace.main()
        return recorded

    def test_space_selector_runs_one_checker(self) -> None:
        items = self.dispatch("-P", "core", "--checker", "mypy")
        self.assertEqual([name for name, _ in items], ["mypy :: core"])

    def test_equals_selector_runs_one_checker(self) -> None:
        items = self.dispatch("-P", "core", "--checker=mypy")
        self.assertEqual([name for name, _ in items], ["mypy :: core"])
        self.assertNotIn("--checker=mypy", items[0][1])

    def test_equals_selector_runs_one_sample_checker(self) -> None:
        items = self.dispatch("-S", "--checker=pyright")
        self.assertEqual([name for name, _ in items], ["pyright :: samples"])
        self.assertNotIn("--checker=pyright", items[0][1])

    def test_mixed_selectors_preserve_order(self) -> None:
        items = self.dispatch("-P", "core", "--checker", "mypy", "--checker=pyright")
        self.assertEqual([name for name, _ in items], ["mypy :: core", "pyright :: core"])
        self.assertTrue(all("--checker=pyright" not in command for _, command in items))

    def test_other_arguments_are_forwarded(self) -> None:
        items = self.dispatch("-P", "core", "--checker", "mypy", "--ignore-missing-imports")
        self.assertEqual([name for name, _ in items], ["mypy :: core"])
        self.assertIn("--ignore-missing-imports", items[0][1])

    def test_no_selector_keeps_all_gating_checkers(self) -> None:
        items = self.dispatch("-P", "core")
        self.assertEqual(
            [name for name, _ in items],
            ["mypy :: core", "pyrefly :: core", "ty :: core", "zuban :: core", "pyright :: core"],
        )

    def test_unknown_space_checker_is_rejected(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            self.dispatch("-P", "core", "--checker", "unknown")
        self.assertEqual(raised.exception.code, 2)

    def test_unknown_equals_checker_is_rejected(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            self.dispatch("-P", "core", "--checker=unknown")
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
