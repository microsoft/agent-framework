# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

FilesystemMode = Literal["none", "read_only", "read_write"]
NetworkMode = Literal["none", "allow_list"]


@dataclass(frozen=True, slots=True)
class FileMount:
    """Map a host file or directory into the sandbox input tree."""

    host_path: str | Path
    mount_path: str
