# Copyright (c) Microsoft. All rights reserved.
"""Enforce Python package coverage according to package lifecycle."""

# ruff:file-ignore[print]
# ruff:file-ignore[implicit-namespace-package]

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET  # ruff:ignore[suspicious-xml-etree-import]
from dataclasses import dataclass
from pathlib import Path

import tomllib

DEVELOPMENT_STATUS_PREFIX = "Development Status :: "
ENFORCED_DEVELOPMENT_STATUS = 4
EXEMPT_PACKAGES = {"devui", "lab"}


@dataclass(frozen=True)
class PackagePolicy:
    """Coverage policy derived from a package's project metadata."""

    directory: str
    distribution_name: str
    development_status: int
    development_status_label: str
    enforced: bool
    exempt: bool


@dataclass
class CoverageStats:
    """Line and branch coverage counters."""

    lines_valid: int = 0
    lines_covered: int = 0
    branches_valid: int = 0
    branches_covered: int = 0

    @property
    def line_coverage_percent(self) -> float:
        """Return line coverage as a percentage."""
        if not self.lines_valid:
            return 0
        return self.lines_covered / self.lines_valid * 100


def normalize_coverage_path(path: str) -> str:
    """Normalize a coverage path for matching."""
    return path.replace("\\", "/").lstrip("./")


def load_package_policies(packages_dir: Path) -> list[PackagePolicy]:
    """Load lifecycle-based coverage policies from package pyproject files."""
    policies: list[PackagePolicy] = []
    for pyproject_path in sorted(packages_dir.glob("*/pyproject.toml")):
        with pyproject_path.open("rb") as pyproject_file:
            pyproject = tomllib.load(pyproject_file)

        project = pyproject.get("project", {})
        distribution_name = str(project.get("name", "")).strip()
        if not distribution_name:
            raise ValueError(f"{pyproject_path}: project.name is required")

        status_classifiers = [
            classifier
            for classifier in project.get("classifiers", [])
            if classifier.startswith(DEVELOPMENT_STATUS_PREFIX)
        ]
        if len(status_classifiers) != 1:
            raise ValueError(
                f"{pyproject_path}: expected exactly one Development Status classifier, found {len(status_classifiers)}"
            )

        match = re.fullmatch(r"Development Status :: (\d+) - (.+)", status_classifiers[0])
        if match is None:
            raise ValueError(f"{pyproject_path}: malformed Development Status classifier")

        directory = pyproject_path.parent.name
        development_status = int(match.group(1))
        exempt = directory in EXEMPT_PACKAGES
        policies.append(
            PackagePolicy(
                directory=directory,
                distribution_name=distribution_name,
                development_status=development_status,
                development_status_label=match.group(2),
                enforced=development_status >= ENFORCED_DEVELOPMENT_STATUS and not exempt,
                exempt=exempt,
            )
        )

    if not policies:
        raise ValueError(f"No package pyproject.toml files found below {packages_dir}")
    return policies


def parse_coverage_xml(xml_path: Path) -> tuple[dict[str, CoverageStats], float, float]:
    """Parse Cobertura XML and aggregate coverage by package directory."""
    root = ET.parse(xml_path).getroot()  # ruff:ignore[suspicious-xml-element-tree-usage]  # Trusted CI-generated coverage report.
    package_stats: dict[str, CoverageStats] = {}

    for class_elem in root.findall(".//class"):
        file_path = normalize_coverage_path(class_elem.get("filename", ""))
        path_parts = file_path.split("/")
        try:
            packages_index = path_parts.index("packages")
            package_directory = path_parts[packages_index + 1]
        except (ValueError, IndexError):
            continue

        stats = package_stats.setdefault(package_directory, CoverageStats())
        for line in class_elem.findall(".//line"):
            stats.lines_valid += 1
            if int(line.get("hits", 0)) > 0:
                stats.lines_covered += 1

            if line.get("branch") != "true":
                continue
            condition_coverage = line.get("condition-coverage", "")
            match = re.search(r"\((\d+)/(\d+)\)", condition_coverage)
            if match is not None:
                stats.branches_covered += int(match.group(1))
                stats.branches_valid += int(match.group(2))

    return (
        package_stats,
        float(root.get("line-rate", 0)) * 100,
        float(root.get("branch-rate", 0)) * 100,
    )


def check_coverage(xml_path: Path, threshold: float, packages_dir: Path) -> bool:
    """Check all lifecycle-enforced packages against the coverage threshold."""
    policies = load_package_policies(packages_dir)
    package_stats, overall_line_coverage, overall_branch_coverage = parse_coverage_xml(xml_path)

    print("\n" + "=" * 110)
    print("PYTHON PACKAGE TEST COVERAGE")
    print("=" * 110)
    print(f"Overall Line Coverage:   {overall_line_coverage:.1f}%")
    print(f"Overall Branch Coverage: {overall_branch_coverage:.1f}%")
    print(f"Enforced Threshold:      {threshold:.1f}%")
    print("-" * 110)
    print(f"{'Package':<48} {'Stage':<20} {'Policy':<14} {'Lines':<12} {'Line Cov':<10}")
    print("-" * 110)

    failed_packages: list[str] = []
    for policy in sorted(policies, key=lambda item: (not item.enforced, item.distribution_name)):
        stats = package_stats.get(policy.directory)
        if policy.exempt:
            policy_label = "EXEMPT"
        elif policy.enforced:
            policy_label = "ENFORCED"
        else:
            policy_label = "REPORT ONLY"

        if stats is None:
            lines = "-"
            coverage = "missing"
            if policy.enforced:
                failed_packages.append(f"{policy.distribution_name} (missing from coverage report)")
        else:
            lines = f"{stats.lines_covered}/{stats.lines_valid}"
            coverage = f"{stats.line_coverage_percent:.1f}%"
            if policy.enforced and stats.line_coverage_percent < threshold:
                failed_packages.append(f"{policy.distribution_name} ({coverage})")

        stage = f"{policy.development_status} - {policy.development_status_label}"
        print(f"{policy.distribution_name:<48} {stage:<20} {policy_label:<14} {lines:<12} {coverage:<10}")

    print("-" * 110)
    if failed_packages:
        print(f"\nFAILED: Enforced packages below {threshold:.1f}% or missing:")
        for package in failed_packages:
            print(f"  - {package}")
        return False

    print(f"\nPASSED: All non-exempt Beta-or-higher packages meet {threshold:.1f}% line coverage.")
    return True


def main() -> int:
    """Run the coverage policy check."""
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <coverage-xml-path> <threshold>")
        return 1

    try:
        threshold = float(sys.argv[2])
    except ValueError:
        print(f"Error: Invalid threshold value: {sys.argv[2]}")
        return 1

    repository_root = Path(__file__).resolve().parents[2]
    try:
        passed = check_coverage(
            Path(sys.argv[1]),
            threshold,
            repository_root / "python" / "packages",
        )
    except (FileNotFoundError, ET.ParseError, ValueError) as error:
        print(f"Error: {error}")
        return 1
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
