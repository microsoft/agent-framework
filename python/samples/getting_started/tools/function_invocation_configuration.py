# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework.openai import OpenAIResponsesClient

"""
This sample demonstrates how to configure function invocation settings
for an client and use a simple ai_function as a tool in an agent.

This behavior is the same for all chat client types.
"""


def add(
    x: Annotated[int, "First number"],
    y: Annotated[int, "Second number"],
) -> str:
    return f"{x} + {y} = {x + y}"


async def main():
    client = OpenAIResponsesClient()
    if client.function_invocation_configuration is not None:
        client.function_invocation_configuration.max_iterations = 5
        print(f"Function invocation configured with: {client.function_invocation_configuration.to_json(indent=2)}")

    agent = client.create_agent(name="ToolAgent", instructions="Use the provided tools.", tools=add)

    print("=" * 60)
    print("Call add(239847293, 29834)")
    query = "Add 239847293 and 29834"
    response = await agent.run(query)
    print(f"Response: {response.text}")


"""
Expected Output:
============================================================
Function invocation configured with: {
  "type": "function_invocation_configuration",
  "enabled": true,
  "max_iterations": 5,
  "max_consecutive_errors_per_request": 3,
  "terminate_on_unknown_calls": false,
  "additional_tools": []
}
============================================================
Call add(239847293, 29834)
Response: The sum is 239,877,127.
"""

if __name__ == "__main__":
    asyncio.run(main())
