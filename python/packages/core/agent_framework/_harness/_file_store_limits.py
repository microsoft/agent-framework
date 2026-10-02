# Copyright (c) Microsoft. All rights reserved.

"""Capacity accounting shared by the built-in file stores."""

from __future__ import annotations

from dataclasses import dataclass


class _FileStoreQuotaError(ValueError):
    """A configured storage limit would be exceeded, without revealing paths or identities."""

    def __init__(self, name: str, limit: int, requested: int) -> None:
        super().__init__(f"File store quota exceeded: {name}={limit}, requested={requested}.")


@dataclass(frozen=True)
class _FileStoreLimits:
    max_file_bytes: int | None
    max_files: int | None
    max_total_bytes: int | None

    @classmethod
    def create(
        cls, max_file_bytes: int | None, max_files: int | None, max_total_bytes: int | None
    ) -> _FileStoreLimits | None:
        """Validate explicit limits; an entirely unconfigured store keeps its original path."""
        values = (max_file_bytes, max_files, max_total_bytes)
        for name, value in zip(("max_file_bytes", "max_files", "max_total_bytes"), values, strict=True):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value <= 0):
                raise ValueError(f"{name} must be a positive integer or None.")
        return cls(*values) if any(value is not None for value in values) else None

    def content_size(self, content: str) -> int:
        """Count UTF-8 bytes incrementally before allocating the complete encoded payload."""
        limits = [
            (name, limit)
            for name, limit in (("max_file_bytes", self.max_file_bytes), ("max_total_bytes", self.max_total_bytes))
            if limit is not None
        ]
        ceiling = min((limit for _, limit in limits), default=None)
        chunk_size = min(4096, ceiling + 1) if ceiling is not None else 4096
        size = 0
        for offset in range(0, len(content), chunk_size):
            size += len(content[offset : offset + chunk_size].encode("utf-8"))
            for name, limit in limits:
                if size > limit:
                    raise _FileStoreQuotaError(name, limit, size)
        return size

    def check_usage(self, file_count: int, total_bytes: int) -> None:
        """Check the resulting root usage before modifying a file."""
        for name, limit, requested in (
            ("max_files", self.max_files, file_count),
            ("max_total_bytes", self.max_total_bytes, total_bytes),
        ):
            if limit is not None and requested > limit:
                raise _FileStoreQuotaError(name, limit, requested)

    def check_read(self, file_bytes: int) -> None:
        """Bound whole-file reads, including files written before quotas were enabled."""
        if self.max_file_bytes is not None and file_bytes > self.max_file_bytes:
            raise _FileStoreQuotaError("max_file_bytes", self.max_file_bytes, file_bytes)
