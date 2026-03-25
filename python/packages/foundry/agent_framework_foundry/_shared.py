# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

from agent_framework import Content

if sys.version_info >= (3, 11):
    from typing import TypedDict  # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

logger = logging.getLogger("agent_framework.foundry")


class FoundryProjectSettings(TypedDict, total=False):
    """Foundry project settings loaded from FOUNDRY_ environment variables."""

    project_endpoint: str | None


def resolve_file_ids(file_ids: Sequence[str | Content] | None) -> list[str] | None:
    """Resolve file IDs from strings or hosted-file Content objects."""
    if not file_ids:
        return None

    resolved: list[str] = []
    for item in file_ids:
        if isinstance(item, str):
            if not item:
                raise ValueError("file_ids must not contain empty strings.")
            resolved.append(item)
        elif isinstance(item, Content):
            if item.type != "hosted_file":
                raise ValueError(
                    f"Unsupported Content type {item.type!r} for code interpreter file_ids. "
                    "Only Content.from_hosted_file() is supported."
                )
            if item.file_id is None:
                raise ValueError(
                    "Content.from_hosted_file() item is missing a file_id. "
                    "Ensure the Content object has a valid file_id before using it in file_ids."
                )
            resolved.append(item.file_id)

    return resolved if resolved else None
