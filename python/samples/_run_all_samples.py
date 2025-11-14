# Copyright (c) Microsoft. All rights reserved.

"""
Script to run all Python samples in the samples directory concurrently.
This script will run all samples and report results at the end.

Note: This script is AI generated. This is for internal validation purposes only.

Samples that require human interaction are known to fail.

Usage:
    python run_all_samples.py                          # Run all samples using uv run (concurrent)
    python run_all_samples.py --direct                 # Run all samples directly (concurrent,
                                                       # assumes environment is set up)
    python run_all_samples.py --subdir <directory>     # Run samples only in specific subdirectory
    python run_all_samples.py --subdir getting_started/workflows  # Example: run only workflow samples
"""

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def find_python_samples(samples_dir: Path, subdir: str | None = None) -> list[Path]:
    """Find all Python sample files in the samples directory or a subdirectory."""
    python_files: list[Path] = []

    # Determine the search directory
    if subdir:
        search_dir = samples_dir / subdir
        if not search_dir.exists():
            print(f"Warning: Subdirectory '{subdir}' does not exist in {samples_dir}")
            return []
        print(f"Searching in subdirectory: {search_dir}")
    else:
        search_dir = samples_dir
        print(f"Searching in all samples: {search_dir}")

    # Walk through all subdirectories and find .py files
    for root, dirs, files in os.walk(search_dir):
        # Skip __pycache__ directories
        dirs[:] = [d for d in dirs if d != "__pycache__"]

        for file in files:
            if file.endswith(".py") and not file.startswith("_") and file != "_run_all_samples.py":
                python_files.append(Path(root) / file)

    # Sort files for consistent execution order
    return sorted(python_files)


