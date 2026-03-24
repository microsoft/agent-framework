# Copyright (c) Microsoft. All rights reserved.

"""Aggregate validation reports across runs and produce a trend report.

Reads JSON reports from individual validation jobs, combines them with
cached history from previous runs, and produces a markdown trend report
showing per-sample status over the last 5 runs.

Usage:
    python aggregate.py <reports-dir> <history-file> <output-file>
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_HISTORY = 5

STATUS_EMOJI = {
    "success": "✅",
    "failure": "❌",
    "missing_setup": "⚠️",
}


def _format_run_label(timestamp: str) -> str:
    """Format a run timestamp as a compact column label (e.g. '03-24 18:05')."""
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.strftime("%m-%d %H:%M")
    except (ValueError, TypeError):
        return timestamp[:16]


def load_current_run(reports_dir: Path) -> dict[str, Any]:
    """Load all JSON report files from the current run and merge them."""
    combined_results: dict[str, str] = {}
    total = success = failure = missing = 0

    json_files = sorted(reports_dir.glob("*.json"))
    if not json_files:
        print(f"Warning: No JSON report files found in {reports_dir}")
        return {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_samples": 0,
                "success_count": 0,
                "failure_count": 0,
                "missing_setup_count": 0,
            },
            "results": {},
        }

    for json_file in json_files:
        print(f"  Loading report: {json_file.name}")
        with open(json_file, encoding="utf-8") as f:
            report = json.load(f)
        for result in report["results"]:
            combined_results[result["path"]] = result["status"]
        summary = report["summary"]
        total += summary["total_samples"]
        success += summary["success_count"]
        failure += summary["failure_count"]
        missing += summary["missing_setup_count"]

    return {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_samples": total,
            "success_count": success,
            "failure_count": failure,
            "missing_setup_count": missing,
        },
        "results": combined_results,
    }


def load_history(history_path: Path) -> list[dict[str, Any]]:
    """Load previous run history from cache."""
    if history_path.exists():
        with open(history_path, encoding="utf-8") as f:
            data = json.load(f)
        runs = data.get("runs", [])
        print(f"  Loaded {len(runs)} previous run(s) from history")
        return runs
    print("  No previous history found")
    return []


def save_history(history_path: Path, runs: list[dict[str, Any]]) -> None:
    """Save run history, keeping only the last MAX_HISTORY entries."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = runs[-MAX_HISTORY:]
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump({"runs": trimmed}, f, indent=2)
    print(f"  Saved {len(trimmed)} run(s) to history")


def generate_trend_report(runs: list[dict[str, Any]]) -> str:
    """Generate a markdown trend report from run history."""
    lines = [
        "# Sample Validation Trend Report",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
    ]

    # --- Overall status table (most recent first) ---
    lines.append("## Overall Status (Last 5 Runs)")
    lines.append("")
    lines.append("| Run | Success | Failure | Missing Setup | Total |")
    lines.append("|-----|---------|---------|---------------|-------|")

    for run in reversed(runs):
        s = run["summary"]
        label = _format_run_label(run["timestamp"])
        lines.append(
            f"| {label} | {s['success_count']}/{s['total_samples']} "
            f"| {s['failure_count']}/{s['total_samples']} "
            f"| {s['missing_setup_count']}/{s['total_samples']} "
            f"| {s['total_samples']} |"
        )

    # Pad with N/A rows if fewer than 5 runs
    for _ in range(MAX_HISTORY - len(runs)):
        lines.append("| N/A | N/A | N/A | N/A | N/A |")

    lines.append("")

    # --- Per-sample results table ---
    lines.append("## Per-Sample Results")
    lines.append("")

    # Collect all sample paths across all runs
    all_paths: set[str] = set()
    for run in runs:
        all_paths.update(run["results"].keys())

    if not all_paths:
        lines.append("*No sample results available.*")
        return "\n".join(lines)

    # Build header (most recent run first)
    header = "| Sample |"
    separator = "|--------|"
    for run in reversed(runs):
        label = _format_run_label(run["timestamp"])
        header += f" {label} |"
        separator += "------------|"
    for _ in range(MAX_HISTORY - len(runs)):
        header += " N/A |"
        separator += "-----|"

    lines.append(header)
    lines.append(separator)

    for path in sorted(all_paths):
        row = f"| `{path}` |"
        for run in reversed(runs):
            status = run["results"].get(path, "N/A")
            emoji = STATUS_EMOJI.get(status, "N/A")
            row += f" {emoji} |"
        for _ in range(MAX_HISTORY - len(runs)):
            row += " N/A |"
        lines.append(row)

    lines.append("")
    lines.append("**Legend:** ✅ Success · ❌ Failure · ⚠️ Missing Setup · N/A Not available")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: python aggregate.py <reports-dir> <history-file> <output-file>")
        return 1

    reports_dir = Path(sys.argv[1])
    history_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3])

    print("Aggregating validation results...")

    # Load current run's reports
    print(f"\nLoading reports from {reports_dir}:")
    current_run = load_current_run(reports_dir)
    s = current_run["summary"]
    print(
        f"  Current run: {s['success_count']} success, "
        f"{s['failure_count']} failure, "
        f"{s['missing_setup_count']} missing setup "
        f"(total: {s['total_samples']})"
    )

    # Load history and append current run
    print(f"\nLoading history from {history_path}:")
    runs = load_history(history_path)
    runs.append(current_run)
    runs = runs[-MAX_HISTORY:]

    # Save updated history
    print(f"\nSaving history to {history_path}:")
    save_history(history_path, runs)

    # Generate trend report
    print("\nGenerating trend report...")
    report = generate_trend_report(runs)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"Trend report written to {output_path}")

    # Also print the report to stdout
    print("\n" + "=" * 80)
    print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
