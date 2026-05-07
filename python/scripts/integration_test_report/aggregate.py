# Copyright (c) Microsoft. All rights reserved.

"""Aggregate per-provider JUnit XML test results and generate a trend report.

Parses JUnit XML files produced by CI jobs — both ``pytest.xml`` (Python) and
xunit v3 ``*.junit`` (dotnet) — merges them into a single run, combines
with historical data, and generates a markdown trend table.

Usage (from CI):
    python aggregate.py <reports-dir> <history-file> <output-file>

The reports directory is expected to contain artifact subdirectories.  Two
layouts are supported:

- **Python (pytest):**  ``test-results-<provider>/pytest.xml``
- **Dotnet (xunit):**   ``dotnet-test-results-<tfm>-<os>/*.junit``
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_HISTORY = 5

STATUS_EMOJI = {
    "passed": "✅",
    "failed": "❌",
    "skipped": "⏭️",
    "xfailed": "⚠️",
    "error": "❌",
}


def _format_run_label(timestamp: str) -> str:
    """Format a timestamp as a compact column label (e.g. '04-16 00:57')."""
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.strftime("%m-%d %H:%M")
    except (ValueError, TypeError):
        return timestamp[:16]


def _derive_provider(directory_name: str) -> str:
    """Derive a provider label from a report directory name.

    Handles both Python and dotnet naming conventions:
    - ``test-results-openai`` → ``OpenAI``
    - ``test-results-azure-openai`` → ``Azure OpenAI``
    - ``dotnet-test-results-net10.0-ubuntu-latest`` → ``net10.0 (ubuntu)``
    """
    # Dotnet convention: dotnet-test-results-<framework>-<os>
    if directory_name.startswith("dotnet-test-results-"):
        raw = directory_name.replace("dotnet-test-results-", "")
        # e.g. "net10.0-ubuntu-latest" → framework="net10.0", os="ubuntu-latest"
        parts = raw.split("-", 1)
        framework = parts[0]
        os_label = parts[1].split("-")[0] if len(parts) > 1 else ""
        return f"{framework} ({os_label})" if os_label else framework

    # Python convention: test-results-<provider>
    raw = directory_name.replace("test-results-", "")
    known = {
        "openai": "OpenAI",
        "azure-openai": "Azure OpenAI",
        "misc": "Misc (Anthropic, Ollama, MCP)",
        "functions": "Functions",
        "foundry": "Foundry",
        "cosmos": "Cosmos",
        "unit": "Unit",
    }
    if raw in known:
        return known[raw]
    parts = raw.split("-")
    return " ".join(p.capitalize() for p in parts)


def _parse_junit_xml(xml_path: Path) -> list[dict[str, str]]:
    """Parse a JUnit XML file and return a list of test result dicts.

    Each dict has keys: ``nodeid``, ``status``, ``duration``, ``message``.
    """
    results: list[dict[str, str]] = []
    try:
        tree = ET.parse(xml_path)  # noqa: S314
    except ET.ParseError as exc:
        print(f"Warning: failed to parse JUnit XML report '{xml_path}': {exc}", file=sys.stderr)
        return results
    root = tree.getroot()

    # Handle both <testsuites><testsuite>... and <testsuite>... layouts
    testcases: list[ET.Element] = []
    if root.tag == "testsuites":
        for suite in root.findall("testsuite"):
            testcases.extend(suite.findall("testcase"))
    elif root.tag == "testsuite":
        testcases = list(root.findall("testcase"))

    for tc in testcases:
        classname = tc.get("classname", "")
        name = tc.get("name", "")
        duration = tc.get("time", "0")

        # Use classname::name as a stable identifier.
        # pytest writes classname as the dotted module path (possibly including
        # a test class), e.g. "packages.openai.tests.openai.test_chat_client"
        # or "packages.openai.tests.openai.test_chat_client.TestClass".
        nodeid = f"{classname}::{name}" if classname else name

        # Extract module/file name from classname for display context.
        # pytest writes classname as a dotted path. For tests inside a class
        # it appends the class name, e.g.:
        #   "packages.foundry.tests.foundry.test_foundry_embedding_client.TestFoundryEmbeddingIntegration"
        # We want the file-level module: "test_foundry_embedding_client"
        #
        # xunit (dotnet) writes classname as the full C# type, e.g.:
        #   "OpenAIChatCompletion.IntegrationTests.ChatCompletionTests"
        # We want the project prefix: "OpenAIChatCompletion"
        if classname:
            parts = classname.rsplit(".", 2)
            # If the last segment starts with uppercase it's a class name — take the one before it
            if len(parts) >= 2 and parts[-1][0:1].isupper():
                # For dotnet: if the penultimate part is "IntegrationTests" or "UnitTests",
                # use the part before that (the project name) instead
                if parts[-2] in ("IntegrationTests", "UnitTests") and len(parts) >= 3:
                    # parts[0] may contain dots — take the last segment of it
                    module = parts[0].rsplit(".", 1)[-1]
                else:
                    module = parts[-2]
            else:
                module = parts[-1]
        else:
            module = ""

        # Determine status from child elements
        failure = tc.find("failure")
        error = tc.find("error")
        skipped = tc.find("skipped")

        if failure is not None:
            status = "failed"
            message = failure.get("message", "")
        elif error is not None:
            status = "error"
            message = error.get("message", "")
        elif skipped is not None:
            # pytest marks xfail as <skipped type="pytest.xfail">
            skip_type = skipped.get("type", "")
            status = "xfailed" if "xfail" in skip_type else "skipped"
            message = skipped.get("message", "")
        else:
            status = "passed"
            message = ""

        results.append({
            "nodeid": nodeid,
            "status": status,
            "duration": duration,
            "message": message,
            "module": module,
        })

    return results


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _discover_xml_files(reports_dir: Path) -> list[tuple[str, Path]]:
    """Discover JUnit XML test result files in artifact subdirectories.

    Handles two directory layouts:
    - **Python (pytest):** ``test-results-<provider>/pytest.xml``
    - **Dotnet (xunit):** ``dotnet-test-results-<tfm>-<os>/*.junit``

    Returns:
        List of ``(directory_name, xml_path)`` tuples.
    """
    xml_files: list[tuple[str, Path]] = []
    if not reports_dir.is_dir():
        return xml_files

    for subdir in sorted(reports_dir.iterdir()):
        if not subdir.is_dir():
            continue

        # Python layout: single pytest.xml per artifact
        pytest_xml = subdir / "pytest.xml"
        if pytest_xml.exists():
            xml_files.append((subdir.name, pytest_xml))
            continue

        # Dotnet layout: multiple *.junit files per artifact
        junit_files = sorted(subdir.rglob("*.junit"))
        for jf in junit_files:
            xml_files.append((subdir.name, jf))

        # Fallback: any .xml file that looks like JUnit (not .trx, not cobertura)
        if not junit_files:
            for xf in sorted(subdir.rglob("*.xml")):
                if xf.suffix == ".xml" and not xf.name.endswith(".cobertura.xml"):
                    xml_files.append((subdir.name, xf))

    return xml_files


def load_current_run(reports_dir: Path) -> dict[str, Any]:
    """Load per-provider JUnit XML reports from the current CI run and merge.

    Supports both pytest (Python) and xunit v3 (dotnet) JUnit XML formats.

    Args:
        reports_dir: Directory containing artifact subdirectories with XML reports.

    Returns:
        Merged run dict with ``timestamp``, ``summary``, ``results``.
    """
    combined_results: dict[str, dict[str, str]] = {}  # nodeid → {status, provider}

    xml_files = _discover_xml_files(reports_dir)

    if not xml_files:
        print(f"Warning: No JUnit XML files found in {reports_dir}")
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
            },
            "results": {},
        }

    # Dotnet tests always run under multiple frameworks, so we always
    # qualify their keys with the provider to ensure deterministic,
    # stable keys across runs regardless of file parse order.
    is_dotnet = any(d.startswith("dotnet-test-results-") for d, _ in xml_files)

    for dir_name, xml_file in xml_files:
        print(f"  Loading: {xml_file}")
        provider = _derive_provider(dir_name)
        tests = _parse_junit_xml(xml_file)
        for test in tests:
            raw_id = test["nodeid"]
            key = f"{provider}::{raw_id}" if is_dotnet else raw_id

            combined_results[key] = {
                "status": test["status"],
                "provider": provider,
                "module": test.get("module", ""),
            }

    # Build per-provider summary counts so the report can show one row per
    # framework (dotnet) or per provider (Python).
    provider_counts: dict[str, dict[str, int]] = {}
    for r in combined_results.values():
        prov = r.get("provider", "Unknown")
        if prov not in provider_counts:
            provider_counts[prov] = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
        provider_counts[prov]["total"] += 1
        st = r["status"]
        if st == "passed":
            provider_counts[prov]["passed"] += 1
        elif st in ("failed", "error"):
            provider_counts[prov]["failed"] += 1
        elif st == "skipped":
            provider_counts[prov]["skipped"] += 1

    # Overall summary (sum across all providers).
    statuses = [r["status"] for r in combined_results.values()]
    summary = {
        "total": len(statuses),
        "passed": statuses.count("passed"),
        "failed": statuses.count("failed") + statuses.count("error"),
        "skipped": statuses.count("skipped"),
    }

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "provider_summaries": provider_counts,
        "results": combined_results,
    }


def load_history(history_path: Path) -> list[dict[str, Any]]:
    """Load previous run history from a cache file."""
    if history_path.exists():
        with open(history_path, encoding="utf-8") as f:
            data = json.load(f)
        runs = data.get("runs", [])
        print(f"  Loaded {len(runs)} previous run(s) from history")
        return runs
    print("  No previous history found")
    return []


def save_history(history_path: Path, runs: list[dict[str, Any]]) -> None:
    """Save run history, keeping only the last ``MAX_HISTORY`` entries."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = runs[-MAX_HISTORY:]
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump({"runs": trimmed}, f, indent=2)
    print(f"  Saved {len(trimmed)} run(s) to history")


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _short_name(nodeid: str) -> str:
    """Extract a short test name from a full nodeid.

    ``packages.openai.tests.openai.test_openai_chat_client::test_integration_options``
    → ``test_integration_options``
    """
    return nodeid.split("::")[-1] if "::" in nodeid else nodeid


def generate_trend_report(runs: list[dict[str, Any]]) -> str:
    """Generate a markdown trend report from run history."""
    lines = [
        "# 🔬 Integration Test Report",
        "",
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
    ]

    # Detect whether this is a dotnet report (provider-qualified keys).
    is_dotnet = False
    for run in runs:
        provider_sums = run.get("provider_summaries", {})
        if any(p.startswith("net") for p in provider_sums):
            is_dotnet = True
            break

    if is_dotnet:
        _generate_dotnet_report(lines, runs)
    else:
        _generate_python_report(lines, runs)

    lines.append("")
    lines.append("**Legend:** ✅ Passed · ❌ Failed · ⏭️ Skipped · ⚠️ Expected Failure (xfail) · N/A Not available")
    lines.append("")

    return "\n".join(lines)


def _generate_python_report(lines: list[str], runs: list[dict[str, Any]]) -> None:
    """Generate the original single-table Python report format."""
    # --- Overall status table ---
    lines.append("## Overall Status (Last 5 Runs)")
    lines.append("")
    lines.append("| Run | Total | ✅ Passed | ❌ Failed | ⏭️ Skipped |")
    lines.append("|-----|-------|-----------|-----------|------------|")

    for run in reversed(runs):
        s = run.get("summary", {})
        total = s.get("total", 0)
        label = _format_run_label(run["timestamp"])
        lines.append(
            f"| {label} "
            f"| {total} "
            f"| {s.get('passed', 0)}/{total} "
            f"| {s.get('failed', 0)}/{total} "
            f"| {s.get('skipped', 0)}/{total} |"
        )

    for _ in range(MAX_HISTORY - len(runs)):
        lines.append("| N/A | N/A | N/A | N/A | N/A |")

    lines.append("")

    # --- Single per-test results table ---
    _generate_per_test_table(lines, runs, "## Per-Test Results")


def _generate_dotnet_report(lines: list[str], runs: list[dict[str, Any]]) -> None:
    """Generate per-framework tables for dotnet (net10.0, net472, etc.)."""
    # Collect all providers seen across all runs, sorted for stable ordering
    all_providers: set[str] = set()
    for run in runs:
        all_providers.update(run.get("provider_summaries", {}).keys())
    providers = sorted(all_providers)

    for provider in providers:
        lines.append(f"## {provider}")
        lines.append("")

        # --- Per-provider summary table ---
        lines.append("| Run | Total | ✅ Passed | ❌ Failed | ⏭️ Skipped |")
        lines.append("|-----|-------|-----------|-----------|------------|")

        for run in reversed(runs):
            ps = run.get("provider_summaries", {}).get(provider, {})
            total = ps.get("total", 0)
            label = _format_run_label(run["timestamp"])
            if total == 0:
                lines.append(f"| {label} | N/A | N/A | N/A | N/A |")
            else:
                lines.append(
                    f"| {label} "
                    f"| {total} "
                    f"| {ps.get('passed', 0)}/{total} "
                    f"| {ps.get('failed', 0)}/{total} "
                    f"| {ps.get('skipped', 0)}/{total} |"
                )

        for _ in range(MAX_HISTORY - len(runs)):
            lines.append("| N/A | N/A | N/A | N/A | N/A |")

        lines.append("")

        # --- Per-test table filtered to this provider ---
        _generate_per_test_table(
            lines, runs,
            heading=None,
            provider_filter=provider,
        )


def _generate_per_test_table(
    lines: list[str],
    runs: list[dict[str, Any]],
    heading: str | None = None,
    provider_filter: str | None = None,
) -> None:
    """Emit a per-test trend table, optionally filtered to a single provider."""
    if heading:
        lines.append(heading)
        lines.append("")

    # Collect all test nodeids (and metadata) across all runs
    all_tests: dict[str, str] = {}  # nodeid → provider
    all_modules: dict[str, str] = {}  # nodeid → module
    for run in runs:
        for nodeid, info in run.get("results", {}).items():
            if not isinstance(info, dict):
                continue
            prov = info.get("provider", "Unknown")
            if provider_filter and prov != provider_filter:
                continue
            module = info.get("module", "")
            all_tests[nodeid] = prov
            all_modules[nodeid] = module

    if not all_tests:
        lines.append("*No test results available.*")
        lines.append("")
        return

    # Build header
    if provider_filter:
        header = "| Test | File |"
        separator = "|------|------|"
    else:
        header = "| Test | File | Provider |"
        separator = "|------|------|----------|"
    for run in reversed(runs):
        label = _format_run_label(run["timestamp"])
        header += f" {label} |"
        separator += "------------|"
    for _ in range(MAX_HISTORY - len(runs)):
        header += " N/A |"
        separator += "-----|"

    lines.append(header)
    lines.append(separator)

    # Sort by module then test name
    for nodeid in sorted(all_tests, key=lambda n: (all_modules.get(n, ""), n)):
        module = all_modules.get(nodeid, "")
        short = _short_name(nodeid)
        if provider_filter:
            row = f"| `{short}` | `{module}` |"
        else:
            provider = all_tests[nodeid]
            row = f"| `{short}` | `{module}` | {provider} |"

        for run in reversed(runs):
            result = run.get("results", {}).get(nodeid)
            if result is None:
                emoji = "N/A"
            else:
                status = result.get("status", "N/A") if isinstance(result, dict) else result
                emoji = STATUS_EMOJI.get(status, "❓")
            row += f" {emoji} |"

        for _ in range(MAX_HISTORY - len(runs)):
            row += " N/A |"

        lines.append(row)

    lines.append("")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: python aggregate.py <reports-dir> <history-file> <output-file>")
        return 1

    reports_dir = Path(sys.argv[1])
    history_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3])

    print("Aggregating test results from JUnit XML...")

    # Load current run's per-provider XML reports
    print(f"\nLoading reports from {reports_dir}:")
    current_run = load_current_run(reports_dir)
    s = current_run.get("summary", {})
    total = s.get("total", 0)
    print(
        f"  Current run: {s.get('passed', 0)} passed, "
        f"{s.get('failed', 0)} failed, "
        f"{s.get('skipped', 0)} skipped "
        f"(total: {total})"
    )

    # Load history and append current run (skip empty runs to avoid polluting trend)
    print(f"\nLoading history from {history_path}:")
    runs = load_history(history_path)
    if total > 0:
        runs.append(current_run)
        runs = runs[-MAX_HISTORY:]
    else:
        print("  Skipping history append (no test results in current run)")

    # Save updated history
    print(f"\nSaving history to {history_path}:")
    save_history(history_path, runs)

    # Generate trend report
    print("\nGenerating trend report...")
    report = generate_trend_report(runs)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"Trend report written to {output_path}")

    # Print the report to stdout for CI visibility
    print("\n" + "=" * 80)
    print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
