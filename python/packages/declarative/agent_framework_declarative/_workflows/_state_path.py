# Copyright (c) Microsoft. All rights reserved.

"""Shared identifier policy for object-attribute steps in workflow state paths."""

import re

_SAFE_PATH_SEGMENT_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def _is_safe_path_segment(segment: str) -> bool:  # pyright: ignore[reportUnusedFunction]
    """Return whether an object-attribute segment is a declarative identifier."""
    return _SAFE_PATH_SEGMENT_RE.fullmatch(segment) is not None
