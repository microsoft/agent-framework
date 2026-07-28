# Copyright (c) Microsoft. All rights reserved.

# ruff:file-ignore[implicit-namespace-package, undocumented-public-class, undocumented-public-method]

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "python_check_coverage.py"
SPEC = importlib.util.spec_from_file_location("python_check_coverage", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
coverage_checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = coverage_checker
SPEC.loader.exec_module(coverage_checker)


class CoveragePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.packages_dir = self.root / "packages"
        self.packages_dir.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_package(self, directory: str, name: str, status: str) -> None:
        package_dir = self.packages_dir / directory
        package_dir.mkdir()
        (package_dir / "pyproject.toml").write_text(
            f"""
[project]
name = "{name}"
classifiers = ["Development Status :: {status}"]
""".strip()
        )

    def write_coverage(self, files: dict[str, list[int]]) -> Path:
        classes = []
        total_lines = 0
        covered_lines = 0
        for file_path, hits in files.items():
            lines = []
            for line_number, hit_count in enumerate(hits, start=1):
                total_lines += 1
                covered_lines += hit_count > 0
                lines.append(f'<line number="{line_number}" hits="{hit_count}"/>')
            classes.append(f'<class filename="{file_path}"><lines>{"".join(lines)}</lines></class>')

        line_rate = covered_lines / total_lines if total_lines else 0
        xml_path = self.root / "coverage.xml"
        xml_path.write_text(
            f"""
<coverage line-rate="{line_rate}" branch-rate="0">
  <packages>
    <package name="test">
      <classes>{"".join(classes)}</classes>
    </package>
  </packages>
</coverage>
""".strip()
        )
        return xml_path

    def test_load_package_policies_uses_lifecycle_exemptions(self) -> None:
        self.write_package("alpha", "agent-framework-alpha", "3 - Alpha")
        self.write_package("beta", "agent-framework-beta", "4 - Beta")
        self.write_package("stable", "agent-framework-stable", "5 - Production/Stable")
        self.write_package("devui", "agent-framework-devui", "4 - Beta")
        self.write_package("lab", "agent-framework-lab", "4 - Beta")

        policies = {policy.directory: policy for policy in coverage_checker.load_package_policies(self.packages_dir)}

        self.assertFalse(policies["alpha"].enforced)
        self.assertTrue(policies["beta"].enforced)
        self.assertTrue(policies["stable"].enforced)
        self.assertTrue(policies["devui"].exempt)
        self.assertFalse(policies["devui"].enforced)
        self.assertTrue(policies["lab"].exempt)
        self.assertFalse(policies["lab"].enforced)

    def test_load_package_policies_rejects_missing_lifecycle(self) -> None:
        package_dir = self.packages_dir / "missing"
        package_dir.mkdir()
        (package_dir / "pyproject.toml").write_text('[project]\nname = "agent-framework-missing"\n')

        with self.assertRaisesRegex(ValueError, "exactly one Development Status"):
            coverage_checker.load_package_policies(self.packages_dir)

    def test_parse_coverage_aggregates_nested_modules_by_distribution(self) -> None:
        xml_path = self.write_coverage({
            "packages/core/agent_framework/_agents.py": [1, 0],
            "packages/core/agent_framework/_workflows/_workflow.py": [1, 1],
        })

        package_stats, _, _ = coverage_checker.parse_coverage_xml(xml_path)

        self.assertEqual(package_stats["core"].lines_valid, 4)
        self.assertEqual(package_stats["core"].lines_covered, 3)

    def test_beta_package_below_threshold_fails(self) -> None:
        self.write_package("beta", "agent-framework-beta", "4 - Beta")
        xml_path = self.write_coverage({"packages/beta/agent_framework_beta/client.py": [1, 0]})

        self.assertFalse(coverage_checker.check_coverage(xml_path, 85, self.packages_dir))

    def test_missing_beta_package_fails(self) -> None:
        self.write_package("beta", "agent-framework-beta", "4 - Beta")
        xml_path = self.write_coverage({})

        self.assertFalse(coverage_checker.check_coverage(xml_path, 85, self.packages_dir))

    def test_alpha_and_exempt_packages_do_not_fail(self) -> None:
        self.write_package("alpha", "agent-framework-alpha", "3 - Alpha")
        self.write_package("devui", "agent-framework-devui", "4 - Beta")
        self.write_package("lab", "agent-framework-lab", "4 - Beta")
        xml_path = self.write_coverage({})

        self.assertTrue(coverage_checker.check_coverage(xml_path, 85, self.packages_dir))

    def test_beta_package_at_threshold_passes(self) -> None:
        self.write_package("beta", "agent-framework-beta", "4 - Beta")
        xml_path = self.write_coverage({"packages/beta/agent_framework_beta/client.py": [1] * 17 + [0] * 3})

        self.assertTrue(coverage_checker.check_coverage(xml_path, 85, self.packages_dir))


if __name__ == "__main__":
    unittest.main()
