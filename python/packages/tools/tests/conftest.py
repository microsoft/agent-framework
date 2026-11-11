# Copyright (c) Microsoft. All rights reserved.

"""Shared fixtures for the shell tool tests."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterable

import pytest


@pytest.fixture
def fake_windows_host(monkeypatch: pytest.MonkeyPatch) -> Callable[[str, Iterable[str]], None]:
    """Return a factory that makes the process look like a Windows host.

    Each call sets ``sys.platform`` and ``PATH``, and makes ``os.path.isfile`` report only the given files. A
    later call replaces the files of an earlier call. The host file system is never consulted, so a real
    installation directory cannot change the result. No file is created and no executable is started, so tests
    that use it behave the same on every platform.
    """

    def configure(path_env: str, files: Iterable[str]) -> None:
        known = frozenset(files)

        def isfile(candidate: str | os.PathLike[str]) -> bool:
            return os.fspath(candidate) in known

        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("PATH", path_env)
        monkeypatch.setattr(os.path, "isfile", isfile)

    return configure
