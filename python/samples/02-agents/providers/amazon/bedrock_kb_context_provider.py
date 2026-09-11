# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent
from agent_framework.amazon import BedrockChatClient, BedrockKnowledgeBaseProvider
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Bedrock Knowledge Base Context Provider Example

This sample demonstrates the `ContextProvider` pattern with `BedrockKnowledgeBaseProvider`. KB
context is retrieved and injected automatically before every agent invocation (via `before_run()`),
so no explicit tool calling is needed. Retrieved passages are added to the untrusted user message
channel rather than the system instructions.

Environment variables used:
- `BEDROCK_CHAT_MODEL`
- `BEDROCK_REGION` (defaults to `us-east-1` if unset)
- AWS credentials via standard variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
  optional `AWS_SESSION_TOKEN`)

Required IAM permissions: `bedrock:Retrieve`
(see the amazon provider README for the exact policy).
"""


async def main() -> None:
    """Run a Bedrock-backed agent that always has KB context injected automatically."""
    # 1. Create the Knowledge Base context provider — subclasses ContextProvider.
    kb_provider = BedrockKnowledgeBaseProvider(
        knowledge_base_id="YOUR_KB_ID",  # Replace with your managed KB ID
        region_name="us-west-2",
        number_of_results=3,
        min_score=0.3,  # Only include results above this relevance threshold
        source_id="company-docs",  # Unique ID for this context source
    )

    # 2. Create an agent with the context provider — context is injected on every run.
    agent = Agent(
        client=BedrockChatClient(),
        name="ContextualAssistant",
        instructions="You are a helpful assistant that answers based on provided context.",
        context_providers=[kb_provider],  # ContextProvider subclass, injects context on every run
    )

    # 3. Run a query — KB context is retrieved and injected automatically via before_run().
    query = "What data sources does Bedrock support?"
    print(f"User: {query}")
    response = await agent.run(query)
    print(f"Assistant: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())
