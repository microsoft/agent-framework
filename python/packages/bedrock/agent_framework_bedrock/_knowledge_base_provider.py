# Copyright (c) Microsoft. All rights reserved.

"""Amazon Bedrock Knowledge Base context provider for Agent Framework."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional

from agent_framework import Message
from agent_framework._sessions import AgentSession, ContextProvider, SessionContext
from agent_framework._telemetry import get_user_agent

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun
    from botocore.client import BaseClient

try:
    import boto3
    from botocore.config import Config as BotoConfig
except ImportError as e:
    raise ImportError(
        "boto3 is required for BedrockKnowledgeBaseProvider. "
        "Install it with: pip install boto3>=1.43.32"
    ) from e

from agent_framework_bedrock._knowledge_base import _get_source_uri


class BedrockKnowledgeBaseProvider(ContextProvider):
    """Context provider that injects Bedrock Knowledge Base results before agent runs.

    Subclasses ContextProvider and implements before_run() to automatically
    retrieve relevant context from a Bedrock Knowledge Base on every agent invocation.

    Usage:
        from agent_framework_bedrock import BedrockKnowledgeBaseProvider

        provider = BedrockKnowledgeBaseProvider(knowledge_base_id="YOUR_KB_ID")
        agent = Agent(context_providers=[provider])
    """

    DEFAULT_CONTEXT_PROMPT = (
        "## Knowledge Base Context\n"
        "The following passages were retrieved from the knowledge base. "
        "Use them to answer the user's question:"
    )

    def __init__(
        self,
        *,
        knowledge_base_id: str,
        region_name: str = "us-east-1",
        number_of_results: int = 5,
        min_score: float = 0.0,
        source_id: str = "bedrock-kb",
        context_prompt: str | None = None,
        client: Optional[BaseClient] = None,
    ) -> None:
        """Create a Bedrock Knowledge Base context provider.

        Args:
            knowledge_base_id: The Bedrock Knowledge Base ID.
            region_name: AWS region name.
            number_of_results: Maximum number of results to inject as context.
            min_score: Minimum relevance score threshold.
            source_id: Identifier for this context source.
            context_prompt: Custom prompt to prepend to retrieved context.
            client: Pre-configured bedrock-agent-runtime client. If not provided, one is created.
        """
        super().__init__(source_id)
        self.knowledge_base_id = knowledge_base_id
        self.region_name = region_name
        self.number_of_results = number_of_results
        self.min_score = min_score
        self.context_prompt = context_prompt or self.DEFAULT_CONTEXT_PROMPT

        if client:
            self._client = client
        else:
            self._client = boto3.client(
                "bedrock-agent-runtime",
                region_name=self.region_name,
                config=BotoConfig(user_agent_extra=f"{get_user_agent()} bedrock-kb"),
            )

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Retrieve relevant KB context and inject it into the session context.

        Called automatically before each model invocation. Extracts the user's
        query from input messages, retrieves relevant passages, and adds them
        as a system message to the context.

        Args:
            agent: The agent running this invocation.
            session: The current session.
            context: The invocation context - add messages here.
            state: The provider-scoped mutable state dict.
        """
        # Extract query from input messages
        input_text = "\n".join(
            msg.text for msg in context.input_messages if msg and msg.text and msg.text.strip()
        )
        if not input_text.strip():
            return

        # Retrieve from knowledge base
        retrieved_context = await self._retrieve(input_text)
        if not retrieved_context:
            return

        # Inject as a system message via extend_messages
        context_message = Message(role="system", contents=[f"{self.context_prompt}\n\n{retrieved_context}"])
        context.extend_messages(self, [context_message])

    async def _retrieve(self, query: str) -> str:
        """Retrieve and format context from the knowledge base."""
        response = await asyncio.to_thread(
            lambda: self._client.retrieve(
                knowledgeBaseId=self.knowledge_base_id,
                retrievalQuery={"text": query},
                retrievalConfiguration={"managedSearchConfiguration": {"numberOfResults": self.number_of_results}},
            )
        )

        passages = []
        for r in response.get("retrievalResults", []):
            score = r.get("score", 0)
            if score >= self.min_score:
                content = r.get("content", {}).get("text", "")
                source = _get_source_uri(r)
                passages.append(f"[Source: {source}]\n{content}")

        return "\n\n---\n\n".join(passages) if passages else ""
