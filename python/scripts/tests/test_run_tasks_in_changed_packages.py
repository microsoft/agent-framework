# Copyright (c) Microsoft. All rights reserved.

"""Routing coverage for repository-relative changed-file paths."""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.run_tasks_in_changed_packages import get_changed_packages


class GetChangedPackagesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Path("/tmp/agent-framework-python")
        self.projects = [Path("packages/core"), Path("packages/redis")]

    def _route(self, *files: str) -> tuple[set[Path], bool]:
        return get_changed_packages(self.projects, list(files), self.workspace)

    def test_forward_slash_repo_relative_path_selects_core(self) -> None:
        packages, core_changed = self._route("python/packages/core/agent_framework/_types.py")
        self.assertEqual({Path("packages/core")}, packages)
        self.assertTrue(core_changed)

    def test_backslash_repo_relative_path_selects_core(self) -> None:
        packages, core_changed = self._route(r"python\packages\core\agent_framework\_types.py")
        self.assertEqual({Path("packages/core")}, packages)
        self.assertTrue(core_changed)

    def test_backslash_repo_relative_redis_path_does_not_mark_core(self) -> None:
        packages, core_changed = self._route(r"python\packages\redis\agent_framework_redis\__init__.py")
        self.assertEqual({Path("packages/redis")}, packages)
        self.assertFalse(core_changed)

    def test_workspace_relative_and_absolute_paths_still_select_core(self) -> None:
        absolute = str(self.workspace / "packages/core/agent_framework/_types.py")
        for spelling in (
            "packages/core/agent_framework/_types.py",
            r"packages\core\agent_framework\_types.py",
            absolute,
        ):
            with self.subTest(spelling=spelling):
                packages, core_changed = self._route(spelling)
                self.assertEqual({Path("packages/core")}, packages)
                self.assertTrue(core_changed)

    def test_unrelated_path_stays_empty(self) -> None:
        packages, core_changed = self._route("dotnet/src/Example.cs")
        self.assertEqual(set(), packages)
        self.assertFalse(core_changed)


if __name__ == "__main__":
    unittest.main()
