# Copyright (c) Microsoft. All rights reserved.

"""Workflow fixtures for hosting tests.

Defined in a module that does not use ``from __future__ import annotations``
because the workflow handler validation reflects on real annotation objects
rather than stringified forms.
"""

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler


class _UpperExecutor(Executor):
    @handler
    async def handle(self, text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.yield_output(text.upper())


class _EchoExecutor(Executor):
    @handler
    async def handle(self, text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.yield_output(text)


def build_upper_workflow() -> Workflow:
    return WorkflowBuilder(start_executor=_UpperExecutor(id="upper")).build()


def build_echo_workflow() -> Workflow:
    return WorkflowBuilder(start_executor=_EchoExecutor(id="echo")).build()


class _MultiChunkExecutor(Executor):
    """Yields three separate ``output`` events so streaming has something to chew on."""

    @handler
    async def handle(self, text: str, ctx: WorkflowContext[str]) -> None:
        for chunk in (f"{text}-1", f"{text}-2", f"{text}-3"):
            await ctx.yield_output(chunk)


def build_multi_chunk_workflow() -> Workflow:
    return WorkflowBuilder(start_executor=_MultiChunkExecutor(id="multi")).build()
