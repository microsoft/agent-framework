# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent
from agent_framework.amazon import BedrockChatClient, BedrockChatOptions, BedrockKnowledgeBaseTool
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Bedrock Knowledge Base Tool Example

This sample demonstrates using `BedrockKnowledgeBaseTool` with an `Agent`. The tool subclasses
`FunctionTool` and can be passed directly to any Agent or ChatClient; the agent decides when to
call it to retrieve context from an Amazon Bedrock managed Knowledge Base.

Environment variables used:
- `BEDROCK_CHAT_MODEL`
- `BEDROCK_REGION` (defaults to `us-east-1` if unset)
- AWS credentials via standard variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
  optional `AWS_SESSION_TOKEN`)

Required IAM permissions: `bedrock:Retrieve` and `bedrock:AgenticRetrieveStream`
(see the amazon provider README for the exact policy).
"""


async def main() -> None:
    """Run a Bedrock-backed agent that can query a managed Knowledge Base on demand."""
    # 1. Create the Knowledge Base tool — subclasses FunctionTool, pass directly to Agent.
    #    Use the same region as BedrockChatClient (BEDROCK_REGION), so the KB and the model
    #    are queried in the same region.
    kb_tool = BedrockKnowledgeBaseTool(
        knowledge_base_id="YOUR_KB_ID",  # Replace with your managed KB ID
        region_name=os.environ.get("BEDROCK_REGION", "us-east-1"),
        number_of_results=5,
        use_agentic_retrieval=True,  # Uses query decomposition + managed reranking
    )

    # 2. Create an agent with the KB tool — the agent calls it when it needs context.
    agent = Agent(
        client=BedrockChatClient(),
        name="KnowledgeAssistant",
        instructions="You are a helpful assistant. Use the knowledge base tool to answer questions about the company.",
        tools=[kb_tool],  # FunctionTool subclass, works with any ChatClient
        default_options=BedrockChatOptions(tool_choice="auto"),
    )

    # 3. Run a query that uses the KB tool.
    query = "What is our return policy for electronics?"
    print(f"User: {query}")
    response = await agent.run(query)
    print(f"Assistant: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())
