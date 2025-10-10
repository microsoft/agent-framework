# Copyright (c) Microsoft. All rights reserved.

"""
Script to run all workflow samples in the getting_started/workflows directory.
This script will fail fast if any sample fails to execute except when run with --concurrent.

Note: This script is AI generated. This is for internal validation purposes only.

Samples that require human interaction are known to fail.

Usage:
    python _run_all_samples.py                 # Run all samples using uv run (sequential)
    python _run_all_samples.py --concurrent    # Run all samples using uv run (concurrent)
    python _run_all_samples.py --direct        # Run all samples directly (sequential, assumes environment is set up)
    python _run_all_samples.py --direct --concurrent  # Run all samples directly (concurrent)
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
            if file.endswith(".py") and not file.startswith("_") and file != "run_all_samples.py":
                python_files.append(Path(root) / file)

    # Sort files for consistent execution order
    return sorted(python_files)


def run_sample(
    sample_path: Path,
    use_uv: bool = True,
    python_root: Path | None = None,
    quiet: bool = False,
) -> tuple[bool, str, str]:
    """
    Run a single sample file using subprocess and return (success, output, error_info).

    Args:
        sample_path: Path to the sample file
        use_uv: Whether to use uv run
        python_root: Root directory for uv run
        quiet: Whether to suppress output during execution

    Returns:
        Tuple of (success, output, error_info)
    """
    if not quiet:
        print(f"\n{'=' * 60}")
        print(f"Running: {sample_path.relative_to(sample_path.parents[3])}")
        print(f"{'=' * 60}")

    try:
        # Change to the sample's directory to handle relative imports/paths
        sample_dir = sample_path.parent

        if use_uv and python_root:
            # Use uv run from the python root directory
            cmd = ["uv", "run", "python", str(sample_path)]
            cwd = python_root
        else:
            # Run directly with python
            cmd = [sys.executable, sample_path.name]
            cwd = sample_dir

        # Run the sample
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=50,  # 50 second timeout
        )

        if result.returncode == 0:
            success_msg = f"✅ SUCCESS: {sample_path.name}"
            output = result.stdout.strip() if result.stdout.strip() else "No output"
            if not quiet:
                print(success_msg)
                if result.stdout.strip():
                    print("Output:")
                    print(result.stdout)
            return True, output, ""

        error_info = f"Exit code: {result.returncode}"
        if result.stderr.strip():
            error_info += f"\nSTDERR: {result.stderr}"

        if not quiet:
            print(f"❌ FAILED: {sample_path.name}")
            print(error_info)
            if result.stdout.strip():
                print("STDOUT:")
                print(result.stdout)

        return False, result.stdout.strip() if result.stdout.strip() else "", error_info

    except subprocess.TimeoutExpired:
        error_info = f"TIMEOUT: {sample_path.name} (exceeded 50 seconds)"
        if not quiet:
            print(f"❌ {error_info}")
        return False, "", error_info
    except Exception as e:
        error_info = f"ERROR: {sample_path.name} - Exception: {str(e)}"
        if not quiet:
            print(f"❌ {error_info}")
        return False, "", error_info


def run_samples_concurrently(
    sample_files: list[Path],
    use_uv: bool = True,
    python_root: Path | None = None,
    max_workers: int = 4,
) -> tuple[int, int, list[tuple[Path, bool, str, str]]]:
    """
    Run multiple samples concurrently and return results.

    Args:
        sample_files: List of sample file paths
        use_uv: Whether to use uv run
        python_root: Root directory for uv run
        max_workers: Maximum number of concurrent workers

    Returns:
        Tuple of (successful_runs, failed_runs, results_list)
        results_list contains (sample_path, success, output, error_info) for each sample
    """
    print(f"\n🚀 Running {len(sample_files)} samples concurrently with {max_workers} workers...")

    results: list[tuple[Path, bool, str, str]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_sample = {
            executor.submit(run_sample, sample_path, use_uv, python_root, quiet=True): sample_path
            for sample_path in sample_files
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

    return successful_runs, failed_runs, results


def main() -> None:
    """Main function to run all workflow samples."""
    # Check command line arguments
    use_uv = "--direct" not in sys.argv
    use_concurrent = "--concurrent" in sys.argv

    # Get the workflows directory (assuming this script is in the workflows directory)
    workflows_dir = Path(__file__).parent
    python_root = workflows_dir.parents[2]  # Go up to the python/ directory

    print(f"Scanning for Python samples in: {workflows_dir}")
    if use_uv:
        print(f"Using uv run from: {python_root}")
    else:
        print("Running samples directly (assuming environment is set up)")

    if use_concurrent:
        print("🚀 Concurrent execution enabled")
    else:
        print("🔄 Sequential execution (fail-fast)")

    # Find all Python sample files
    sample_files = find_python_samples(workflows_dir)

    if not sample_files:
        print("No Python sample files found!")
        return

    print(f"Found {len(sample_files)} Python sample files:")
    for file in sample_files:
        print(f"  - {file.relative_to(workflows_dir)}")

    if use_concurrent:
        # Run samples concurrently
        successful_runs, failed_runs, results = run_samples_concurrently(
            sample_files, use_uv=use_uv, python_root=python_root, max_workers=16
        )

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
    else:
        # Run samples sequentially with fail-fast behavior
        successful_runs = 0
        failed_runs = 0

        for sample_file in sample_files:
            success, _, error_info = run_sample(sample_file, use_uv=use_uv, python_root=python_root)
            if success:
                successful_runs += 1
            else:
                failed_runs += 1
                # Fail fast - exit immediately on first failure
                print(f"\n{'=' * 60}")
                print(f"❌ EXECUTION STOPPED due to failure in: {sample_file.name}")
                print(f"Successful runs: {successful_runs}")
                print(f"Failed runs: {failed_runs}")
                print(f"{'=' * 60}")
                sys.exit(1)

        # All samples completed successfully
        print(f"\n{'=' * 60}")
        print("🎉 ALL SAMPLES COMPLETED SUCCESSFULLY!")
        print(f"Total samples run: {successful_runs}")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
