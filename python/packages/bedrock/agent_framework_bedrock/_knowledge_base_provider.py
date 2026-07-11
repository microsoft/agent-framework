# Copyright (c) Microsoft. All rights reserved.

"""Amazon Bedrock Knowledge Base Context Provider for Microsoft Agent Framework.

Provides automatic retrieval-augmented context from a Bedrock Managed Knowledge Base
before each model invocation — similar to FoundryMemoryProvider but backed by AWS.

Usage:
    from agent_framework import Agent, AgentSession
    from agent_framework_bedrock._knowledge_base_provider import BedrockKnowledgeBaseProvider

    kb_provider = BedrockKnowledgeBaseProvider(
        source_id="bedrock-kb",
        knowledge_base_id="ABCDEFGHIJ",
        region_name="us-west-2",
    )

    agent = Agent(context_providers=[kb_provider])
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Optional

from agent_framework import (
    AgentSession,
    ContextProvider,
    SessionContext,
)

if TYPE_CHECKING:
    from agent_framework import SupportsAgentRun

logger = logging.getLogger(__name__)


def _get_source_uri(result: dict) -> str:
    """Extract source URI from a retrieval result, handling all location types."""
    location = result.get("location", {})
    loc_type = location.get("type", "")
    if loc_type == "S3" or "s3Location" in location:
        return location.get("s3Location", {}).get("uri", "")
    if loc_type == "WEB" or "webLocation" in location:
        return location.get("webLocation", {}).get("url", "")
    if "confluenceLocation" in location:
        return location.get("confluenceLocation", {}).get("url", "")
    if "salesforceLocation" in location:
        return location.get("salesforceLocation", {}).get("url", "")
    if "sharePointLocation" in location:
        return location.get("sharePointLocation", {}).get("url", "")
    if "customDocumentLocation" in location:
        return location.get("customDocumentLocation", {}).get("id", "")
    # Fallback to metadata._source_uri (for agentic results)
    return result.get("metadata", {}).get("_source_uri", "")


class BedrockKnowledgeBaseProvider(ContextProvider):
    """Context provider that retrieves relevant documents from a Bedrock Knowledge Base.

    Automatically queries the KB with the user's latest message before each model
    invocation, injecting retrieved context as system messages.

    Args:
        source_id: Unique identifier for this provider instance.
        knowledge_base_id: The KB ID. Falls back to KNOWLEDGE_BASE_ID env var.
        region_name: AWS region. Falls back to AWS_REGION env var or us-east-1.
        number_of_results: Max results to retrieve per query. Defaults to 5.
        min_score: Minimum relevance score to include a result. Defaults to 0.0.
    """

    def __init__(
        self,
        source_id: str = "bedrock-kb",
        knowledge_base_id: Optional[str] = None,
        region_name: Optional[str] = None,
        number_of_results: int = 5,
        min_score: float = 0.0,
    ):
        super().__init__(source_id=source_id)
        self.knowledge_base_id = knowledge_base_id or os.environ.get("KNOWLEDGE_BASE_ID", "")
        self.region_name = region_name or os.environ.get("AWS_REGION", "us-east-1")
        self.number_of_results = number_of_results
        self.min_score = min_score
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError:
                raise ImportError(
                    "boto3 is required for BedrockKnowledgeBaseProvider. Install with: pip install boto3>=1.43.2"
                )
            self._client = boto3.client(
                "bedrock-agent-runtime",
                region_name=self.region_name,
                config=Config(user_agent_extra="ms-agent-framework/bedrock-kb"),
            )
        return self._client

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Retrieve relevant KB context before model invocation.

        Extracts the latest user message, queries the knowledge base,
        and injects retrieved passages as context messages.
        """
        if not self.knowledge_base_id:
            logger.warning("No knowledge_base_id configured. Skipping KB context.")
            return

        # Extract the latest user query from the session
        query = self._extract_latest_query(session)
        if not query:
            return

        # Retrieve from KB
        passages = await self._retrieve(query)
        if not passages:
            return

        # Inject as context
        context_text = self._format_context(passages)
        context.add_instructions(f"[Knowledge Base Context from {self.source_id}]\n{context_text}")

    def _extract_latest_query(self, session: AgentSession) -> str:
        """Extract the most recent user message as the retrieval query."""
        messages = session.messages if hasattr(session, "messages") else []
        for message in reversed(messages):
            if hasattr(message, "role") and message.role == "user" and hasattr(message, "content"):
                content = message.content
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    # Extract text from content parts
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            return part.get("text", "")
                        if isinstance(part, str):
                            return part
        return ""

    async def _retrieve(self, query: str) -> list[dict[str, Any]]:
        """Query the Bedrock Knowledge Base."""
        retrieval_config: dict[str, Any] = {"managedSearchConfiguration": {"numberOfResults": self.number_of_results}}

        try:
            response = self.client.retrieve(
                knowledgeBaseId=self.knowledge_base_id,
                retrievalQuery={"text": query},
                retrievalConfiguration=retrieval_config,
            )

            results = []
            for result in response.get("retrievalResults", []):
                score = result.get("score", 0.0)
                if score < self.min_score:
                    continue
                content = result.get("content", {}).get("text", "")
                source = _get_source_uri(result)
                if content:
                    results.append({
                        "content": content,
                        "source": source,
                        "score": score,
                    })
            return results
        except Exception:
            logger.exception("Error retrieving from Bedrock KB")
            return []

    def _format_context(self, passages: list[dict[str, Any]]) -> str:
        """Format retrieved passages into a context string."""
        formatted = []
        for i, passage in enumerate(passages, 1):
            source = passage.get("source", "unknown")
            content = passage.get("content", "")
            formatted.append(f"[{i}] {content}\n    Source: {source}")
        return "\n\n".join(formatted)
