# Copyright (c) Microsoft. All rights reserved.
"""Amazon Bedrock Knowledge Base retrieval tool for Microsoft Agent Framework.

Provides document retrieval from Amazon Bedrock Managed Knowledge Bases
for use as a tool in agent workflows.

Usage:
    from agent_framework_tools.bedrock_knowledge_base import BedrockKnowledgeBaseTool

    kb_tool = BedrockKnowledgeBaseTool(knowledge_base_id="ABCDEFGHIJ")
    results = await kb_tool.run(query="What is our deployment process?")
"""

import logging
import os
from typing import Any, Optional

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


class BedrockKnowledgeBaseTool:
    """Retrieves documents from an Amazon Bedrock Managed Knowledge Base.

    Args:
        knowledge_base_id: The KB ID. Falls back to KNOWLEDGE_BASE_ID env var.
        region_name: AWS region. Falls back to AWS_REGION env var or us-east-1.
        number_of_results: Max results to return. Defaults to 5.
        use_agentic_retrieval: If True, try AgenticRetrieveStream first with fallback to plain Retrieve.
    """

    name: str = "bedrock_knowledge_base"
    description: str = (
        "Retrieves relevant documents from an Amazon Bedrock Knowledge Base. "
        "Use this to search internal documentation and knowledge sources."
    )

    def __init__(
        self,
        knowledge_base_id: Optional[str] = None,
        region_name: Optional[str] = None,
        number_of_results: int = 5,
        use_agentic_retrieval: Optional[bool] = None,
    ):
        self.knowledge_base_id = knowledge_base_id or os.environ.get("KNOWLEDGE_BASE_ID", "")
        self.region_name = region_name or os.environ.get("AWS_REGION", "us-east-1")
        self.number_of_results = number_of_results
        self.use_agentic_retrieval = (
            use_agentic_retrieval
            if use_agentic_retrieval is not None
            else os.environ.get("USE_AGENTIC_RETRIEVAL", "true").lower() != "false"
        )
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError:
                raise ImportError(
                    "boto3 is required for Bedrock Knowledge Base tool. Install with: pip install boto3>=1.43.2"
                )
            self._client = boto3.client(
                "bedrock-agent-runtime",
                region_name=self.region_name,
                config=Config(user_agent_extra="ms-agent-framework/bedrock-kb"),
            )
        return self._client

    async def run(self, query: str, **kwargs) -> list[dict[str, Any]]:
        """Retrieve relevant documents.

        Args:
            query: The search query.

        Returns:
            List of results with content, source, and score.
        """
        k = kwargs.get("max_results", self.number_of_results)

        # Try agentic retrieval first
        if self.use_agentic_retrieval:
            agentic_results = self._agentic_retrieve(query, k)
            if agentic_results is not None:
                return agentic_results

        # Fallback to managed retrieve
        retrieval_config = {"managedSearchConfiguration": {"numberOfResults": k}}

        try:
            response = self.client.retrieve(
                knowledgeBaseId=self.knowledge_base_id,
                retrievalQuery={"text": query},
                retrievalConfiguration=retrieval_config,
            )

            results = []
            for result in response.get("retrievalResults", []):
                content = result.get("content", {}).get("text", "")
                source = _get_source_uri(result)
                score = result.get("score", 0.0)
                results.append({
                    "content": content,
                    "source": source,
                    "score": score,
                })
            return results
        except Exception:
            logger.exception("Error retrieving from Bedrock KB")
            return []

    def _agentic_retrieve(self, query: str, top_k: int) -> list[dict[str, Any]] | None:
        """Try agentic retrieval with streaming. Returns list of results or None on failure."""
        try:
            response = self.client.agentic_retrieve_stream(
                knowledgeBaseId=self.knowledge_base_id,
                messages=[{"content": {"text": query}, "role": "user"}],
                retrievers=[
                    {
                        "configuration": {
                            "knowledgeBase": {
                                "knowledgeBaseId": self.knowledge_base_id,
                                "retrievalOverrides": {"maxNumberOfResults": top_k},
                            }
                        }
                    }
                ],
                agenticRetrieveConfiguration={
                    "foundationModelType": "MANAGED",
                    "rerankingModelType": "MANAGED",
                },
            )
            results = []
            for event in response.get("stream", []):
                if "result" in event and "results" in event["result"]:
                    for result in event["result"]["results"]:
                        results.append({
                            "content": result.get("content", {}).get("text", ""),
                            "source": _get_source_uri(result),
                            "score": result.get("score", 0.0),
                        })
            return results
        except Exception as e:
            logger.debug(f"Agentic retrieval unavailable, will fall back to managed retrieve: {e}")
            return None

    def get_tool_definition(self) -> dict[str, Any]:
        """Return the tool definition for registration with an agent."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to find relevant documents.",
                    }
                },
                "required": ["query"],
            },
        }
