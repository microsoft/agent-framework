# Copyright (c) Microsoft. All rights reserved.

"""Provide the standard TOML reader on every supported Python version."""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

__all__ = ["tomllib"]
