# Copyright (c) Microsoft. All rights reserved.

"""Private filesystem security helpers."""

from __future__ import annotations

import stat
from pathlib import Path


def is_link_or_reparse_point(path: Path) -> bool:
    """Return whether ``path`` is a symbolic link, junction, or other reparse point."""
    path_stat = path.lstat()
    if stat.S_ISLNK(path_stat.st_mode):
        return True

    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True

    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(path_stat, "st_file_attributes", 0)
    return bool(reparse_attribute and file_attributes & reparse_attribute)
