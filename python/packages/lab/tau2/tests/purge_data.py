# Copyright (c) Microsoft. All rights reserved.

import shutil
from pathlib import Path


def purge_tau2_data():
    """Purge tau2 data directory if it exists."""

    data_dir = Path.cwd() / "data"

    if data_dir.exists():
        shutil.rmtree(data_dir)
        print(f"Data directory at {data_dir} has been purged.")
    else:
        print("Data directory not found. Skipping purge.")


if __name__ == "__main__":
    purge_tau2_data()
