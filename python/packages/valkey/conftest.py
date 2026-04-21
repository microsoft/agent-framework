# Copyright (c) Microsoft. All rights reserved.

"""Skip valkey test collection when valkey-glide is not installed (e.g., on Windows)."""

collect_ignore_glob: list[str] = []

try:
    import glide  # noqa: F401
except ImportError:
    collect_ignore_glob.append("tests/*.py")
