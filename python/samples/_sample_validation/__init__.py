# Copyright (c) Microsoft. All rights reserved.

"""
Sample Validation System

A workflow-based system for validating Python samples by:
1. Discovering all sample files
2. Creating a dynamic nested concurrent workflow (one GitHub agent per sample)
3. Running the nested workflow
4. Generating a validation report

Usage:
    uv run python -m _sample_validation
    uv run python -m _sample_validation --subdir 01-get-started
"""

from _sample_validation.models import Report, RunResult, SampleInfo
from _sample_validation.workflow import create_validation_workflow

__all__ = [
    "SampleInfo",
    "RunResult",
    "Report",
    "create_validation_workflow",
]
