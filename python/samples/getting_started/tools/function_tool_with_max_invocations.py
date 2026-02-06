# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import FunctionCallContent, FunctionResultContent, tool
from agent_framework.openai import OpenAIResponsesClient

"""
For tools you can specify if there is a maximum number of invocations allowed.
This sample shows a tool that can only be invoked once.
"""


@tool(max_invocations=1)
def unicorn_function(times: Annotated[int, "The number of unicorns to return."]) -> str:
    """This function returns precious unicorns!"""
    return f"{'🦄' * times}✨"


async def main():
    # tools = Tools()
    agent = OpenAIResponsesClient().as_agent(
        name="ToolAgent",
        instructions="Use the provided tools.",
        tools=[unicorn_function],
    )
    thread = agent.get_new_thread()
    print("=" * 60)
    print("Step 1: Call unicorn_function")
    response = await agent.run("Call 5 unicorns!", thread=thread)
    print(f"Response: {response.text}")
    print("=" * 60)
    print("Step 2: Call unicorn_function again - will refuse to execute due to max_invocations")
    response = await agent.run("Call 10 unicorns and use the function to do it.", thread=thread)
    print(f"Response: {response.text}")
    print("=" * 60)
    print(f"Number of tool calls attempted: {unicorn_function.invocation_count}")
    print(f"Number of tool calls failed: {unicorn_function.invocation_exception_count}")
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
Step 1: Call unicorn_function
Response: Five unicorns summoned: 🦄🦄🦄🦄🦄✨
============================================================
Step 2: Call unicorn_function again - will refuse to execute due to max_invocations
[2025-10-31 15:54:40 - /Users/edvan/Work/agent-framework/python/packages/core/agent_framework/_tools.py:718 - ERROR]
Function failed. Error: Function 'unicorn_function' has reached its maximum invocation limit,
you can no longer use this tool.
Response: The unicorn function has reached its maximum invocation limit. I can’t call it again right now.

Here are 10 unicorns manually: 🦄 🦄 🦄 🦄 🦄 🦄 🦄 🦄 🦄 🦄

Would you like me to try again later, or generate something else?
============================================================
Number of tool calls attempted: 1
Number of tool calls failed: 0
Replay the conversation:
1  user: Call 5 unicorns!
2  ToolAgent: calling function: unicorn_function with arguments: {"times":5}
3  tool: 🦄🦄🦄🦄🦄✨
4  ToolAgent: Five unicorns summoned: 🦄🦄🦄🦄🦄✨
5  user: Call 10 unicorns and use the function to do it.
6  ToolAgent: calling function: unicorn_function with arguments: {"times":10}
7  tool: Function 'unicorn_function' has reached its maximum invocation limit, you can no longer use this tool.
8  ToolAgent: The unicorn function has reached its maximum invocation limit. I can’t call it again right now.

Here are 10 unicorns manually: 🦄 🦄 🦄 🦄 🦄 🦄 🦄 🦄 🦄 🦄

Would you like me to try again later, or generate something else?
"""

if __name__ == "__main__":
    asyncio.run(main())
