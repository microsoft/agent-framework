# Copyright (c) Microsoft. All rights reserved.

"""Amazon Bedrock Knowledge Base retrieval tool for Agent Framework."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Annotated, Any, Optional

from agent_framework import FunctionTool
from agent_framework._telemetry import get_user_agent
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from botocore.client import BaseClient

try:
    import boto3
    from botocore.config import Config as BotoConfig
except ImportError as e:
    raise ImportError(
        "boto3 is required for BedrockKnowledgeBaseTool. "
        "Install it with: pip install boto3>=1.43.32"
    ) from e

logger = logging.getLogger(__name__)


def _get_source_uri(result: dict) -> str:
    """Extract source URI from a retrieval result."""
    location = result.get("location", {})
    if "s3Location" in location:
        return location["s3Location"].get("uri", "")
    if "webLocation" in location:
        return location["webLocation"].get("url", "")
    if "confluenceLocation" in location:
        return location["confluenceLocation"].get("url", "")
    if "sharePointLocation" in location:
        return location["sharePointLocation"].get("url", "")
    if "customDocumentLocation" in location:
        return location["customDocumentLocation"].get("id", "")
    return ""


class _BedrockKBQueryInput(BaseModel):
    """Input schema for the Bedrock Knowledge Base tool."""

    query: Annotated[str, Field(description="The search query to find relevant documents in the knowledge base.")]


class BedrockKnowledgeBaseTool(FunctionTool):
    """Tool that retrieves documents from Amazon Bedrock Knowledge Bases.

    Subclasses FunctionTool so it can be passed directly to any Agent or ChatClient.

    Usage:
        from agent_framework_bedrock import BedrockKnowledgeBaseTool

        tool = BedrockKnowledgeBaseTool(knowledge_base_id="YOUR_KB_ID")
        agent = Agent(tools=[tool])
    """

    def __init__(
        self,
        *,
        knowledge_base_id: str,
        region_name: str = "us-east-1",
        number_of_results: int = 5,
        use_agentic_retrieval: bool = True,
        client: Optional[BaseClient] = None,
        name: str = "bedrock_knowledge_base",
        description: str = (
            "Retrieves relevant documents from an Amazon Bedrock Knowledge Base. "
            "Use this to answer questions that require specific knowledge or context."
        ),
    ) -> None:
        """Create a Bedrock Knowledge Base tool.

        Args:
            knowledge_base_id: The Bedrock Knowledge Base ID.
            region_name: AWS region name.
            number_of_results: Maximum number of results to return.
            use_agentic_retrieval: Use AgenticRetrieveStream for query decomposition + reranking.
            client: Pre-configured bedrock-agent-runtime client. If not provided, one is created.
            name: Tool name for model registration.
            description: Tool description for model context.
        """
        self.knowledge_base_id = knowledge_base_id
        self.region_name = region_name
        self.number_of_results = number_of_results
        self.use_agentic_retrieval = use_agentic_retrieval

        if client:
            self._client = client
        else:
            self._client = boto3.client(
                "bedrock-agent-runtime",
                region_name=self.region_name,
                config=BotoConfig(user_agent_extra=f"{get_user_agent()} bedrock-kb"),
            )

        super().__init__(
            name=name,
            description=description,
            func=self._retrieve,
            input_model=_BedrockKBQueryInput,
        )

    async def _retrieve(self, query: str) -> str:
        """Retrieve documents from the knowledge base.

        Args:
            query: The search query.

        Returns:
            Formatted string of retrieval results.
        """
        if self.use_agentic_retrieval:
            try:
                results = await asyncio.to_thread(self._agentic_retrieve, query)
                if results:
                    return self._format_results(results)
            except Exception as e:
                logger.debug("Agentic retrieval failed, falling back: %s", e)

        results = await asyncio.to_thread(self._standard_retrieve, query)
        return self._format_results(results)

    def _agentic_retrieve(self, query: str) -> list[dict[str, Any]]:
        """Use AgenticRetrieveStream for query decomposition + managed reranking."""
        response = self._client.agentic_retrieve_stream(
            messages=[{"content": {"text": query}, "role": "user"}],
            retrievers=[{
                "configuration": {
                    "knowledgeBase": {
                        "knowledgeBaseId": self.knowledge_base_id,
                        "retrievalOverrides": {"maxNumberOfResults": self.number_of_results},
                    }
                }
            }],
            agenticRetrieveConfiguration={
                "foundationModelType": "MANAGED",
                "rerankingModelType": "MANAGED",
            },
        )
        results = []
        for event in response.get("stream", []):
            if "result" in event and "results" in event["result"]:
                for r in event["result"]["results"]:
                    results.append({
                        "content": r.get("content", {}).get("text", ""),
                        "source": _get_source_uri(r),
                        "score": r.get("score", 0),
                    })
        return results

    def _standard_retrieve(self, query: str) -> list[dict[str, Any]]:
        """Use standard Retrieve API with managed search configuration."""
        response = self._client.retrieve(
            knowledgeBaseId=self.knowledge_base_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={"managedSearchConfiguration": {"numberOfResults": self.number_of_results}},
        )
        results = []
        for r in response.get("retrievalResults", []):
            results.append({
                "content": r.get("content", {}).get("text", ""),
                "source": _get_source_uri(r),
                "score": r.get("score", 0),
            })
        return results

    @staticmethod
    def _format_results(results: list[dict[str, Any]]) -> str:
        """Format retrieval results as a readable string."""
        if not results:
            return "No relevant documents found."
        parts = []
        for i, r in enumerate(results, 1):
            source = r.get("source", "")
            content = r.get("content", "")
            score = r.get("score", 0)
            parts.append(f"[{i}] (score: {score:.3f}) {content}\n    Source: {source}")
        return "\n\n".join(parts)
