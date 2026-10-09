# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path

from packaging.version import Version

from scripts.dependencies.upgrade_dev_dependencies import (
    _apply_tool_requirement_replacements,
    _collect_tool_requirement_replacements,
)


class _VersionCatalog:
    def __init__(self, versions: dict[str, list[str]]) -> None:
        self._versions = versions

    def get(self, package_name: str) -> list[Version]:
        return [Version(version) for version in self._versions.get(package_name, [])]


def test_collect_tool_requirement_replacements_preserves_extras_and_markers(tmp_path: Path) -> None:
    requirements_file = tmp_path / "testing.txt"
    requirements_file.write_text('# Test tools\npytest==9.1.1\npytest-xdist[psutil]==3.8.0; python_version >= "3.10"\n')
    catalog = _VersionCatalog({
        "pytest": ["9.1.1", "9.2.0"],
        "pytest-xdist": ["3.8.0", "3.9.0"],
    })

    replacements = _collect_tool_requirement_replacements(requirements_file, catalog=catalog)  # type: ignore[arg-type]

    assert replacements == {
        "pytest==9.1.1": "pytest==9.2.0",
        'pytest-xdist[psutil]==3.8.0; python_version >= "3.10"': (
            'pytest-xdist[psutil]==3.9.0; python_version >= "3.10"'
        ),
    }


def test_apply_tool_requirement_replacements_preserves_includes_and_comments(tmp_path: Path) -> None:
    requirements_file = tmp_path / "all.txt"
    requirements_file.write_text("# Shared tools\n-r runtime.txt\nruff==0.16.10\n")

    _apply_tool_requirement_replacements(requirements_file, {"ruff==0.16.10": "ruff==0.17.0"})

    assert requirements_file.read_text() == "# Shared tools\n-r runtime.txt\nruff==0.17.0\n"
