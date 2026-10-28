# Copyright (c) Microsoft. All rights reserved.

"""Amazon Bedrock Knowledge Base retrieval (internal tool + shared helpers).

The public entry point is ``BedrockKnowledgeBaseProvider`` (see
``_knowledge_base_provider.py``). ``BedrockKnowledgeBaseTool`` here is an internal
``FunctionTool`` the provider exposes when its ``mode`` includes tool use; it is not
part of the public API.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypedDict, cast

from agent_framework import FunctionTool
from agent_framework._settings import SecretString, load_settings
from agent_framework._telemetry import get_user_agent, mark_feature_used
from boto3.session import Session as Boto3Session
from botocore.config import Config as BotoConfig

from ._feature_usage import FeatureIndex

if TYPE_CHECKING:
    from botocore.client import BaseClient

logger = logging.getLogger("agent_framework.bedrock")

DEFAULT_REGION = "us-east-1"

# Image formats Bedrock Converse accepts in an image block (see BedrockChatClient). Other
# image formats are rendered as text rather than injected as Content the chat client drops.
SUPPORTED_IMAGE_FORMATS = frozenset({"gif", "jpeg", "png", "webp"})

# Bedrock Converse tool names must match this pattern and be at most 64 characters.
TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

_DATA_URI_PATTERN = re.compile(r"^data:(?P<mime>[^;,]+);base64,(?P<data>.*)$", re.DOTALL)


class BedrockKnowledgeBaseSettings(TypedDict, total=False):
    """Bedrock KB settings resolved from constructor args, env vars, or .env files.

    Mirrors ``BedrockSettings`` / ``BedrockEmbeddingSettings`` so the KB tool and
    provider resolve region and credentials the same way as ``BedrockChatClient``
    and the embedding client (env prefix ``BEDROCK_``).
    """

    region: str | None
    access_key: SecretString | None
    secret_key: SecretString | None
    session_token: SecretString | None


def build_kb_client(
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
        BedrockKnowledgeBaseSettings,
        env_prefix="BEDROCK_",
        region=region,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )
    # Same precedence as BedrockChatClient: an explicit/configured region wins over a
    # supplied session's default region, so chat and KB calls target the same region.
    session_region = _session_region(boto3_session)
    resolved_region = settings.get("region") or session_region or DEFAULT_REGION

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

    # boto3 has no type stubs, so ``Session.client`` is untyped; the declared return
    # type is what callers rely on.
    return cast(
        "BaseClient",
        boto3_session.client(  # pyright: ignore[reportUnknownMemberType]
            "bedrock-agent-runtime",
            region_name=resolved_region,
            config=BotoConfig(user_agent_extra=f"{get_user_agent()} bedrock-kb"),
        ),
    )


def _session_region(session: Boto3Session | None) -> str | None:
    """Return a boto3 session's default region (boto3 has no type stubs)."""
    if session is None:
        return None
    return cast("str | None", session.region_name)  # pyright: ignore[reportUnknownMemberType]


def client_region(client: BaseClient) -> str | None:
    """Return the region a botocore client targets (``client.meta`` is untyped)."""
    return cast("str | None", client.meta.region_name)  # pyright: ignore[reportUnknownMemberType]


