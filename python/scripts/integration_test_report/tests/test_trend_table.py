# Copyright (c) Microsoft. All rights reserved.

"""Regression tests for test names in Markdown trend tables."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

from scripts.integration_test_report.aggregate import generate_trend_report, load_current_run


class TrendTableTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def load_run(self, names: list[str], *, dotnet: bool = False) -> dict:
        reports = self.root / "reports"
        if dotnet:
            directory = reports / "dotnet-test-results-net10.0-ubuntu-latest"
            filename = "results.junit"
        else:
            directory = reports / "test-results-openai"
            filename = "pytest.xml"
        directory.mkdir(parents=True, exist_ok=True)
        suite = ElementTree.Element("testsuite", tests=str(len(names)))
        for name in names:
            ElementTree.SubElement(suite, "testcase", classname="test_report_input", name=name, time="0")
        ElementTree.ElementTree(suite).write(directory / filename, encoding="utf-8")
        return load_current_run(reports)

    def test_python_name_pipe_stays_in_its_cell(self) -> None:
        report = generate_trend_report([self.load_run(["test_echo[a|b]"])])
        self.assertIn("| `test_echo[a\\|b]` | `test_report_input` | OpenAI |", report)

    def test_multiple_pipes_stay_in_the_test_name(self) -> None:
        report = generate_trend_report([self.load_run(["test_echo[a|b|c]"])])
        self.assertIn("| `test_echo[a\\|b\\|c]` |", report)

    def test_dotnet_name_pipe_stays_in_its_cell(self) -> None:
        report = generate_trend_report([self.load_run(["TestEcho(a|b)"], dotnet=True)])
        self.assertIn("| `TestEcho(a\\|b)` | `test_report_input` |", report)
        self.assertIn("## net10.0 (ubuntu)", report)

    def test_plain_name_and_summary_are_unchanged(self) -> None:
        run = self.load_run(["test_echo[plain]"])
        report = generate_trend_report([run])
        self.assertIn("| `test_echo[plain]` | `test_report_input` | OpenAI |", report)
        self.assertEqual(run["summary"], {"total": 1, "passed": 1, "failed": 0, "skipped": 0})

    def test_generating_report_does_not_change_history(self) -> None:
        run = self.load_run(["test_echo[a|b]", "test_echo[plain]"])
        history = [run, copy.deepcopy(run)]
        original = copy.deepcopy(history)
        generate_trend_report(history)
        self.assertEqual(history, original)
        self.assertIn("test_report_input::test_echo[a|b]", run["results"])
        self.assertEqual(run["summary"]["total"], 2)
        self.assertEqual(run["summary"]["passed"], 2)

    def test_cli_escapes_report_but_preserves_history_keys(self) -> None:
        self.load_run(["test_echo[a|b]", "test_echo[plain]"])
        history = self.root / "history.json"
        output = self.root / "report.md"
        script = Path(__file__).resolve().parents[1] / "aggregate.py"
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", str(script), str(self.root / "reports"), str(history), str(output)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(history.read_text(encoding="utf-8"))["runs"][0]
        self.assertIn("test_report_input::test_echo[a|b]", data["results"])
        self.assertEqual(data["summary"]["passed"], 2)
        report = output.read_text(encoding="utf-8")
        self.assertIn("| `test_echo[a\\|b]` | `test_report_input` | OpenAI |", report)
        self.assertIn("| `test_echo[plain]` | `test_report_input` | OpenAI |", report)


if __name__ == "__main__":
    unittest.main()
