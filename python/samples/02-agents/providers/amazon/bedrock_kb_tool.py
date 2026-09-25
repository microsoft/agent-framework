# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent
from agent_framework.amazon import BedrockChatClient, BedrockChatOptions, BedrockKnowledgeBaseProvider
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Bedrock Knowledge Base — tool mode

`BedrockKnowledgeBaseProvider` is the single entry point for using an Amazon Bedrock managed
Knowledge Base with an agent. With `mode="tool"`, it exposes a Knowledge Base *search tool* the
model can call on demand (rather than injecting context on every turn). The same provider also
supports `mode="inject"` and `mode="both"` (the default).

Environment variables used:
- `BEDROCK_CHAT_MODEL`
- `BEDROCK_REGION` (defaults to `us-east-1` if unset)
- AWS credentials via standard variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
  optional `AWS_SESSION_TOKEN`)

Required IAM permissions: `bedrock:Retrieve` (always). The default agentic path
(`use_agentic_retrieval=True`) additionally needs `bedrock:AgenticRetrieveStream`,
`bedrock:GetDocumentContent`, and `bedrock:InvokeModelWithResponseStream`; without them
the agentic call fails or falls back to single-pass retrieval. See the amazon provider
README for the exact policy.
"""


async def main() -> None:
    """Run a Bedrock-backed agent that can query a managed Knowledge Base on demand (tool mode)."""
    # 1. Create the provider in tool mode — it exposes a KB search tool the model calls when
    #    it needs context. Region/credentials resolve from BEDROCK_* (same as BedrockChatClient).
    kb_provider = BedrockKnowledgeBaseProvider(
        knowledge_base_id="YOUR_KB_ID",  # Replace with your managed KB ID
        mode="tool",
        number_of_results=5,
        use_agentic_retrieval=True,  # Query decomposition + managed reranking, with fallback
    )

    # 2. Attach the provider — in tool mode it adds the KB search tool for each run.
    agent = Agent(
        client=BedrockChatClient(),
        name="KnowledgeAssistant",
        instructions="You are a helpful assistant. Use the knowledge base tool to answer questions about the company.",
        context_providers=[kb_provider],
        default_options=BedrockChatOptions(tool_choice="auto"),
    )

    # 3. Run a query — the model calls the KB search tool when it needs context.
    query = "What is our return policy for electronics?"
    print(f"User: {query}")
    response = await agent.run(query)
    print(f"Assistant: {response.text}")


"""
Expected Output:
============================================================
User: What is our return policy for electronics?
Assistant: According to the knowledge base, electronics can be returned within 30
days of purchase with the original receipt. Items must be in their original
packaging and undamaged. Opened software and consumables are non-refundable.
============================================================

Notes:
- mode="tool" exposes a KB search tool rather than injecting context every turn;
  the model decides when to call it. Use mode="inject" for always-on context, or
  mode="both" (the default) for both.
- With use_agentic_retrieval=True the search uses AgenticRetrieveStream (query
  decomposition + managed reranking) and falls back to single-pass Retrieve if the
  agentic call is unavailable.
"""


if __name__ == "__main__":
    asyncio.run(main())
