# Copyright (c) Microsoft. All rights reserved.

"""Sample: Using BedrockKnowledgeBaseProvider for automatic context injection.

This demonstrates the ContextProvider pattern where KB context is automatically
retrieved and injected before every agent invocation — no explicit tool calling needed.

Prerequisites:
    pip install agent-framework-bedrock
    export AWS_DEFAULT_REGION=us-west-2
    # AWS credentials configured (IAM role with bedrock:Retrieve)
"""

import asyncio

from agent_framework import Agent
from agent_framework_bedrock import BedrockChatClient, BedrockChatOptions, BedrockKnowledgeBaseProvider


async def main() -> None:
    # Create the Knowledge Base context provider — subclasses ContextProvider
    kb_provider = BedrockKnowledgeBaseProvider(
        knowledge_base_id="YOUR_KB_ID",  # Replace with your managed KB ID
        region_name="us-west-2",
        number_of_results=3,
        min_score=0.3,  # Only include results above this relevance threshold
        source_id="company-docs",  # Unique ID for this context source
    )

    # Create a Bedrock chat client
    chat_client = BedrockChatClient(
        options=BedrockChatOptions(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0")
    )

    # Create an agent with the context provider — context is injected automatically
    agent = Agent(
        client=chat_client,
        name="ContextualAssistant",
        instructions="You are a helpful assistant that answers based on provided context.",
        context_providers=[kb_provider],  # ContextProvider subclass, injects context on every run
    )

    # Run the agent — KB context is retrieved and injected automatically via before_run()
    session = agent.create_session()
    response = await agent.run("What data sources does Bedrock support?", session=session)
    print(f"Agent response: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())
