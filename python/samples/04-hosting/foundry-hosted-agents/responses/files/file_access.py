# Copyright (c) Microsoft. All rights reserved.

"""Bounded, descriptor-relative access to this sandbox's explicit uploads."""

from __future__ import annotations

import os
import stat
from contextlib import suppress
from pathlib import Path

UPLOAD_DIRECTORY = "sample_files"
MAX_FILE_BYTES = 1_000_000


def validate_filename(filename: str) -> None:
    """Accept one portable filename, never a path supplied by the model."""
    if (
        not isinstance(filename, str)
        or not filename
        or filename in (".", "..")
        or filename != filename.strip()
        or any(character in filename for character in ("/", "\\", ":"))
        or any(ord(character) < 32 or ord(character) == 127 for character in filename)
        or len(os.fsencode(filename)) > 255
    ):
        raise ValueError("filename must be a single file name in sample_files, not a path.")


def _posix_flag(name: str) -> int:
    """Look up a required POSIX-only `os` flag (O_DIRECTORY, O_NOFOLLOW, O_NONBLOCK) by name.

    These flags are not defined in the Windows type stubs, so a literal `os.O_NOFOLLOW`-style
    reference fails Pyright on Windows even though this sandbox only ever executes the code
    path on POSIX. Looking the flag up via `getattr` keeps static analysis clean everywhere
    while still failing closed at runtime: a missing flag raises here exactly like the
    previous `hasattr` guard did, so no-follow/descriptor-relative behavior is unchanged.
    """
    flag = getattr(os, name, None)
    if flag is None:
        raise RuntimeError("Secure file access requires POSIX no-follow, descriptor-relative directory opens.")
    return flag


def _directory_flags() -> int:
    nofollow = _posix_flag("O_NOFOLLOW")
    directory = _posix_flag("O_DIRECTORY")
    if os.open not in os.supports_dir_fd:
        raise RuntimeError("Secure file access requires POSIX no-follow, descriptor-relative directory opens.")
    return os.O_RDONLY | directory | nofollow


def _open_directory(path: Path) -> int:
    """Walk from the filesystem root without following any directory symlink."""
    flags = _directory_flags()
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("The upload directory must be under an absolute, non-traversing HOME.")
    directory = os.open(path.anchor, flags)
    try:
        for component in path.parts[1:]:
            child = os.open(component, flags, dir_fd=directory)
            os.close(directory)
            directory = child
        return directory
    except BaseException:
        os.close(directory)
        raise


def _open_upload_directory(*, create: bool = False) -> int:
    home = _open_directory(Path.home())
    try:
        if create:
            with suppress(FileExistsError):
                os.mkdir(UPLOAD_DIRECTORY, mode=0o700, dir_fd=home)
        return os.open(UPLOAD_DIRECTORY, _directory_flags(), dir_fd=home)
    finally:
        os.close(home)


def _read_file(directory: int, filename: str) -> bytes:
    validate_filename(filename)
    # O_NONBLOCK prevents a substituted FIFO/device from blocking before fstat rejects it.
    descriptor = os.open(
        filename, os.O_RDONLY | _posix_flag("O_NOFOLLOW") | _posix_flag("O_NONBLOCK"), dir_fd=directory
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Only regular uploaded files can be read.")
        if metadata.st_nlink != 1:
            raise ValueError("Uploaded files must not have hard links.")
        if metadata.st_size > MAX_FILE_BYTES:
            raise ValueError("Only UTF-8 files of at most 1,000,000 bytes can be read.")
    except BaseException:
        os.close(descriptor)
        raise
    with os.fdopen(descriptor, "rb") as file:
        # Recheck the bound in case the file grew after fstat.
        data = file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Only UTF-8 files of at most 1,000,000 bytes can be read.")
    data.decode("utf-8")
    return data


def list_uploaded_files() -> list[str]:
    """List regular files only; a session with no uploads has an empty list."""
    try:
        directory = _open_upload_directory()
    except FileNotFoundError:
        return []
    try:
        with os.scandir(directory) as entries:
            return sorted(
                entry.name
                for entry in entries
                if entry.is_file(follow_symlinks=False) and entry.stat(follow_symlinks=False).st_nlink == 1
            )
    finally:
        os.close(directory)


def read_uploaded_file(filename: str) -> str:
    """Read only one file in the current sandbox's HOME/sample_files directory."""
    validate_filename(filename)
    directory = _open_upload_directory()
    try:
        return _read_file(directory, filename).decode("utf-8")
    finally:
        os.close(directory)


def read_upload_source(source: Path) -> bytes:
    """Read the operator-selected source portably; sandbox access remains descriptor-relative."""
    validate_filename(source.name)
    source = source.expanduser().resolve(strict=True)
    if not source.is_file():
        raise ValueError("The upload source must be a regular UTF-8 file.")
    with source.open("rb") as file:
        metadata = os.fstat(file.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("The upload source must be a regular UTF-8 file.")
        if metadata.st_size > MAX_FILE_BYTES:
            raise ValueError("Only UTF-8 files of at most 1,000,000 bytes can be uploaded.")
        data = file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Only UTF-8 files of at most 1,000,000 bytes can be uploaded.")
    data.decode("utf-8")
    return data


def write_local_upload(filename: str, data: bytes) -> None:
    """Stage an explicit local upload under HOME, not in the code directory."""
    validate_filename(filename)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Only UTF-8 files of at most 1,000,000 bytes can be uploaded.")
    data.decode("utf-8")
    directory = _open_upload_directory(create=True)
    try:
        descriptor = os.open(
            filename,
            os.O_WRONLY | os.O_CREAT | _posix_flag("O_NOFOLLOW") | _posix_flag("O_NONBLOCK"),
            mode=0o600,
            dir_fd=directory,
        )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("Only regular uploaded files can be written.")
            if metadata.st_nlink != 1:
                raise ValueError("Uploaded files must not have hard links.")
        except BaseException:
            os.close(descriptor)
            raise
        with os.fdopen(descriptor, "wb") as file:
            file.truncate()
            file.write(data)
    finally:
        os.close(directory)
