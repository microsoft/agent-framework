# Copyright (c) Microsoft. All rights reserved.

"""Tests for the three-state output_executors contract on WorkflowBuilder.

State A: output_executors=None (unset, legacy)  -> DeprecationWarning at build
State B: output_executors=[] (explicit, no terminals) -> strict mode
State C: output_executors=[X, ...] (explicit list) -> strict mode
"""

from __future__ import annotations

import warnings

import pytest
from typing_extensions import Never

from agent_framework import (
    Message,
    WorkflowBuilder,
    WorkflowContext,
    executor,
)


@executor
async def _emit_one(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:
    await ctx.yield_output("hello")


def test_output_executors_unset_emits_deprecation_warning() -> None:
    """State A: WorkflowBuilder built without explicit output_executors warns."""
    with pytest.warns(DeprecationWarning, match="output_executors"):
        WorkflowBuilder(start_executor=_emit_one).build()


@pytest.mark.parametrize("output_executors", [[], [_emit_one]], ids=["empty_list", "designated_list"])
def test_output_executors_explicit_value_does_not_warn(output_executors) -> None:
    """States B and C: any explicit list (including ``[]``) opts into strict mode without warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        WorkflowBuilder(start_executor=_emit_one, output_executors=output_executors).build()
