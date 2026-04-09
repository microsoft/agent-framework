# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Literal, NamedTuple, TypeAlias

FilesystemMode = Literal["none", "read_only", "read_write"]
NetworkMode = Literal["none", "allow_list"]


class FileMount(NamedTuple):
    """Map a host file or directory into the sandbox input tree."""

    host_path: str
    mount_path: str


FileMountInput: TypeAlias = str | tuple[str, str] | FileMount
