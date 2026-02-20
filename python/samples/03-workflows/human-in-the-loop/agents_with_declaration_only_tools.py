# Copyright (c) Microsoft. All rights reserved.

"""
Sample: Declaration-only tools in a workflow (issue #3425)

A declaration-only tool (func=None) represents a client-side tool that the
framework cannot execute — the LLM can call it, but the workflow must pause
so the caller can supply the result.

Flow:
  1. The agent is given a declaration-only tool ("get_user_location").
  2. When the LLM decides to call it, the workflow pauses and emits a
     request_info event containing the FunctionCallContent.
  3. The caller inspects the tool name/args, runs the tool however it wants,
     and feeds the result back via workflow.run(responses={...}).
  4. The workflow resumes — the agent sees the tool result and finishes.

Prerequisites:
  - AZURE_AI_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
  - Azure OpenAI endpoint configured via environment variables.
  - `az login` for AzureCliCredential.
"""

import asyncio
import json
import os
from typing import Any

from agent_framework import Content, FunctionTool, WorkflowBuilder
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# A declaration-only tool: the schema is sent to the LLM, but the framework
# has no implementation to execute. The caller must supply the result.
get_user_location = FunctionTool(
    name="get_user_location",
    func=None,
    description="Get the user's current city. Only the client application can resolve this.",
    input_model={
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Why the location is needed"},
        },
        "required": ["reason"],
    },
)


async def main() -> None:
    agent = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    ).as_agent(
        name="WeatherBot",
        instructions=(
            "You are a helpful weather assistant. "
            "When the user asks about weather, call get_user_location first, "
            "then make up a plausible forecast for that city."
        ),
        tools=[get_user_location],
    )

    workflow = WorkflowBuilder(start_executor=agent).build()

    # --- First run: the agent should call the declaration-only tool ---
    print(">>> Sending: 'What's the weather like today?'")
    result = await workflow.run("What's the weather like today?")

    requests = result.get_request_info_events()
    if not requests:
        # The LLM chose not to call the tool — print whatever it said and exit
        print(f"Agent replied without calling the tool: {result.get_outputs()}")
        return

    # --- Inspect what the agent wants ---
    for req in requests:
        data = req.data
        args = json.loads(data.arguments) if isinstance(data.arguments, str) else data.arguments
        print(f"Workflow paused — agent called: {data.name}({args})")

    # --- "Execute" the tool on the client side and send results back ---
    responses: dict[str, Any] = {}
    for req in requests:
        # In a real app this could be a GPS lookup, browser API, user prompt, etc.
        client_result = "Seattle, WA"
        print(f"Client provides result for {req.data.name}: {client_result!r}")
        responses[req.request_id] = Content.from_function_result(
            call_id=req.data.call_id,
            result=client_result,
        )

    result = await workflow.run(responses=responses)

    # --- Final answer ---
    for output in result.get_outputs():
        print(f"\nAgent: {output.text}")


if __name__ == "__main__":
    asyncio.run(main())
