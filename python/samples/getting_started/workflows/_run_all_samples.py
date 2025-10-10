# Copyright (c) Microsoft. All rights reserved.

"""
Script to run all workflow samples in the getting_started/workflows directory concurrently.
This script will run all samples and report results at the end.

Note: This script is AI generated. This is for internal validation purposes only.

Samples that require human interaction are known to fail.

Usage:
    python _run_all_samples.py              # Run all samples using uv run (concurrent)
    python _run_all_samples.py --direct     # Run all samples directly (concurrent, assumes environment is set up)
"""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def find_python_samples(workflows_dir: Path) -> list[Path]:
    """Find all Python sample files in the workflows directory."""
    python_files: list[Path] = []

    # Walk through all subdirectories and find .py files
    for root, dirs, files in os.walk(workflows_dir):
        # Skip __pycache__ directories
        dirs[:] = [d for d in dirs if d != "__pycache__"]

        for file in files:
            if file.endswith(".py") and not file.startswith("_"):
                python_files.append(Path(root) / file)

    # Sort files for consistent execution order
    return sorted(python_files)


def run_sample(
    sample_path: Path,
    use_uv: bool = True,
    python_root: Path | None = None,
) -> tuple[bool, str, str]:
    """
    Run a single sample file using subprocess and return (success, output, error_info).

    Args:
        sample_path: Path to the sample file
        use_uv: Whether to use uv run
        python_root: Root directory for uv run

    Returns:
        Tuple of (success, output, error_info)
    """
    if use_uv and python_root:
        cmd = ["uv", "run", "python", str(sample_path)]
        cwd = python_root
    else:
        cmd = [sys.executable, sample_path.name]
        cwd = sample_path.parent

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=50,  # 50 second timeout
        )

        if result.returncode == 0:
            output = result.stdout.strip() if result.stdout.strip() else "No output"
            return True, output, ""

        error_info = f"Exit code: {result.returncode}"
        if result.stderr.strip():
            error_info += f"\nSTDERR: {result.stderr}"

        return False, result.stdout.strip() if result.stdout.strip() else "", error_info

    except subprocess.TimeoutExpired:
        return False, "", f"TIMEOUT: {sample_path.name} (exceeded 50 seconds)"
    except Exception as e:
        return False, "", f"ERROR: {sample_path.name} - Exception: {str(e)}"


def main() -> None:
    """Main function to run all workflow samples concurrently."""
    # Check command line arguments
    use_uv = "--direct" not in sys.argv

    # Get the workflows directory (assuming this script is in the workflows directory)
    workflows_dir = Path(__file__).parent
    python_root = workflows_dir.parents[2]  # Go up to the python/ directory

    print(f"Scanning for Python samples in: {workflows_dir}")
    if use_uv:
        print(f"Using uv run from: {python_root}")
    else:
        print("Running samples directly (assuming environment is set up)")

    print("🚀 Running samples concurrently...")

    # Find all Python sample files
    sample_files = find_python_samples(workflows_dir)

    if not sample_files:
        print("No Python sample files found!")
        return

    print(f"Found {len(sample_files)} Python sample files")

    # Run samples concurrently
    results: list[tuple[Path, bool, str, str]] = []
    max_workers = 16

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_sample = {
            executor.submit(run_sample, sample_path, use_uv, python_root): sample_path for sample_path in sample_files
        }

        # Collect results as they complete
        for future in as_completed(future_to_sample):
            sample_path = future_to_sample[future]
            try:
                success, output, error_info = future.result()
                results.append((sample_path, success, output, error_info))

                # Print progress
                if success:
                    print(f"✅ {sample_path.name}")
                else:
                    print(f"❌ {sample_path.name} - {error_info.split(':', 1)[0]}")

            except Exception as e:
                error_info = f"Future exception: {str(e)}"
                results.append((sample_path, False, "", error_info))
                print(f"❌ {sample_path.name} - {error_info}")

    # Sort results by original file order for consistent reporting
    sample_to_index = {path: i for i, path in enumerate(sample_files)}
    results.sort(key=lambda x: sample_to_index[x[0]])

    successful_runs = sum(1 for _, success, _, _ in results if success)
    failed_runs = len(results) - successful_runs

    # Print detailed results
    print(f"\n{'=' * 60}")
    print("DETAILED RESULTS:")
    print(f"{'=' * 60}")

    for sample_path, success, output, error_info in results:
        if success:
            print(f"✅ {sample_path.name}")
            if output and output != "No output":
                print(f"   Output preview: {output[:100]}{'...' if len(output) > 100 else ''}")
        else:
            print(f"❌ {sample_path.name}")
            print(f"   Error: {error_info}")

    # Print summary
    print(f"\n{'=' * 60}")
    if failed_runs == 0:
        print("🎉 ALL SAMPLES COMPLETED SUCCESSFULLY!")
    else:
        print(f"❌ {failed_runs} SAMPLE(S) FAILED!")
    print(f"Successful runs: {successful_runs}")
    print(f"Failed runs: {failed_runs}")
    print(f"{'=' * 60}")

    # Exit with error code if any samples failed
    if failed_runs > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
