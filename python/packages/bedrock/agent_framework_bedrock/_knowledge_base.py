# Copyright (c) Microsoft. All rights reserved.
# Copyright (c) Microsoft. All rights reserved.

"""Amazon Bedrock Knowledge Base retrieval tool for Agent Framework."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from agent_framework import FunctionTool
from agent_framework._settings import SecretString, load_settings
from agent_framework._telemetry import get_user_agent, mark_feature_used
from pydantic import BaseModel, Field

from ._feature_usage import FeatureIndex

if TYPE_CHECKING:
    from botocore.client import BaseClient

try:
    from boto3.session import Session as Boto3Session
    from botocore.config import Config as BotoConfig
except ImportError as e:
    raise ImportError(
        "boto3 is required for BedrockKnowledgeBaseTool. Install it with: pip install boto3>=1.43.32"
    ) from e

logger = logging.getLogger("agent_framework.bedrock")

DEFAULT_REGION = "us-east-1"

# Bedrock RetrievalResultContent.type values whose payload is binary (in byteContent),
# not text. A text retrieval tool renders these as placeholders. The full enum is
# TEXT | IMAGE | AUDIO | VIDEO | ROW; ROW is handled separately.
_BINARY_MEDIA_CONTENT_TYPES = frozenset({"IMAGE", "AUDIO", "VIDEO"})


class _KnowledgeBaseSettings(TypedDict, total=False):
    """Bedrock KB settings resolved from constructor args, env vars, or .env files.

    Mirrors ``BedrockSettings`` / ``BedrockEmbeddingSettings`` so the KB tool and
    provider resolve region and credentials the same way as ``BedrockChatClient``
    and the embedding client (env prefix ``BEDROCK_``).
    """

    region: str | None
    access_key: SecretString | None
    secret_key: SecretString | None
    session_token: SecretString | None


def _build_kb_client(
    *,
    client: BaseClient | None,
    boto3_session: Boto3Session | None,
    region: str | None,
    access_key: str | None,
    secret_key: str | None,
    session_token: str | None,
    env_file_path: str | None,
    env_file_encoding: str | None,
) -> BaseClient:
    """Build a ``bedrock-agent-runtime`` client using the shared Bedrock settings path.

    Resolves ``BEDROCK_REGION`` / ``BEDROCK_ACCESS_KEY`` / ``BEDROCK_SECRET_KEY`` /
    ``BEDROCK_SESSION_TOKEN`` (and .env files) the same way as ``BedrockChatClient``
    and the embedding client, and accepts a caller-supplied ``client`` or
    ``boto3_session`` so the KB tool/provider and a configured chat client can share
    region and credentials instead of silently diverging.
    """
    if client is not None:
        return client

    settings = load_settings(
        _KnowledgeBaseSettings,
        env_prefix="BEDROCK_",
        region=region,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )
    resolved_region = settings.get("region") or DEFAULT_REGION

    if boto3_session is None:
        session_kwargs: dict[str, Any] = {}
        if region_setting := settings.get("region"):
            session_kwargs["region_name"] = region_setting
        if (ak := settings.get("access_key")) and (sk := settings.get("secret_key")):
            session_kwargs["aws_access_key_id"] = ak.get_secret_value()
            session_kwargs["aws_secret_access_key"] = sk.get_secret_value()
        if st := settings.get("session_token"):
            session_kwargs["aws_session_token"] = st.get_secret_value()
        boto3_session = Boto3Session(**session_kwargs)

    return boto3_session.client(
        "bedrock-agent-runtime",
        region_name=boto3_session.region_name or resolved_region,
        config=BotoConfig(user_agent_extra=f"{get_user_agent()} bedrock-kb"),
    )


def _get_source_uri(result: dict[str, Any]) -> str:
    """Extract source URI from a standard Retrieve result location.

    Handles every location variant in the Bedrock Retrieve response union
    (per the boto3 >= 1.43.32 schema). Agentic results use a different schema
    and derive their source from ``metadata._source_uri`` instead.
    """
    location = result.get("location", {})
    if "s3Location" in location:
        return location["s3Location"].get("uri", "")
    if "webLocation" in location:
        return location["webLocation"].get("url", "")
    if "confluenceLocation" in location:
        return location["confluenceLocation"].get("url", "")
    if "sharePointLocation" in location:
        return location["sharePointLocation"].get("url", "")
    if "googleDriveLocation" in location:
        return location["googleDriveLocation"].get("url", "")
    if "oneDriveLocation" in location:
        return location["oneDriveLocation"].get("url", "")
    if "salesforceLocation" in location:
        return location["salesforceLocation"].get("url", "")
    if "kendraDocumentLocation" in location:
        return location["kendraDocumentLocation"].get("uri", "")
    if "sqlLocation" in location:
        return location["sqlLocation"].get("query", "")
    if "customDocumentLocation" in location:
        return location["customDocumentLocation"].get("id", "")
    return ""


def _extract_content_text(result: dict[str, Any]) -> str:
    """Extract passage text from a Retrieve result, handling every content type.

    The Bedrock ``RetrievalResultContent`` union has a ``type`` of ``TEXT``, ``IMAGE``,
    ``AUDIO``, ``VIDEO``, or ``ROW`` (SQL knowledge bases). A ``ROW`` result carries no
    ``text`` field — its data is in ``row`` as a list of ``{columnName, columnValue}``
    entries — so reading only ``content.text`` would emit an empty passage and discard
    every column value. This renders ROW columns as ``columnName: columnValue`` lines
    instead. Binary media types (``IMAGE``, ``AUDIO``, ``VIDEO``) carry their payload in
    ``byteContent`` (not text); since this is a text retrieval tool, each is rendered as
    a short placeholder rather than an empty string, so it does not surface as a blank
    numbered result or a source header with no body.
    """
    content = result.get("content", {}) or {}
    content_type = content.get("type", "TEXT")
    if content_type == "ROW":
        columns = content.get("row", []) or []
        rendered = [
            f"{col.get('columnName', '')}: {col.get('columnValue', '')}"
            for col in columns
            if col.get("columnName") or col.get("columnValue")
        ]
        return "\n".join(rendered)
    if content_type in _BINARY_MEDIA_CONTENT_TYPES:
        # Binary media payload lives in content.byteContent, not content.text. A text
        # tool cannot render bytes, so emit a placeholder instead of an empty passage.
        return f"[{content_type.lower()} content omitted]"
    # Default handling for the TEXT content type.
    return content.get("text", "")


@dataclass
class _KnowledgeBasePassage:
    """A single normalized passage from a standard Bedrock ``Retrieve`` response.

    Shared representation so the tool and the context provider extract content,
    source, and score in exactly one place. ``score`` is the numeric relevance
    score standard ``Retrieve`` returns per chunk (agentic results have none).
    """

    content: str
    source: str
    score: float


def _retrieve_standard_passages(
    client: BaseClient,
    knowledge_base_id: str,
    query: str,
    number_of_results: int,
) -> list[_KnowledgeBasePassage]:
    """Run the standard ``Retrieve`` API and normalize the results.

    Single source of truth for the standard-retrieval request shape
    (``managedSearchConfiguration``) and response normalization, so retrieval
    options or SDK response changes are updated in one place. Callers format the
    passages (the tool) or filter by score and frame them as context (the
    provider) without duplicating the request or the extraction.
    """
    # bedrock-agent-runtime is dynamically typed by botocore (no stubs); annotate the
    # response so the extraction below is typed.
    response: dict[str, Any] = client.retrieve(  # pyright: ignore[reportUnknownMemberType]
        knowledgeBaseId=knowledge_base_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={"managedSearchConfiguration": {"numberOfResults": number_of_results}},
    )
    results: list[dict[str, Any]] = response.get("retrievalResults", [])
    return [
        _KnowledgeBasePassage(
            content=_extract_content_text(r),
            source=_get_source_uri(r),
            score=r.get("score", 0),
        )
        for r in results
    ]


class _BedrockKBQueryInput(BaseModel):
    """Input schema for the Bedrock Knowledge Base tool."""

    query: Annotated[str, Field(description="The search query to find relevant documents in the knowledge base.")]


class BedrockKnowledgeBaseTool(FunctionTool):
    """Tool that retrieves documents from Amazon Bedrock Knowledge Bases.

    Subclasses FunctionTool so it can be passed directly to any Agent or ChatClient.

    Usage:
        from agent_framework_bedrock import BedrockKnowledgeBaseTool, BedrockChatClient
        from agent_framework import Agent

        tool = BedrockKnowledgeBaseTool(knowledge_base_id="YOUR_KB_ID")
        agent = Agent(client=BedrockChatClient(model="..."), tools=[tool])
    """

    def __init__(
        self,
        *,
        knowledge_base_id: str,
        region_name: str | None = None,
        number_of_results: int = 5,
        use_agentic_retrieval: bool = True,
        client: BaseClient | None = None,
        boto3_session: Boto3Session | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        session_token: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        name: str = "bedrock_knowledge_base",
        description: str = (
            "Retrieves relevant documents from an Amazon Bedrock Knowledge Base. "
            "Use this to answer questions that require specific knowledge or context."
        ),
    ) -> None:
        """Create a Bedrock Knowledge Base tool.

        Region and credentials are resolved the same way as ``BedrockChatClient`` and
        the embedding client — from these arguments, then the ``BEDROCK_*`` environment
        variables (``BEDROCK_REGION``, ``BEDROCK_ACCESS_KEY``, ``BEDROCK_SECRET_KEY``,
        ``BEDROCK_SESSION_TOKEN``), then an optional .env file — so a KB tool and a
        configured ``BedrockChatClient()`` target the same region/credentials by default.

        Args:
            knowledge_base_id: The Bedrock Knowledge Base ID.
            region_name: AWS region name; falls back to ``BEDROCK_REGION`` then us-east-1.
            number_of_results: Maximum number of results to return.
            use_agentic_retrieval: Use AgenticRetrieveStream for query decomposition + reranking.
            client: Pre-configured bedrock-agent-runtime client. If given, it is used as-is.
            boto3_session: Optional boto3 Session to build the client from.
            access_key: Optional AWS access key; falls back to ``BEDROCK_ACCESS_KEY``.
            secret_key: Optional AWS secret key; falls back to ``BEDROCK_SECRET_KEY``.
            session_token: Optional AWS session token; falls back to ``BEDROCK_SESSION_TOKEN``.
            env_file_path: Optional path to a .env file to load settings from.
            env_file_encoding: Encoding for the .env file.
            name: Tool name for model registration.
            description: Tool description for model context.
        """
        self.knowledge_base_id = knowledge_base_id
        self.number_of_results = number_of_results
        self.use_agentic_retrieval = use_agentic_retrieval

        self._client = _build_kb_client(
            client=client,
            boto3_session=boto3_session,
            region=region_name,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        self.region_name = self._client.meta.region_name

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
        mark_feature_used(FeatureIndex.BEDROCK)

        if self.use_agentic_retrieval:
            try:
                results = await asyncio.to_thread(self._agentic_retrieve, query)
                if results:
                    return self._format_results(results)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug("Agentic retrieval failed, falling back: %s", e)

        results = await asyncio.to_thread(self._standard_retrieve, query)
        return self._format_results(results)

    def _agentic_retrieve(self, query: str) -> list[dict[str, Any]]:
        """Use AgenticRetrieveStream for query decomposition + managed reranking."""
        response: dict[str, Any] = self._client.agentic_retrieve_stream(  # pyright: ignore[reportUnknownMemberType]
            messages=[{"content": {"text": query}, "role": "user"}],
            # This tool returns retrieval passages only; the agent's own model
            # generates the final answer. AgenticRetrieveStream defaults to
            # generating a response (streamed responseEvents we would discard),
            # so disable it explicitly to avoid unnecessary generation latency/cost.
            generateResponse=False,
            retrievers=[
                {
                    "configuration": {
                        "knowledgeBase": {
                            "knowledgeBaseId": self.knowledge_base_id,
                            "retrievalOverrides": {"maxNumberOfResults": self.number_of_results},
                        }
                    }
                }
            ],
            agenticRetrieveConfiguration={
                "foundationModelType": "MANAGED",
                "rerankingModelType": "MANAGED",
            },
        )
        results: list[dict[str, Any]] = []
        for event in response.get("stream", []):
            if "result" in event and "results" in event["result"]:
                for r in event["result"]["results"]:
                    # AgenticRetrieveStream results use a different schema than standard
                    # Retrieve: they expose `content`/`metadata`/`sourceRetriever` and do
                    # NOT include `score` or `location`. The source URI lives in metadata,
                    # and managed reranking orders results without exposing a numeric score.
                    metadata = r.get("metadata", {}) or {}
                    results.append({
                        "content": r.get("content", {}).get("text", ""),
                        "source": metadata.get("_source_uri", ""),
                        "score": None,
                    })
        return results

    def _standard_retrieve(self, query: str) -> list[dict[str, Any]]:
        """Use standard Retrieve API with managed search configuration."""
        passages = _retrieve_standard_passages(self._client, self.knowledge_base_id, query, self.number_of_results)
        return [{"content": p.content, "source": p.source, "score": p.score} for p in passages]

    @staticmethod
    def _format_results(results: list[dict[str, Any]]) -> str:
        """Format retrieval results as a readable string."""
        if not results:
            return "No relevant documents found."
        parts = []
        for i, r in enumerate(results, 1):
            source = r.get("source", "")
            content = r.get("content", "")
            score = r.get("score")
            # Standard Retrieve results carry a numeric relevance score; agentic
            # (managed reranking) results do not, so only render it when present.
            header = f"[{i}] (score: {score:.3f})" if isinstance(score, (int, float)) else f"[{i}]"
            parts.append(f"{header} {content}\n    Source: {source}")
        return "\n\n".join(parts)
