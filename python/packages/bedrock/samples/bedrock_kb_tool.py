# Copyright (c) Microsoft. All rights reserved.

"""Sample: Using BedrockKnowledgeBaseTool with an Agent.

This demonstrates how the Bedrock Knowledge Base tool integrates with
Agent Framework primitives. The tool subclasses FunctionTool and can be
passed directly to any Agent or ChatClient.

Prerequisites:
    pip install agent-framework-bedrock
    export AWS_DEFAULT_REGION=us-west-2
    # AWS credentials configured (IAM role with bedrock:Retrieve and bedrock:AgenticRetrieveStream)
"""

import asyncio

from agent_framework import Agent
from agent_framework_bedrock import BedrockChatClient, BedrockChatOptions, BedrockKnowledgeBaseTool


async def main() -> None:
    # Create the Knowledge Base tool — subclasses FunctionTool, pass directly to Agent
    kb_tool = BedrockKnowledgeBaseTool(
        knowledge_base_id="YOUR_KB_ID",  # Replace with your managed KB ID
        region_name="us-west-2",
        number_of_results=5,
        use_agentic_retrieval=True,  # Uses query decomposition + managed reranking
    )

    # Create a Bedrock chat client
    chat_client = BedrockChatClient(
        options=BedrockChatOptions(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0")
    )

    # Create an agent with the KB tool — Agent will call it when it needs context
    agent = Agent(
        name="KnowledgeAssistant",
        instructions="You are a helpful assistant. Use the knowledge base tool to answer questions about the company.",
        chat_client=chat_client,
        tools=[kb_tool],  # FunctionTool subclass, works with any ChatClient
    )

    # Run the agent
    session = agent.create_session()
    response = await agent.invoke(
        session=session,
        input_message="What is our return policy for electronics?",
    )
    print(f"Agent response: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())
