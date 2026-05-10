# Copyright (c) Microsoft. All rights reserved.

"""CLI entry point for the integration test report tool.

Usage:
    uv run python -m scripts.integration_test_report <reports-dir> <history-file> <output-file>

Example (from python/ directory):
    uv run python -m scripts.integration_test_report \\
        ../test-results/ \\
        integration-report-history.json \\
        integration-test-report.md
"""

import sys

from scripts.integration_test_report.aggregate import main

if __name__ == "__main__":
    sys.exit(main())
