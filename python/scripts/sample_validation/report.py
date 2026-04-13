# Copyright (c) Microsoft. All rights reserved.

"""Report generation for sample validation results."""

import json
from datetime import datetime
from pathlib import Path

from agent_framework import Executor, WorkflowContext, handler
from typing_extensions import Never

from sample_validation.models import ExecutionResult, Report, RunResult, RunStatus


def generate_report(results: list[RunResult]) -> Report:
    """
    Generate a validation report from run results.

    Args:
        results: List of RunResult objects from sample execution

    Returns:
        Report object with aggregated statistics
    """
    # Sort results: failures, missing setup first, then successes
    status_priority = {
        RunStatus.FAILURE: 0,
        RunStatus.MISSING_SETUP: 1,
        RunStatus.SUCCESS: 2,
    }
    sorted_results = sorted(results, key=lambda r: status_priority[r.status])

    return Report(
        timestamp=datetime.now(),
        total_samples=len(results),
        success_count=sum(1 for r in results if r.status == RunStatus.SUCCESS),
        failure_count=sum(1 for r in results if r.status == RunStatus.FAILURE),
        missing_setup_count=sum(1 for r in results if r.status == RunStatus.MISSING_SETUP),
        results=sorted_results,
    )


def save_report(
    report: Report, output_dir: Path, name: str | None = None
) -> tuple[Path, Path]:
    """
    Save the report to markdown and JSON files.

    Args:
        report: The report to save
        output_dir: Directory to save the report files
        name: Optional custom name for the report files (without extension)

    Returns:
        Tuple of (markdown_path, json_path)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if name:
        base_name = name
    else:
        timestamp_str = report.timestamp.strftime("%Y%m%d_%H%M%S")
        base_name = f"validation_report_{timestamp_str}"

    # Save markdown
    md_path = output_dir / f"{base_name}.md"
    md_path.write_text(report.to_markdown(), encoding="utf-8")

    # Save JSON
    json_path = output_dir / f"{base_name}.json"
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2),
        encoding="utf-8",
    )

    return md_path, json_path


def print_summary(report: Report) -> None:
    """Print a summary of the validation report to console."""
    print("\n" + "=" * 80)
    print("SAMPLE VALIDATION SUMMARY")
    print("=" * 80)

    if (
        report.failure_count == 0
        and report.missing_setup_count == 0
    ):
        print("[PASS] ALL SAMPLES PASSED!")
    else:
        print("[FAIL] SOME SAMPLES FAILED")

    print(f"\nTotal samples: {report.total_samples}")
    print()
    print("Results:")
    print(f"  [PASS] Success: {report.success_count}")
    print(f"  [FAIL] Failure: {report.failure_count}")
    print(f"  [MISSING_SETUP] Missing Setup: {report.missing_setup_count}")
    print("=" * 80)

    # Print JSON output for GitHub Actions visibility
    print("\nJSON Report:")
    print(json.dumps(report.to_dict(), indent=2))


class GenerateReportExecutor(Executor):
    """Executor that generates the final validation report."""

    def __init__(self) -> None:
        super().__init__(id="generate_report")

    @handler
    async def generate(
        self, execution: ExecutionResult, ctx: WorkflowContext[Never, Report]
    ) -> None:
        """Generate the validation report from fan-in results."""
        print("\nGenerating report...")

        report = generate_report(execution.results)
        print_summary(report)

        await ctx.yield_output(report)
