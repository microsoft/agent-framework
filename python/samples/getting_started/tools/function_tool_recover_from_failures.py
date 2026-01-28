# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import FunctionCallContent, FunctionResultContent
from agent_framework import tool
from agent_framework.openai import OpenAIResponsesClient

"""
Tool exceptions handled by returning the error for the agent to recover from.

Shows how a tool that throws an exception creates gracefull recovery and can keep going.
The LLM decides whether to retry the call or to respond with something else, based on the exception.
"""

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def greet(name: Annotated[str, "Name to greet"]) -> str:
    """Greet someone."""
    return f"Hello, {name}!"


@tool(approval_mode="never_require")
# we trick the AI into calling this function with 0 as denominator to trigger the exception
@tool(approval_mode="never_require")
def safe_divide(
    a: Annotated[int, "Numerator"],
    b: Annotated[int, "Denominator"],
) -> str:
    """Divide two numbers can be used with 0 as denominator."""
    try:
        result = a / b  # Will raise ZeroDivisionError
    except ZeroDivisionError as exc:
        print(f"    Tool failed: with error: {exc}")
        raise

    return f"{a} / {b} = {result}"


async def main():
    # tools = Tools()
    agent = OpenAIResponsesClient().as_agent(
        name="ToolAgent",
        instructions="Use the provided tools.",
        tools=[greet, safe_divide],
    )
    thread = agent.get_new_thread()
    print("=" * 60)
    print("Step 1: Call divide(10, 0) - tool raises exception")
    response = await agent.run("Divide 10 by 0", thread=thread)
    print(f"Response: {response.text}")
    print("=" * 60)
    print("Step 2: Call greet('Bob') - conversation can keep going.")
    response = await agent.run("Greet Bob", thread=thread)
    print(f"Response: {response.text}")
    print("=" * 60)
    print("Replay the conversation:")
    assert thread.message_store
    assert thread.message_store.list_messages
    for idx, msg in enumerate(await thread.message_store.list_messages()):
        if msg.text:
            print(f"{idx + 1}  {msg.author_name or msg.role}: {msg.text} ")
        for content in msg.contents:
            if isinstance(content, FunctionCallContent):
                print(
                    f"{idx + 1}  {msg.author_name}: calling function: {content.name} with arguments: {content.arguments}"
                )
            if isinstance(content, FunctionResultContent):
                print(f"{idx + 1}  {msg.role}: {content.result if content.result else content.exception}")


"""
Expected Output:
============================================================
Step 1: Call divide(10, 0) - tool raises exception
    Tool failed: with error: division by zero
Response: Division by zero is undefined in standard arithmetic, so 10 ÷ 0 has no meaning.

If you’re curious about limits: as x approaches 0 from the positive side, 10/x tends to +∞; from the negative side,
10/x tends to -∞.

If you want a finite result, try dividing by a nonzero number, e.g., 10 ÷ 2 = 5 or 10 ÷ 0.1 = 100. Want me to compute
something else?
============================================================
Step 2: Call greet('Bob') - conversation can keep going.
Response: Hello, Bob!
============================================================
Replay the conversation:
1  user: Divide 10 by 0
2  ToolAgent: calling function: safe_divide with arguments: {"a":10,"b":0}
3  tool: division by zero
4  ToolAgent: Division by zero is undefined in standard arithmetic, so 10 ÷ 0 has no meaning.

If you’re curious about limits: as x approaches 0 from the positive side, 10/x tends to +∞; from the negative side,
10/x tends to -∞.

If you want a finite result, try dividing by a nonzero number, e.g., 10 ÷ 2 = 5 or 10 ÷ 0.1 = 100. Want me to compute
something else?
5  user: Greet Bob
6  ToolAgent: calling function: greet with arguments: {"name":"Bob"}
7  tool: Hello, Bob!
8  ToolAgent: Hello, Bob!
"""

if __name__ == "__main__":
    asyncio.run(main())
