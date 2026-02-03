# Copyright (c) Microsoft. All rights reserved.

from agent_framework import FunctionTool
from agent_framework.openai import OpenAIResponsesClient

"""
Example of how to create a function that only consists of a declaration without an implementation.
This is useful when you want the agent to use tools that are defined elsewhere or when you want
to test the agent's ability to reason about tool usage without executing them.

The only difference is that you provide a FunctionTool without a function.
If you need a input_model, you can still provide that as well.
"""


async def main():
    function_declaration = FunctionTool(
        name="get_current_time",
        description="Get the current time in ISO 8601 format.",
    )

    agent = OpenAIResponsesClient().as_agent(
        name="DeclarationOnlyToolAgent",
        instructions="You are a helpful agent that uses tools.",
        tools=function_declaration,
    )
    query = "What is the current time?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Result: {result.to_json(indent=2)}\n")


"""
Expected result:
User: What is the current time?
Result: {
  "type": "agent_response",
  "messages": [
    {
      "type": "chat_message",
      "role": {
        "type": "role",
        "value": "assistant"
      },
      "contents": [
        {
          "type": "function_call",
          "call_id": "call_0flN9rfGLK8LhORy4uMDiRSC",
          "name": "get_current_time",
          "arguments": "{}",
          "fc_id": "fc_0fd5f269955c589f016904c46584348195b84a8736e61248de"
        }
      ],
      "author_name": "DeclarationOnlyToolAgent",
      "additional_properties": {}
    }
  ],
  "response_id": "resp_0fd5f269955c589f016904c462d5cc819599d28384ba067edc",
  "created_at": "2025-10-31T15:14:58.000000Z",
  "usage_details": {
    "type": "usage_details",
    "input_token_count": 63,
    "output_token_count": 145,
    "total_token_count": 208,
    "openai.reasoning_tokens": 128
  },
  "additional_properties": {}
}
"""


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