def _as_dict(value: Any) -> dict[str, Any]:
    """Return ``value`` if it is a dict, else an empty dict (typed view of SDK JSON)."""
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    """Return ``value`` if it is a list, else an empty list (typed view of SDK JSON)."""
    return cast(list[Any], value) if isinstance(value, list) else []


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
    instead. ``AUDIO`` and ``VIDEO`` results carry a text ``transcription`` / ``summary``,
    which is used as the passage text. ``IMAGE`` results carry binary data (see
    ``_extract_image``); their text form is a short placeholder so they never surface as a
    blank numbered result or a source header with no body.
    """
    content = _as_dict(result.get("content"))
    content_type = content.get("type") or "TEXT"
    if content_type == "ROW":
        rendered: list[str] = []
        for item in _as_list(content.get("row")):
            col = _as_dict(item)
            if col.get("columnName") or col.get("columnValue"):
                rendered.append(f"{col.get('columnName', '')}: {col.get('columnValue', '')}")
        return "\n".join(rendered)
    if content_type == "AUDIO":
        return str(_as_dict(content.get("audio")).get("transcription") or "[audio content omitted]")
    if content_type == "VIDEO":
        return str(_as_dict(content.get("video")).get("summary") or "[video content omitted]")
    if content_type == "IMAGE":
        return str(content.get("text") or "[image content omitted]")
    # Default handling for the TEXT content type.
    return str(content.get("text") or "")


def _extract_image(result: dict[str, Any]) -> tuple[bytes, str] | None:
    """Return ``(bytes, mime_type)`` for an image result, or ``None``.

    Standard ``Retrieve`` returns image data as a ``data:<mime>;base64,<data>`` URI in
    ``content.byteContent``. Agentic results return already-decoded bytes in
    ``content.byteContent`` with a separate ``content.mimeType``.
    """
    content = _as_dict(result.get("content"))
    raw: Any = content.get("byteContent")
    if not raw:
        return None
    if isinstance(raw, (bytes, bytearray)):
        mime = str(content.get("mimeType") or "")
        return (bytes(cast(bytes, raw)), mime) if mime.startswith("image/") else None
    match = _DATA_URI_PATTERN.match(str(raw))
    if not match or not match.group("mime").startswith("image/"):
        return None
    try:
        return base64.b64decode(match.group("data"), validate=True), match.group("mime")
    except (binascii.Error, ValueError):
        return None


@dataclass
class _KnowledgeBasePassage:
    """A single normalized passage from a standard Bedrock ``Retrieve`` response.

    Shared representation so the tool and the context provider extract content,
    source, and score in exactly one place. ``score`` is the numeric relevance
    score standard ``Retrieve`` returns per chunk, or ``None`` for agentic results,
    whose API exposes no numeric score.
    """

    content: str
    source: str
    score: float | None
    image: tuple[bytes, str] | None = None


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
    # bedrock-agent-runtime is dynamically typed by botocore (no stubs); cast the
    # response so the extraction below is typed.
    response = cast(
        dict[str, Any],
        client.retrieve(  # pyright: ignore[reportUnknownMemberType]
            knowledgeBaseId=knowledge_base_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={"managedSearchConfiguration": {"numberOfResults": number_of_results}},
        ),
    )
    passages: list[_KnowledgeBasePassage] = []
    for item in _as_list(response.get("retrievalResults")):
        r = _as_dict(item)
        score = r.get("score")
        passages.append(
            _KnowledgeBasePassage(
                content=_extract_content_text(r),
                source=_get_source_uri(r),
                score=float(score) if isinstance(score, (int, float)) else 0.0,
                image=_extract_image(r),
            )
        )
    return passages


def _retrieve_agentic_passages(
    client: BaseClient,
    knowledge_base_id: str,
    query: str,
    number_of_results: int,
) -> list[_KnowledgeBasePassage]:
    """Run ``AgenticRetrieveStream`` (query decomposition + managed reranking) and normalize.

    Agentic results use a different schema than standard ``Retrieve``: they expose
    ``content``/``metadata``/``sourceRetriever`` and carry no ``score`` or ``location``,
    so the source URI comes from ``metadata._source_uri`` and ``score`` is ``None`` (managed
    reranking orders results without exposing a numeric score). ``generateResponse`` is
    disabled: callers want passages, not a service-generated answer.
    """
    response = cast(
        dict[str, Any],
        client.agentic_retrieve_stream(  # pyright: ignore[reportUnknownMemberType]
            messages=[{"content": {"text": query}, "role": "user"}],
            generateResponse=False,
            retrievers=[
                {
                    "configuration": {
                        "knowledgeBase": {
                            "knowledgeBaseId": knowledge_base_id,
                            "retrievalOverrides": {"maxNumberOfResults": number_of_results},
                        }
                    }
                }
            ],
            agenticRetrieveConfiguration={
                "foundationModelType": "MANAGED",
                "rerankingModelType": "MANAGED",
            },
        ),
    )
    passages: list[_KnowledgeBasePassage] = []
    for event in _as_list(response.get("stream")):
        result = _as_dict(_as_dict(event).get("result"))
        if "results" not in result:
            continue
        for item in _as_list(result["results"]):
            r = _as_dict(item)
            metadata = _as_dict(r.get("metadata"))
            image = _extract_image(r)
            text = str(_as_dict(r.get("content")).get("text") or ("[image content omitted]" if image else ""))
            passages.append(
                _KnowledgeBasePassage(
                    content=text,
                    source=str(metadata.get("_source_uri") or ""),
                    score=None,
                    image=image,
                )
            )
    return passages


def retrieve_passages(
    client: BaseClient,
    knowledge_base_id: str,
    query: str,
    number_of_results: int,
    *,
    use_agentic_retrieval: bool,
) -> list[_KnowledgeBasePassage]:
    """Retrieve passages, using agentic retrieval when enabled and falling back to standard.

    Shared by the tool and the provider so both consume the KB the same way. When
    ``use_agentic_retrieval`` is set, ``AgenticRetrieveStream`` is tried first (query
    decomposition + managed reranking); if it fails or returns nothing, this falls back
    to the standard ``Retrieve`` API.
    """
    if use_agentic_retrieval:
        try:
            passages = _retrieve_agentic_passages(client, knowledge_base_id, query, number_of_results)
            if passages:
                return passages
        except Exception as e:
            logger.debug("Agentic retrieval failed, falling back to standard Retrieve: %s", e)
    return _retrieve_standard_passages(client, knowledge_base_id, query, number_of_results)


class BedrockKnowledgeBaseTool(FunctionTool):
    """Internal ``FunctionTool`` that retrieves documents from an Amazon Bedrock Knowledge Base.

    Not part of the public API. ``BedrockKnowledgeBaseProvider`` constructs and exposes
    this tool when its ``mode`` includes tool use (``"tool"`` or ``"both"``); it can also
    be passed directly to an Agent's ``tools`` list internally.
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
        the embedding client: explicit arguments first, then the ``.env`` file (when
        ``env_file_path`` is given), then the ``BEDROCK_*`` environment variables
        (``BEDROCK_REGION``, ``BEDROCK_ACCESS_KEY``, ``BEDROCK_SECRET_KEY``,
        ``BEDROCK_SESSION_TOKEN``). A resolved region takes precedence over a supplied
        ``boto3_session``'s default region, so a KB tool and a configured
        ``BedrockChatClient()`` target the same region/credentials by default.

        Args:
            knowledge_base_id: The Bedrock Knowledge Base ID.
            region_name: AWS region name; falls back to ``BEDROCK_REGION``, then the
                ``boto3_session`` region, then us-east-1.
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

        self._client = build_kb_client(
            client=client,
            boto3_session=boto3_session,
            region=region_name,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        self.region_name = client_region(self._client)

        super().__init__(
            name=name,
            description=description,
            func=self._retrieve,
            input_model={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to find relevant documents in the knowledge base.",
                    }
                },
                "required": ["query"],
            },
        )

    async def _retrieve(self, query: str) -> str:
        """Retrieve documents from the knowledge base and format them as text.

        Args:
            query: The search query.

        Returns:
            Formatted string of retrieval results.
        """
        mark_feature_used(FeatureIndex.BEDROCK)
        passages = await asyncio.to_thread(
            retrieve_passages,
            self._client,
            self.knowledge_base_id,
            query,
            self.number_of_results,
            use_agentic_retrieval=self.use_agentic_retrieval,
        )
        return self._format_results(passages)

    @staticmethod
    def _format_results(passages: list[_KnowledgeBasePassage]) -> str:
        """Format retrieval passages as a readable string."""
        if not passages:
            return "No relevant documents found."
        parts: list[str] = []
        for i, p in enumerate(passages, 1):
            # Standard Retrieve results carry a numeric relevance score; agentic
            # (managed reranking) results do not, so only render it when present (> 0).
            header = f"[{i}] (score: {p.score:.3f})" if p.score is not None else f"[{i}]"
            parts.append(f"{header} {p.content}\n    Source: {p.source}")
        return "\n\n".join(parts)
