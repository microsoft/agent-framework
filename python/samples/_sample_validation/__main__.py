# Copyright (c) Microsoft. All rights reserved.

"""
Sample Validation Script

Validates all Python samples in the samples directory using a workflow that:
1. Discovers all sample files
2. Builds a nested concurrent workflow with one GitHub agent per sample
3. Runs the nested workflow
4. Generates a validation report

Usage:
    uv run python -m _sample_validation
    uv run python -m _sample_validation --subdir 03-workflows
    uv run python -m _sample_validation --output-dir ./reports
"""

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Add the samples directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from _sample_validation.models import Report
from _sample_validation.report import save_report
from _sample_validation.workflow import ValidationConfig, create_validation_workflow


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate Python samples using a dynamic nested concurrent workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python -m _sample_validation                        # Validate all samples
  uv run python -m _sample_validation --subdir 03-workflows  # Validate only workflows
  uv run python -m _sample_validation --output-dir ./reports # Save reports to custom dir
        """,
    )

    parser.add_argument(
        "--subdir",
        type=str,
        help="Validate samples only in the specified subdirectory (relative to samples/)",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="./_sample_validation/reports",
        help="Directory to save validation reports (default: ./_sample_validation/reports)",
    )

    parser.add_argument(
        "--save-report",
        action="store_true",
        help="Save the validation report to files",
    )

    parser.add_argument(
        "--max-parallel-workers",
        type=int,
        default=10,
        help="Maximum number of samples to run in parallel per batch (default: 10)",
    )

    parser.add_argument(
        "--report-name",
        type=str,
        help="Custom name for the report files (without extension). If not provided, uses timestamp.",
    )

    return parser.parse_args()


async def main() -> int:
    """Main entry point."""
    args = parse_arguments()

    # Determine paths
    samples_dir = Path(__file__).parent.parent
    python_root = samples_dir.parent

    print("=" * 80)
    print("SAMPLE VALIDATION WORKFLOW")
    print("=" * 80)
    print(f"Samples directory: {samples_dir}")
    print(f"Python root: {python_root}")

    if os.environ.get("GITHUB_COPILOT_MODEL"):
        print(f"Using GitHub Copilot model override: {os.environ['GITHUB_COPILOT_MODEL']}")

    # Create validation config
    config = ValidationConfig(
        samples_dir=samples_dir,
        python_root=python_root,
        subdir=args.subdir,
        max_parallel_workers=max(1, args.max_parallel_workers),
    )

    # Create and run the workflow
    workflow = create_validation_workflow(config)

    print("\nStarting validation workflow...")
    print("-" * 80)

    # Run the workflow
    run_start = time.perf_counter()
    try:
        events = await workflow.run("start")
    finally:
        run_duration = time.perf_counter() - run_start
        print(f"\nWorkflow run completed in {run_duration:.2f}s")

    outputs = events.get_outputs()

    if not outputs:
        print("\n[ERROR] Workflow did not produce any output")
        return 1

    report: Report = outputs[0]

    # Save report if requested
    if args.save_report:
        output_dir = samples_dir / args.output_dir
        md_path, json_path = save_report(report, output_dir, name=args.report_name)
        print("\nReports saved:")
        print(f"   Markdown: {md_path}")
        print(f"   JSON: {json_path}")

    # Return appropriate exit code
    failed = report.failure_count + report.timeout_count + report.error_count
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
