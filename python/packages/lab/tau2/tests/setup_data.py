# Copyright (c) Microsoft. All rights reserved.

import shutil
import subprocess
from pathlib import Path


def setup_tau2_data():
    """Set up tau2 data directory by cloning repository if needed."""

    # Get project directory (parent of tests directory)
    data_dir = Path.cwd() / "data"
    print(data_dir)

    print("Setting up tau2 data directory...")

    # Check if data directory already exists
    if data_dir.exists():
        print(f"Data directory already exists at {data_dir}")
    else:
        print("Data directory not found. Cloning tau2-bench repository...")

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
            tau2_bench_dir = Path.cwd() / "tau2-bench"
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

    print(f"TAU2_DATA_DIR should be set to: {data_dir}")

    return str(data_dir)


if __name__ == "__main__":
    setup_tau2_data()
