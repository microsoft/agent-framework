#!/usr/bin/env python3
# Copyright (c) Microsoft. All rights reserved.
"""Check Python test coverage against threshold for enforced modules.

This script parses a Cobertura XML coverage report and enforces a minimum
coverage threshold on specific modules. Non-enforced modules are reported
for visibility but don't block the build.

Usage:
    python python-check-coverage.py <coverage-xml-path> <threshold>

Example:
    python python-check-coverage.py python-coverage.xml 85
"""

import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass

# =============================================================================
# ENFORCED MODULES CONFIGURATION
# =============================================================================
# Add or remove modules from this set to control which packages must meet
# the coverage threshold. Only these modules will fail the build if below
# threshold. Other modules are reported for visibility only.
#
# Module paths should match the package paths as they appear in the coverage
# report (e.g., "packages.azure-ai.agent_framework_azure_ai" for packages/azure-ai).
# Sub-modules can be included by specifying their full path.
# =============================================================================
ENFORCED_MODULES: set[str] = {
    "packages.azure-ai.agent_framework_azure_ai",
    "packages.core.agent_framework",
    "packages.core.agent_framework._workflows",
    "packages.purview.agent_framework_purview",
    "packages.anthropic.agent_framework_anthropic",
    # Add more modules here as coverage improves:
    # "packages.azure-ai-search.agent_framework_azure_ai_search",
}


@dataclass
class PackageCoverage:
    """Coverage data for a single package."""

    name: str
    line_rate: float
    branch_rate: float
    lines_valid: int
    lines_covered: int
    branches_valid: int
    branches_covered: int

    @property
    def line_coverage_percent(self) -> float:
        """Return line coverage as a percentage."""
        return self.line_rate * 100

    @property
    def branch_coverage_percent(self) -> float:
        """Return branch coverage as a percentage."""
        return self.branch_rate * 100


