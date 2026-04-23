# Copyright (c) Microsoft. All rights reserved.

"""CLI entry point for the flaky test report tool.

Usage:
    uv run python -m scripts.flaky_report <reports-dir> <history-file> <output-file>

Example (from python/ directory):
    uv run python -m scripts.flaky_report \\
        ../flaky-reports/ \\
        flaky-report-history.json \\
        flaky-test-report.md
"""

import sys

from scripts.flaky_report.aggregate import main

if __name__ == "__main__":
    sys.exit(main())
