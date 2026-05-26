# Copyright (c) Microsoft. All rights reserved.

"""Public types for ``agent-framework-local-codeact``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NamedTuple, TypeAlias

ExecutionMode: TypeAlias = Literal["subprocess", "unsafe_in_process"]
MountMode: TypeAlias = Literal["overlay", "read-only", "read-write"]


class FileMount(NamedTuple):
    """Describe a directory exposed to generated code by direct path.

    The local CodeAct executor does not provide a virtual filesystem. The
    ``mount_path`` is a stable display/capture path used in instructions and
    returned file metadata; generated code receives and uses ``host_path`` as a
    direct path inside the surrounding sandbox.
    """

    host_path: str | Path
    mount_path: str
    mode: MountMode = "overlay"
    write_bytes_limit: int | None = None


FileMountHostPath: TypeAlias = str | Path
FileMountInput: TypeAlias = str | tuple[FileMountHostPath, str] | FileMount


@dataclass(frozen=True)
class ProcessExecutionLimits:
    """Defense-in-depth limits for local generated-code execution.

    These limits help keep accidental or buggy generated code bounded. They are
    not a security boundary and should be paired with external sandboxing.
    """

    timeout_seconds: float = 10.0
    max_code_bytes: int = 64 * 1024
    max_stdout_bytes: int = 64 * 1024
    max_stderr_bytes: int = 64 * 1024
    max_result_bytes: int = 128 * 1024
    max_captured_file_bytes: int = 5 * 1024 * 1024
    max_total_captured_file_bytes: int = 25 * 1024 * 1024