def parse_coverage_xml(
    xml_path: str,
) -> tuple[dict[str, PackageCoverage], float, float]:
    """Parse Cobertura XML and extract per-package coverage data.

    Args:
        xml_path: Path to the Cobertura XML coverage report.

    Returns:
        A tuple of (packages_dict, overall_line_rate, overall_branch_rate).
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Get overall coverage from root element
    overall_line_rate = float(root.get("line-rate", 0))
    overall_branch_rate = float(root.get("branch-rate", 0))

    packages: dict[str, PackageCoverage] = {}

    for package in root.findall(".//package"):
        package_path = package.get("name", "unknown")

        line_rate = float(package.get("line-rate", 0))
        branch_rate = float(package.get("branch-rate", 0))

        # Count lines and branches from classes within this package
        lines_valid = 0
        lines_covered = 0
        branches_valid = 0
        branches_covered = 0

        for class_elem in package.findall(".//class"):
            for line in class_elem.findall(".//line"):
                lines_valid += 1
                if int(line.get("hits", 0)) > 0:
                    lines_covered += 1
                # Branch coverage from line elements
                if line.get("branch") == "true":
                    condition_coverage = line.get("condition-coverage", "")
                    if condition_coverage:
                        # Parse "X% (covered/total)" format
                        try:
                            coverage_parts = (
                                condition_coverage.split("(")[1].rstrip(")").split("/")
                            )
                            branches_covered += int(coverage_parts[0])
                            branches_valid += int(coverage_parts[1])
                        except (IndexError, ValueError):
                            # Ignore malformed condition-coverage strings; treat this line as having no branch data.
                            pass

        # Use full package path as the key (no aggregation)
        packages[package_path] = PackageCoverage(
            name=package_path,
            line_rate=line_rate if lines_valid == 0 else lines_covered / lines_valid,
            branch_rate=branch_rate
            if branches_valid == 0
            else branches_covered / branches_valid,
            lines_valid=lines_valid,
            lines_covered=lines_covered,
            branches_valid=branches_valid,
            branches_covered=branches_covered,
        )

    return packages, overall_line_rate, overall_branch_rate


def format_coverage_value(coverage: float, threshold: float, is_enforced: bool) -> str:
    """Format a coverage value with optional pass/fail indicator.

    Args:
        coverage: Coverage percentage (0-100).
        threshold: Minimum required coverage percentage.
        is_enforced: Whether this module is enforced.

    Returns:
        Formatted string like "85.5%" or "85.5% ✅" or "75.0% ❌".
    """
    formatted = f"{coverage:.1f}%"
    if is_enforced:
        icon = "✅" if coverage >= threshold else "❌"
        formatted = f"{formatted} {icon}"
    return formatted


def print_coverage_table(
    packages: dict[str, PackageCoverage],
    threshold: float,
    overall_line_rate: float,
    overall_branch_rate: float,
) -> None:
    """Print a formatted coverage summary table.

    Args:
        packages: Dictionary of package name to coverage data.
        threshold: Minimum required coverage percentage.
        overall_line_rate: Overall line coverage rate (0-1).
        overall_branch_rate: Overall branch coverage rate (0-1).
    """
    print("\n" + "=" * 80)
    print("PYTHON TEST COVERAGE REPORT")
    print("=" * 80)

    # Overall coverage
    print(f"\nOverall Line Coverage:   {overall_line_rate * 100:.1f}%")
    print(f"Overall Branch Coverage: {overall_branch_rate * 100:.1f}%")
    print(f"Threshold:               {threshold}%")

    # Package table
    print("\n" + "-" * 110)
    print(f"{'Package':<80} {'Lines':<15} {'Line Cov':<15}")
    print("-" * 110)

    # Sort: enforced modules first, then alphabetically
    sorted_packages = sorted(
        packages.values(),
        key=lambda p: (p.name not in ENFORCED_MODULES, p.name),
    )

    for pkg in sorted_packages:
        is_enforced = pkg.name in ENFORCED_MODULES
        enforced_marker = "[ENFORCED] " if is_enforced else ""
        line_cov = format_coverage_value(
            pkg.line_coverage_percent, threshold, is_enforced
        )
        lines_info = f"{pkg.lines_covered}/{pkg.lines_valid}"
        package_label = f"{enforced_marker}{pkg.name}"

        print(f"{package_label:<80} {lines_info:<15} {line_cov:<15}")

    print("-" * 110)


def check_coverage(xml_path: str, threshold: float) -> bool:
    """Check if all enforced modules meet the coverage threshold.

    Args:
        xml_path: Path to the Cobertura XML coverage report.
        threshold: Minimum required coverage percentage.

    Returns:
        True if all enforced modules pass, False otherwise.
    """
    packages, overall_line_rate, overall_branch_rate = parse_coverage_xml(xml_path)

    print_coverage_table(packages, threshold, overall_line_rate, overall_branch_rate)

    # Check enforced modules
    failed_modules: list[str] = []
    missing_modules: list[str] = []

    for module_name in ENFORCED_MODULES:
        if module_name not in packages:
            missing_modules.append(module_name)
            continue

        pkg = packages[module_name]
        if pkg.line_coverage_percent < threshold:
            failed_modules.append(f"{module_name} ({pkg.line_coverage_percent:.1f}%)")

    # Report results
    if missing_modules:
        print(
            f"\n❌ FAILED: Enforced modules not found in coverage report: {', '.join(missing_modules)}"
        )
        return False

    if failed_modules:
        print(
            f"\n❌ FAILED: The following enforced modules are below {threshold}% coverage threshold:"
        )
        for module in failed_modules:
            print(f"   - {module}")
        print("\nTo fix: Add more tests to improve coverage for the failing modules.")
        return False

    if ENFORCED_MODULES:
        found_enforced = [m for m in ENFORCED_MODULES if m in packages]
        if found_enforced:
            print(
                f"\n✅ PASSED: All enforced modules meet the {threshold}% coverage threshold."
            )

    return True


def main() -> int:
    """Main entry point.

    Returns:
        Exit code: 0 for success, 1 for failure.
    """
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <coverage-xml-path> <threshold>")
        print(f"Example: {sys.argv[0]} python-coverage.xml 85")
        return 1

    xml_path = sys.argv[1]
    try:
        threshold = float(sys.argv[2])
    except ValueError:
        print(f"Error: Invalid threshold value: {sys.argv[2]}")
        return 1

    try:
        success = check_coverage(xml_path, threshold)
        return 0 if success else 1
    except FileNotFoundError:
        print(f"Error: Coverage file not found: {xml_path}")
        return 1
    except ET.ParseError as e:
        print(f"Error: Failed to parse coverage XML: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
