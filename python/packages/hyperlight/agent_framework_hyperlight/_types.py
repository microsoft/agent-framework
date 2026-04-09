# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from pathlib import Path
from typing import Literal, NamedTuple, TypeAlias

FilesystemMode = Literal["none", "read_only", "read_write"]
NetworkMode = Literal["none", "allow_list"]


class FileMount(NamedTuple):
    """Map a host file or directory into the sandbox input tree."""

    host_path: str | Path
    mount_path: str


FileMountHostPath: TypeAlias = str | Path
FileMountInput: TypeAlias = str | tuple[FileMountHostPath, str] | FileMount
