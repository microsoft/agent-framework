# Copyright (c) Microsoft. All rights reserved.

"""Filesystem helpers for local CodeAct."""

from __future__ import annotations

import mimetypes
from collections.abc import Iterator, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast

from agent_framework import Content

from ._types import FileMount, FileMountInput, ProcessExecutionLimits

WORKSPACE_MOUNT_PATH = "/input"


def normalize_mount_path(mount_path: str) -> str:
    """Normalize a display/capture mount path to a clean POSIX absolute path."""
    raw = mount_path.strip().replace("\\", "/")
    if not raw:
        raise ValueError("mount_path must not be empty.")
    pure = PurePosixPath(raw)
    parts = [part for part in pure.parts if part not in {"", "/", "."}]
    if any(part == ".." for part in parts):
        raise ValueError("mount_path must not contain '..' segments.")
    if not parts:
        raise ValueError("mount_path must point to a concrete absolute path.")
    return "/" + "/".join(parts)


def resolve_existing_directory(value: str | Path) -> Path:
    """Resolve a path and require it to point at an existing real directory.

    Symlinks at the mount root are rejected: a mount whose host_path is itself
    a symlink could silently expose a directory outside the intended location
    (for example a ``/tmp/foo`` symlink pointing at ``/etc``). Callers must
    supply concrete directories so the surface visible to generated code is
    the surface the host actually approved.
    """
    raw = Path(value).expanduser()
    if raw.is_symlink():
        raise ValueError(f"Path {value!r} must not be a symbolic link.")
    resolved = raw.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"Path {value!r} must point to an existing directory.")
    return resolved


def is_file_mount_pair(value: Any) -> bool:
    """Return whether ``value`` is a ``(host_path, mount_path)`` file-mount pair."""
    if not isinstance(value, tuple) or isinstance(value, FileMount):
        return False
    items = cast("tuple[object, ...]", value)
    if len(items) != 2:
        return False
    host_path, mount_path = items
    return isinstance(host_path, (str, Path)) and isinstance(mount_path, str)


def normalize_file_mount(file_mount: FileMountInput) -> FileMount:
    """Normalize a public file-mount input."""
    if isinstance(file_mount, FileMount):
        host_path = file_mount.host_path
        mount_path = file_mount.mount_path
        mode = file_mount.mode
        write_limit = file_mount.write_bytes_limit
    elif isinstance(file_mount, str):
        host_path = file_mount
        mount_path = file_mount
        mode = "overlay"
        write_limit = None
    else:
        host_path, mount_path = file_mount
        mode = "overlay"
        write_limit = None

    if write_limit is not None and write_limit < 0:
        raise ValueError("write_bytes_limit must be non-negative or None.")

    return FileMount(
        host_path=resolve_existing_directory(host_path),
        mount_path=normalize_mount_path(mount_path),
        mode=mode,
        write_bytes_limit=write_limit,
    )


def iter_real_files(root: Path) -> Iterator[Path]:
    """Walk ``root`` recursively, yielding only real non-symlink files.

    Defenses against generated code trying to surface protected host data via
    a virtual mount path:

    * Symlinks (file or directory) are skipped so they cannot redirect the
      walk to content outside the mount.
    * Hardlinks (``st_nlink > 1``) are skipped because a hardlink inside the
      mount can point at an inode whose canonical path is outside the mount
      (for example ``ln /etc/passwd /input/loot.txt``).
    * Every entry's resolved path is required to stay under ``root`` so that
      junctions, bind mounts, or any other filesystem feature that ``is_symlink``
      does not flag cannot escape the mount boundary.
    """
    try:
        root_resolved = root.resolve(strict=True)
    except OSError:
        return
    stack: list[Path] = [root_resolved]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                resolved = entry.resolve(strict=False)
                if not resolved.is_relative_to(root_resolved):
                    continue
                if entry.is_dir():
                    stack.append(entry)
                elif entry.is_file():
                    stat = entry.lstat()
                    if stat.st_nlink > 1:
                        continue
                    yield entry
            except OSError:
                continue


def snapshot_writable_mounts(mounts: Sequence[FileMount]) -> dict[str, dict[str, tuple[int, int]]]:
    """Capture ``(size, mtime_ns)`` for real files under read-write mounts."""
    snapshot: dict[str, dict[str, tuple[int, int]]] = {}
    for mount in mounts:
        if mount.mode != "read-write":
            continue
        host_root = Path(mount.host_path)
        per_mount: dict[str, tuple[int, int]] = {}
        for entry in iter_real_files(host_root):
            try:
                stat = entry.lstat()
            except OSError:
                continue
            relative = entry.relative_to(host_root).as_posix()
            per_mount[relative] = (int(stat.st_size), int(stat.st_mtime_ns))
        snapshot[mount.mount_path] = per_mount
    return snapshot


def capture_written_files(
    mounts: Sequence[FileMount],
    pre_state: dict[str, dict[str, tuple[int, int]]],
    *,
    limits: ProcessExecutionLimits,
) -> list[Content]:
    """Return content items for files written under read-write mounts."""
    captured: list[Content] = []
    total_bytes = 0
    for mount in mounts:
        if mount.mode != "read-write":
            continue
        host_root = Path(mount.host_path)
        before = pre_state.get(mount.mount_path, {})
        mount_bytes = 0
        for entry in sorted(iter_real_files(host_root)):
            try:
                stat = entry.lstat()
            except OSError:
                continue
            relative = entry.relative_to(host_root).as_posix()
            current = (int(stat.st_size), int(stat.st_mtime_ns))
            if before.get(relative) == current:
                continue
            sandbox_path = f"{mount.mount_path.rstrip('/')}/{relative}"
            if stat.st_size > limits.max_captured_file_bytes:
                captured.append(Content.from_text(f"[file {sandbox_path} omitted: file exceeds capture limit]"))
                continue
            if mount.write_bytes_limit is not None and mount_bytes + stat.st_size > mount.write_bytes_limit:
                captured.append(Content.from_text(f"[file {sandbox_path} omitted: mount capture limit exceeded]"))
                continue
            if total_bytes + stat.st_size > limits.max_total_captured_file_bytes:
                captured.append(Content.from_text(f"[file {sandbox_path} omitted: total capture limit exceeded]"))
                continue
            try:
                data = entry.read_bytes()
            except OSError:
                continue
            media_type = mimetypes.guess_type(entry.name)[0] or "application/octet-stream"
            captured.append(
                Content.from_data(
                    data=data,
                    media_type=media_type,
                    additional_properties={"path": sandbox_path},
                )
            )
            mount_bytes += stat.st_size
            total_bytes += stat.st_size
    return captured
