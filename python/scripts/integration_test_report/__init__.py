# Copyright (c) Microsoft. All rights reserved.

"""Integration test report aggregation and trend generation.

Parses JUnit XML (``pytest.xml``) files produced by each CI job, merges
them with historical data, and generates a markdown trend report showing
per-test status across the last N runs.

Usage:
    uv run python -m scripts.integration_test_report <reports-dir> <history-file> <output-file>
"""
