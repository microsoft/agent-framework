# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import ChatAgent
from agent_framework.openai import OpenAIResponsesClient

"""
RAG with Context Providers

Demonstrates Retrieval-Augmented Generation (RAG) using a ContextProvider
to inject relevant documents into the agent's context before each call.

This example uses a simple in-memory context provider. For production use cases,
see the deeper samples using Azure AI Search, Redis, or Mem0.

For more on context providers:
- Azure AI Search: getting_started/context_providers/azure_ai_search/
- Redis: getting_started/context_providers/redis/
- Mem0: getting_started/context_providers/mem0/
- Custom: getting_started/context_providers/simple_context_provider.py
- Docs: https://learn.microsoft.com/agent-framework/concepts/context-providers
"""

from collections.abc import MutableSequence, Sequence
from typing import Any

from agent_framework import ChatMessage, Context, ContextProvider


# <context_provider>
class SimpleRAGProvider(ContextProvider):
    """A simple in-memory context provider that searches a document store."""

    def __init__(self, documents: dict[str, str]) -> None:
        self._documents = documents

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        """Called before each agent invocation to provide relevant context."""
        # Get the latest user message
        if isinstance(messages, ChatMessage):
            query = messages.text or ""
        else:
            query = messages[-1].text or "" if messages else ""

        # Simple keyword search (replace with vector search in production)
        relevant_docs: list[str] = []
        for title, content in self._documents.items():
            if any(word.lower() in content.lower() for word in query.split()):
                relevant_docs.append(f"**{title}**: {content}")

        if relevant_docs:
            context_text = "Relevant documents:\n" + "\n\n".join(relevant_docs)
            return Context(instructions=context_text)

        return Context(instructions="No relevant documents found in the knowledge base.")

    async def invoked(
        self,
        request_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage] | None = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """Called after each agent invocation (for logging, analytics, etc.)."""
        pass
# </context_provider>


# <sample_documents>
KNOWLEDGE_BASE = {
    "Python Basics": "Python is a high-level programming language known for its readability. "
    "It supports multiple paradigms including object-oriented, functional, and procedural programming.",
    "Agent Framework Overview": "Agent Framework is Microsoft's SDK for building AI agents. "
    "It supports multiple LLM providers including OpenAI, Azure OpenAI, Anthropic, and Ollama.",
    "RAG Pattern": "Retrieval-Augmented Generation (RAG) combines information retrieval with "
    "text generation. Documents are retrieved based on relevance and provided as context to the LLM.",
}
# </sample_documents>


async def main() -> None:
    print("=== RAG with Context Providers ===\n")

    # <create_agent_with_rag>
    rag_provider = SimpleRAGProvider(documents=KNOWLEDGE_BASE)

    agent = ChatAgent(
        chat_client=OpenAIResponsesClient(),
        name="RAGAgent",
        instructions="You are a helpful assistant. Use the provided context to answer questions accurately.",
        context_provider=rag_provider,
    )
    # </create_agent_with_rag>

    # <run_queries>
    queries = [
        "What is Agent Framework?",
        "Explain the RAG pattern",
        "What programming paradigms does Python support?",
    ]

    thread = agent.get_new_thread()
    for query in queries:
        print(f"User: {query}")
        response = await agent.run(query, thread=thread)
        print(f"Agent: {response}\n")
    # </run_queries>


if __name__ == "__main__":
    asyncio.run(main())