def run_sample(
    sample_path: Path,
    use_uv: bool = True,
    python_root: Path | None = None,
) -> tuple[bool, str, str, str]:
    """
    Run a single sample file using subprocess and return (success, output, error_info, error_type).

    Args:
        sample_path: Path to the sample file
        use_uv: Whether to use uv run
        python_root: Root directory for uv run

    Returns:
        Tuple of (success, output, error_info, error_type)
        error_type can be: "timeout", "input_hang", "execution_error", "exception"
    """
    if use_uv and python_root:
        cmd = ["uv", "run", "python", str(sample_path)]
        cwd = python_root
    else:
        cmd = [sys.executable, sample_path.name]
        cwd = sample_path.parent

    # Set environment variables to handle Unicode properly
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"  # Force Python to use UTF-8 for I/O
    env["PYTHONUTF8"] = "1"  # Enable UTF-8 mode in Python 3.7+

    try:
        # Use Popen for better timeout handling with stdin for samples that may wait for input
        # Popen gives us more control over process lifecycle compared to subprocess.run()
        process = subprocess.Popen(
            cmd,  # Command to execute as a list [program, arg1, arg2, ...]
            cwd=cwd,  # Working directory for the subprocess
            stdout=subprocess.PIPE,  # Capture stdout so we can read the output
            stderr=subprocess.PIPE,  # Capture stderr so we can read error messages
            stdin=subprocess.PIPE,  # Create a pipe for stdin so we can send input
            text=True,  # Handle input/output as text strings (not bytes)
            encoding="utf-8",  # Use UTF-8 encoding to handle Unicode characters like emojis
            errors="replace",  # Replace problematic characters instead of failing
            env=env,  # Pass environment variables for proper Unicode handling
        )

        try:
            # communicate() sends input to stdin and waits for process to complete
            # input="" sends an empty string to stdin, which causes input() calls to
            # immediately receive EOFError (End Of File) since there's no data to read.
            # This prevents the process from hanging indefinitely waiting for user input.
            stdout, stderr = process.communicate(input="", timeout=60)
        except subprocess.TimeoutExpired:
            # If the process doesn't complete within the timeout period, we need to
            # forcibly terminate it. This is especially important for processes that
            # ignore EOFError and continue to hang on input() calls.

            # First attempt: Send SIGKILL (immediate termination) on Unix or TerminateProcess on Windows
            process.kill()
            try:
                # Give the process a few seconds to clean up after being killed
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                # If the process is still alive after kill(), use terminate() as a last resort
                # terminate() sends SIGTERM (graceful termination request) which may work
                # when kill() doesn't on some systems
                process.terminate()
                stdout, stderr = "", "Process forcibly terminated"
            return False, "", f"TIMEOUT: {sample_path.name} (exceeded 60 seconds)", "timeout"

        if process.returncode == 0:
            output = stdout.strip() if stdout.strip() else "No output"
            return True, output, "", "success"

        error_info = f"Exit code: {process.returncode}"
        if stderr.strip():
            error_info += f"\nSTDERR: {stderr}"

        # Check if this looks like an input/interaction related error
        error_type = "execution_error"
        stderr_safe = stderr.encode("utf-8", errors="replace").decode("utf-8") if stderr else ""
        if "EOFError" in stderr_safe or "input" in stderr_safe.lower() or "stdin" in stderr_safe.lower():
            error_type = "input_hang"
        elif "UnicodeEncodeError" in stderr_safe and ("charmap" in stderr_safe or "codec can't encode" in stderr_safe):
            error_type = "input_hang"  # Unicode errors often indicate interactive samples with emojis

        return False, stdout.strip() if stdout.strip() else "", error_info, error_type
    except Exception as e:
        return False, "", f"ERROR: {sample_path.name} - Exception: {str(e)}", "exception"


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run Python samples concurrently",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_all_samples.py                                    # Run all samples
  python run_all_samples.py --direct                           # Run all samples directly
  python run_all_samples.py --subdir getting_started           # Run only getting_started samples
  python run_all_samples.py --subdir getting_started/workflows # Run only workflow samples
  python run_all_samples.py --subdir semantic-kernel-migration # Run only SK migration samples
        """,
    )

    parser.add_argument(
        "--direct", action="store_true", help="Run samples directly with python instead of using uv run"
    )

    parser.add_argument(
        "--subdir", type=str, help="Run samples only in the specified subdirectory (relative to samples/)"
    )

    parser.add_argument(
        "--max-workers", type=int, default=16, help="Maximum number of concurrent workers (default: 16)"
    )

    return parser.parse_args()


def main() -> None:
    """Main function to run all samples concurrently."""
    args = parse_arguments()

    # Get the samples directory (assuming this script is in the samples directory)
    samples_dir = Path(__file__).parent
    python_root = samples_dir.parent  # Go up to the python/ directory

    print("Python samples runner")
    print(f"Samples directory: {samples_dir}")

    if args.direct:
        print("Running samples directly (assuming environment is set up)")
    else:
        print(f"Using uv run from: {python_root}")

    if args.subdir:
        print(f"Filtering to subdirectory: {args.subdir}")

    print("🚀 Running samples concurrently...")

    # Find all Python sample files
    sample_files = find_python_samples(samples_dir, args.subdir)

    if not sample_files:
        print("No Python sample files found!")
        return

    print(f"Found {len(sample_files)} Python sample files")

    # Run samples concurrently
    results: list[tuple[Path, bool, str, str, str]] = []

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        # Submit all tasks
        future_to_sample = {
            executor.submit(run_sample, sample_path, not args.direct, python_root): sample_path
            for sample_path in sample_files
        }

        # Collect results as they complete
        for future in as_completed(future_to_sample):
            sample_path = future_to_sample[future]
            try:
                success, output, error_info, error_type = future.result()
                results.append((sample_path, success, output, error_info, error_type))

                # Print progress - show relative path from samples directory
                relative_path = sample_path.relative_to(samples_dir)
                if success:
                    print(f"✅ {relative_path}")
                else:
                    # Show error type in progress display
                    error_display = f"{error_type.upper()}" if error_type != "execution_error" else "ERROR"
                    print(f"❌ {relative_path} - {error_display}")

            except Exception as e:
                error_info = f"Future exception: {str(e)}"
                results.append((sample_path, False, "", error_info, "exception"))
                relative_path = sample_path.relative_to(samples_dir)
                print(f"❌ {relative_path} - EXCEPTION")

    # Sort results by original file order for consistent reporting
    sample_to_index = {path: i for i, path in enumerate(sample_files)}
    results.sort(key=lambda x: sample_to_index[x[0]])

    successful_runs = sum(1 for _, success, _, _, _ in results if success)
    failed_runs = len(results) - successful_runs

    # Categorize failures by type
    timeout_failures = [r for r in results if not r[1] and r[4] == "timeout"]
    input_hang_failures = [r for r in results if not r[1] and r[4] == "input_hang"]
    execution_errors = [r for r in results if not r[1] and r[4] == "execution_error"]
    exceptions = [r for r in results if not r[1] and r[4] == "exception"]

    # Print detailed results
    print(f"\n{'=' * 80}")
    print("DETAILED RESULTS:")
    print(f"{'=' * 80}")

    for sample_path, success, output, error_info, error_type in results:
        relative_path = sample_path.relative_to(samples_dir)
        if success:
            print(f"✅ {relative_path}")
            if output and output != "No output":
                print(f"   Output preview: {output[:100]}{'...' if len(output) > 100 else ''}")
        else:
            # Display error with type indicator
            if error_type == "timeout":
                print(f"⏱️  {relative_path} - TIMEOUT (likely waiting for input)")
            elif error_type == "input_hang":
                print(f"⌨️  {relative_path} - INPUT ERROR (interactive sample)")
            elif error_type == "exception":
                print(f"💥 {relative_path} - EXCEPTION")
            else:
                print(f"❌ {relative_path} - EXECUTION ERROR")
            print(f"   Error: {error_info}")

    # Print categorized summary
    print(f"\n{'=' * 80}")
    if failed_runs == 0:
        print("🎉 ALL SAMPLES COMPLETED SUCCESSFULLY!")
    else:
        print(f"❌ {failed_runs} SAMPLE(S) FAILED!")

    print(f"Successful runs: {successful_runs}")
    print(f"Failed runs: {failed_runs}")

    if failed_runs > 0:
        print("\nFailure breakdown:")
        if len(timeout_failures) > 0:
            print(f"  ⏱️  Timeouts (likely interactive): {len(timeout_failures)}")
        if len(input_hang_failures) > 0:
            print(f"  ⌨️  Input errors (interactive): {len(input_hang_failures)}")
        if len(execution_errors) > 0:
            print(f"  ❌ Execution errors: {len(execution_errors)}")
        if len(exceptions) > 0:
            print(f"  💥 Exceptions: {len(exceptions)}")

    if args.subdir:
        print(f"Subdirectory filter: {args.subdir}")

    print(f"{'=' * 80}")

    # Exit with error code if any samples failed
    if failed_runs > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
