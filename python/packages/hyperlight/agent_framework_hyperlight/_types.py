# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple, TypeAlias


class FileMount(NamedTuple):
    """Map a host file or directory into the sandbox input tree."""

    host_path: str | Path
    mount_path: str


FileMountHostPath: TypeAlias = str | Path
FileMountInput: TypeAlias = str | tuple[FileMountHostPath, str] | FileMount


class AllowedDomain(NamedTuple):
    """Allow outbound requests to one target, optionally restricted to specific HTTP methods."""

    target: str
    methods: tuple[str, ...] | None = None


AllowedDomainInput: TypeAlias = str | tuple[str, str | Sequence[str]] | AllowedDomain
