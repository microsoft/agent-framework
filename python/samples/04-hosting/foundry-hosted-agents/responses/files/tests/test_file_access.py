# Copyright (c) Microsoft. All rights reserved.

"""Focused negative checks for the sandbox file-access boundary."""

from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"),
    reason="This hosted sample requires POSIX no-follow directory opens.",
)


@pytest.fixture
def access(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location("sample_file_access", Path(__file__).parents[1] / "file_access.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_upload_round_trip_and_cross_sandbox_isolation(
    access: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "report.txt"
    source.write_text("Explicit upload.", encoding="utf-8")
    access.write_local_upload(source.name, access.read_upload_source(source))
    assert access.list_uploaded_files() == ["report.txt"]
    assert access.read_uploaded_file("report.txt") == "Explicit upload."
    other = tmp_path / "other-sandbox"
    other.mkdir()
    monkeypatch.setenv("HOME", str(other))
    assert access.list_uploaded_files() == []
    with pytest.raises(FileNotFoundError):
        access.read_uploaded_file("report.txt")


def test_paths_symlinks_and_nonregular_files_are_rejected(access: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "sample_files"
    root.mkdir()
    private = tmp_path / "private.txt"
    private.write_text("Private data.", encoding="utf-8")
    (root / "link.txt").symlink_to(private)
    (root / "directory").mkdir()
    os.mkfifo(root / "pipe")
    for filename in ("", "..", "../private.txt", str(private), r"C:\private.txt", "file\x00.txt", "file\n.txt"):
        with pytest.raises(ValueError, match="single file name"):
            access.read_uploaded_file(filename)
    with pytest.raises(OSError):
        access.read_uploaded_file("link.txt")
    for filename in ("directory", "pipe"):
        with pytest.raises(ValueError, match="regular uploaded files"):
            access.read_uploaded_file(filename)
    with pytest.raises(OSError):
        access.write_local_upload("link.txt", b"Do not overwrite private data.")
    assert private.read_text(encoding="utf-8") == "Private data."
    assert access.list_uploaded_files() == []


def test_directory_symlinks_and_missing_no_follow_fail_closed(
    access: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private = tmp_path / "private"
    private.mkdir()
    (tmp_path / "sample_files").symlink_to(private, target_is_directory=True)
    with pytest.raises(OSError):
        access.list_uploaded_files()
    home_link = tmp_path / "home-link"
    home_link.symlink_to(private, target_is_directory=True)
    monkeypatch.setenv("HOME", str(home_link))
    with pytest.raises(OSError):
        access.read_uploaded_file("report.txt")
    monkeypatch.delattr(access.os, "O_NOFOLLOW")
    with pytest.raises(RuntimeError, match="no-follow"):
        access.read_uploaded_file("report.txt")


def test_byte_limit_is_checked_before_read_and_after_growth(
    access: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "sample_files"
    root.mkdir()
    (root / "limit.txt").write_bytes(b"x" * 1_000_000)
    assert len(access.read_uploaded_file("limit.txt")) == 1_000_000
    (root / "large.txt").write_bytes(b"x" * 1_000_001)
    original_fdopen = os.fdopen
    reads: list[int] = []

    class Reader:
        def __init__(self, descriptor: int) -> None:
            self.file = original_fdopen(descriptor, "rb")

        def __enter__(self) -> Reader:
            return self

        def __exit__(self, *args: Any) -> None:
            self.file.close()

        def read(self, size: int) -> bytes:
            reads.append(size)
            return self.file.read(size)

    monkeypatch.setattr(access.os, "fdopen", lambda descriptor, mode: Reader(descriptor))
    with pytest.raises(ValueError, match="1,000,000 bytes"):
        access.read_uploaded_file("large.txt")
    assert reads == []
    monkeypatch.setattr(access.os, "fstat", lambda descriptor: SimpleNamespace(st_mode=stat.S_IFREG, st_size=1))
    with pytest.raises(ValueError, match="1,000,000 bytes"):
        access.read_uploaded_file("large.txt")
    assert reads == [1_000_001]


@pytest.mark.parametrize("replacement", ["directory", "file"])
def test_replacement_cannot_redirect_a_read(
    access: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replacement: str
) -> None:
    root, private = tmp_path / "sample_files", tmp_path / "private"
    root.mkdir()
    private.mkdir()
    (root / "report.txt").write_text("Original upload.", encoding="utf-8")
    (private / "report.txt").write_text("Private data.", encoding="utf-8")
    original_open = os.open

    def replace(path: Any, flags: int, mode: int = 0o777, *, dir_fd: int | None = None) -> int:
        if path == "report.txt":
            if replacement == "directory":
                root.rename(tmp_path / "original-uploads")
                root.symlink_to(private, target_is_directory=True)
            else:
                (root / "report.txt").unlink()
                (root / "report.txt").symlink_to(private / "report.txt")
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(access.os, "open", replace)
    monkeypatch.setattr(access.os, "supports_dir_fd", {*os.supports_dir_fd, replace})
    if replacement == "directory":
        assert access.read_uploaded_file("report.txt") == "Original upload."
    else:
        with pytest.raises(OSError):
            access.read_uploaded_file("report.txt")
