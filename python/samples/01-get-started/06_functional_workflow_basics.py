# Copyright (c) Microsoft. All rights reserved.

"""
Functional Workflow Basics — Orchestrate async functions with @workflow

The functional API lets you write workflows as plain Python async functions.
No graph concepts, no edges, no executor classes — just call functions
and use native control flow (if/else, loops, asyncio.gather).

This sample builds a minimal pipeline with two steps:
1. Convert text to uppercase
2. Reverse the text

No external services are required.
"""

import asyncio

from agent_framework import workflow


# Plain async functions — no decorators needed
async def to_upper_case(text: str) -> str:
    """Convert input to uppercase."""
    return text.upper()


async def reverse_text(text: str) -> str:
    """Reverse the string."""
    return text[::-1]


# <create_workflow>
@workflow
async def text_workflow(text: str) -> str:
    """Uppercase the text, then reverse it."""
    upper = await to_upper_case(text)
    return await reverse_text(upper)
# </create_workflow>


async def main() -> None:
    # <run_workflow>
    result = await text_workflow.run("hello world")
    print(f"Output: {result.get_outputs()}")
    print(f"Final state: {result.get_final_state()}")
    # </run_workflow>

    """
    Expected output:
      Output: ['DLROW OLLEH']
      Final state: WorkflowRunState.IDLE
    """


if __name__ == "__main__":
    asyncio.run(main())
