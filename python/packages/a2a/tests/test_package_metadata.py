# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path

import tomllib
from packaging.requirements import Requirement
from packaging.version import Version


def test_a2a_sdk_dependency_range_tracks_validated_sdk_line() -> None:
    pyproject_data = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    a2a_sdk_requirement = next(
        Requirement(dependency)
        for dependency in pyproject_data["project"]["dependencies"]
        if dependency.startswith("a2a-sdk")
    )

    assert Version("0.3.0") in a2a_sdk_requirement.specifier
    assert Version("0.3.25") in a2a_sdk_requirement.specifier
    assert Version("0.4.0") not in a2a_sdk_requirement.specifier
