# Copyright (c) Microsoft. All rights reserved.

"""Run two async functions as a functional workflow.

The workflow uppercases text, then reverses it using normal Python control flow.
"""

import asyncio

from agent_framework import workflow


async def to_upper_case(text: str) -> str:
    return text.upper()


async def reverse_text(text: str) -> str:
    return text[::-1]


@workflow
async def text_workflow(text: str) -> str:
    upper = await to_upper_case(text)
    return await reverse_text(upper)


async def main() -> None:
    result = await text_workflow.build().run("hello world")
    print(result.get_outputs()[0])


if __name__ == "__main__":
    asyncio.run(main())
