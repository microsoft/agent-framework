# Copyright (c) Microsoft. All rights reserved.

from importlib import metadata as _metadata
from pathlib import Path as _Path
from typing import Any, cast

try:
    import tomllib as _toml  # type: ignore # Python 3.11+
except ModuleNotFoundError:  # Python 3.10
    import tomli as _toml  # type: ignore


def _load_pyproject() -> dict[str, Any]:
    pyproject = (_Path(__file__).resolve().parents[1] / "pyproject.toml").read_text("utf-8")
    return cast(dict[str, Any], _toml.loads(pyproject))  # type: ignore


def _version() -> str:
    try:
        return _metadata.version("agent-framework")
    except _metadata.PackageNotFoundError as ex:
        data = _load_pyproject()
        project = cast(dict[str, Any], data.get("project", {}))
        version = project.get("version")
        if isinstance(version, str):
            return version
        raise RuntimeError("pyproject.toml missing project.version") from ex


__version__ = _version()
__all__ = ["__version__"]
