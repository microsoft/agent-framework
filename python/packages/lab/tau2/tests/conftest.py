# Copyright (c) Microsoft. All rights reserved.

"""Pytest configuration and fixtures for tau2 tests."""

import os
import shutil
import subprocess
from pathlib import Path
import pytest


def setup_tau2_data():
    """Set up tau2 data directory by cloning repository if needed."""

    # Get project directory (parent of tests directory)
    tests_dir = Path(__file__).parent
    project_dir = tests_dir.parent
    data_dir = project_dir / "data"

    print("Setting up tau2 data directory...")

    # Check if data directory already exists
    if data_dir.exists():
        print(f"Data directory already exists at {data_dir}")
    else:
        print("Data directory not found. Cloning tau2-bench repository...")

        # Change to project directory
        original_cwd = os.getcwd()
        os.chdir(project_dir)

        try:
            # Clone the repository
            print("Cloning https://github.com/sierra-research/tau2-bench.git...")
            subprocess.run(
                ["git", "clone", "https://github.com/sierra-research/tau2-bench.git"],
                check=True,
                capture_output=True,
                text=True,
            )

            # Move data directory
            print("Moving data directory...")
            tau2_bench_dir = project_dir / "tau2-bench"
            tau2_data_dir = tau2_bench_dir / "data"

            if tau2_data_dir.exists():
                shutil.move(str(tau2_data_dir), str(data_dir))
            else:
                raise FileNotFoundError(f"Data directory not found in cloned repository: {tau2_data_dir}")

            # Clean up cloned repository
            print("Cleaning up cloned repository...")
            shutil.rmtree(tau2_bench_dir)

            print("Data directory setup completed successfully!")

        except subprocess.CalledProcessError as e:
            print(f"ERROR: Failed to clone repository: {e}")
            raise
        except Exception as e:
            print(f"ERROR: Failed to set up data directory: {e}")
            raise
        finally:
            os.chdir(original_cwd)

    # Set TAU2_DATA_DIR environment variable
    os.environ["TAU2_DATA_DIR"] = str(data_dir)
    print(f"TAU2_DATA_DIR set to: {data_dir}")

    return str(data_dir)


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """
    Session-scoped fixture that runs automatically before all tests.
    Sets up the tau2 data directory and environment variables.
    """
    data_dir = setup_tau2_data()

    # Verify data directory exists
    if not Path(data_dir).exists():
        pytest.skip("TAU2 data directory could not be set up")

    yield data_dir

    # Cleanup could go here if needed, but we'll keep the data
    # for subsequent test runs to avoid re-downloading
