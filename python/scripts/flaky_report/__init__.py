# Copyright (c) Microsoft. All rights reserved.

"""Flaky test report aggregation and trend generation.

Parses JUnit XML (``pytest.xml``) files produced by each CI job, merges
them with historical data, and generates a markdown trend report showing
per-test status across the last N runs.

Usage:
    uv run python -m scripts.flaky_report <reports-dir> <history-file> <output-file>
"""
