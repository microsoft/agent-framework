# Copyright (c) Microsoft. All rights reserved.

"""Launch DevUI with folder discovery for the samples in this directory.

This sample demonstrates:
- Loading a shared root `.env` file for the DevUI samples folder
- Starting DevUI in directory discovery mode for this folder
- Using root-level settings as fallbacks for discovered samples
"""

from pathlib import Path

from agent_framework.devui import serve
from dotenv import load_dotenv


def main() -> None:
    """Load the root .env file and launch DevUI with folder discovery."""
    samples_dir = Path(__file__).resolve().parent

    # 1. Load shared defaults for the samples in this folder.
    load_dotenv(samples_dir / ".env")

    # 2. Start DevUI and discover entities from this directory.
    serve(entities_dir=str(samples_dir), auto_open=True)


if __name__ == "__main__":
    main()

# Sample output:
# Starting Agent Framework DevUI on 127.0.0.1:8080
