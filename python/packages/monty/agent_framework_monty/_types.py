# Copyright (c) Microsoft. All rights reserved.

"""Public types for ``agent-framework-monty``.

Mirrors ``agent_framework_hyperlight._types`` where the Monty runtime exposes
an equivalent concept so users can move between the two providers with minimal
churn.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, NamedTuple, TypeAlias

#: Allowed Monty mount modes. ``overlay`` (the Monty default) buffers writes
#: in-memory and is therefore not visible to the host after execution.
#: ``read-only`` rejects writes. ``read-write`` writes through to the host
#: directory.
MountMode: TypeAlias = Literal["overlay", "read-only", "read-write"]


class FileMount(NamedTuple):
    """Map a host directory into the Monty sandbox.

    Mirrors :class:`agent_framework_hyperlight.FileMount` with two extra
    fields that surface Monty's underlying ``MountDir`` capabilities:
    ``mode`` selects read-only / read-write / overlay semantics, and
    ``write_bytes_limit`` caps the total bytes written through this mount.
    """

    host_path: str | Path
    mount_path: str
    mode: MountMode = "overlay"
    write_bytes_limit: int | None = None


FileMountHostPath: TypeAlias = str | Path
FileMountInput: TypeAlias = str | tuple[FileMountHostPath, str] | FileMount
