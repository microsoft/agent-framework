# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import math
import sys
from collections.abc import Sequence
from typing import Any, ClassVar, Generic, Literal

from agent_framework import (
    BaseEmbeddingClient,
    Embedding,
    EmbeddingGenerationOptions,
    GeneratedEmbeddings,
    UsageDetails,
    load_settings,
)
from agent_framework._settings import SecretString
from agent_framework._telemetry import mark_feature_used
from agent_framework.exceptions import (
    IntegrationException,
    IntegrationInvalidAuthException,
    IntegrationInvalidRequestException,
    IntegrationInvalidResponseException,
)
from agent_framework.observability import EmbeddingTelemetryLayer
from google import genai
from google.auth.credentials import Credentials
from google.genai import types
from google.genai.errors import APIError as GenAIAPIError
from typing_extensions import TypedDict

from ._feature_usage import FeatureIndex
from ._sdk_client import (
    GoogleGeminiSettings,
    create_genai_client,
    resolve_service_url,
    resolve_vertexai_mode,
)

if sys.version_info >= (3, 13):
    from typing import TypeVar  # pragma: no cover
else:
    from typing_extensions import TypeVar  # pragma: no cover

_DEFAULT_EMBEDDING_MODEL = "gemini-embedding-2"
_SUPPORTED_EMBEDDING_MODELS = ("gemini-embedding-2", "gemini-embedding-2-preview")
_QUERY_TASK_PREFIXES = {
    "RETRIEVAL_QUERY": "search result",
    "QUESTION_ANSWERING": "question answering",
    "FACT_VERIFICATION": "fact checking",
    "CODE_RETRIEVAL_QUERY": "code retrieval",
    "CLASSIFICATION": "classification",
    "CLUSTERING": "clustering",
    "SEMANTIC_SIMILARITY": "sentence similarity",
}


class GeminiEmbeddingOptions(EmbeddingGenerationOptions, total=False):
    """Google Gemini-specific embedding options.

    ``task_type`` is required per call for text strings, and is not used for
    multimodal ``google.genai.types.Content`` or media ``Part`` inputs. The
    client formats text according to the Embedding 2 task instructions at
    https://ai.google.dev/gemini-api/docs/embeddings.
    """

    task_type: Literal[
        "RETRIEVAL_DOCUMENT",
        "RETRIEVAL_QUERY",
        "QUESTION_ANSWERING",
        "FACT_VERIFICATION",
        "CODE_RETRIEVAL_QUERY",
        "CLASSIFICATION",
        "CLUSTERING",
        "SEMANTIC_SIMILARITY",
    ]
    title: str


GeminiEmbeddingOptionsT = TypeVar(
    "GeminiEmbeddingOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="GeminiEmbeddingOptions",
    covariant=True,
)


def _validate_embedding_model(model: object) -> str:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty string")
    if model not in _SUPPORTED_EMBEDDING_MODELS:
        raise ValueError(
            f"Unsupported Gemini embedding model {model!r}; use gemini-embedding-2 or gemini-embedding-2-preview."
        )
    return model


def _prepare_text_for_embedding(text: str, *, task_type: str, title: str | None) -> str:
    if task_type == "RETRIEVAL_DOCUMENT":
        return f"title: {title or 'none'} | text: {text}"
    return f"task: {_QUERY_TASK_PREFIXES[task_type]} | query: {text}"


def _prepare_multimodal_content(value: types.Content | types.Part, *, index: int) -> types.Content:
    content = types.Content(parts=[value]) if isinstance(value, types.Part) else value
    if not content.parts or not any(
        part.inline_data is not None or part.file_data is not None for part in content.parts
    ):
        raise ValueError(f"Multimodal input at index {index} requires a media part; pass text as str with task_type.")
    return content


def _wrap_gemini_embedding_error(ex: Exception) -> IntegrationException:
    """Translate SDK failures into the framework's integration exception hierarchy."""
    if isinstance(ex, ValueError):
        return IntegrationInvalidRequestException(f"Invalid Gemini embeddings request: {ex}", inner_exception=ex)
    if isinstance(ex, GenAIAPIError):
        code = getattr(ex, "code", None)
        if code in (401, 403):
            return IntegrationInvalidAuthException(f"Gemini embeddings authentication failed: {ex}", inner_exception=ex)
        if isinstance(code, int) and 400 <= code < 500:
            return IntegrationInvalidRequestException(f"Invalid Gemini embeddings request: {ex}", inner_exception=ex)
    return IntegrationException(f"Gemini embeddings request failed: {ex}", inner_exception=ex)


class RawGeminiEmbeddingClient(
    BaseEmbeddingClient[str | types.Content | types.Part, list[float], GeminiEmbeddingOptionsT],
    Generic[GeminiEmbeddingOptionsT],
):
    """Generate text and multimodal embeddings via Gemini Developer API or Vertex AI without telemetry.

    Keyword Args:
        model: ``gemini-embedding-2`` (default) or ``gemini-embedding-2-preview``.
            Set ``GOOGLE_EMBEDDING_MODEL`` to override the default.
        api_key: API key, or ``GOOGLE_API_KEY``.
        enterprise: Use Gemini Enterprise Agent Platform, or ``GOOGLE_GENAI_USE_ENTERPRISE``.
        vertexai: Legacy alias for ``enterprise``, or ``GOOGLE_GENAI_USE_VERTEXAI``.
        project: Enterprise (Vertex AI) project, or ``GOOGLE_CLOUD_PROJECT``.
        location: Enterprise (Vertex AI) region, or ``GOOGLE_CLOUD_LOCATION``.
        credentials: Google Cloud credentials for Enterprise; the SDK can also use ADC.
        client: Preconfigured ``genai.Client``; the caller retains ownership of it.
        additional_properties: Extra properties stored on the client instance.
        env_file_path: Optional ``.env`` file for settings.
        env_file_encoding: Encoding for the ``.env`` file.
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "gcp.gemini"

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | SecretString | None = None,
        enterprise: bool | None = None,
        vertexai: bool | None = None,
        project: str | None = None,
        location: str | None = None,
        credentials: Credentials | None = None,
        client: genai.Client | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw Gemini embedding client."""
        google_settings = load_settings(
            GoogleGeminiSettings,
            env_prefix="GOOGLE_",
            api_key=api_key,
            embedding_model=model,
            genai_use_enterprise=enterprise,
            genai_use_vertexai=vertexai,
            cloud_project=project,
            cloud_location=location,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        configured_model = google_settings.get("embedding_model")
        self.model = _validate_embedding_model(
            _DEFAULT_EMBEDDING_MODEL if configured_model is None else configured_model
        )

        configured_enterprise = google_settings.get("genai_use_enterprise")
        configured_vertexai = google_settings.get("genai_use_vertexai")
        self._genai_client = create_genai_client(
            client=client,
            api_key=google_settings.get("api_key"),
            enterprise=configured_enterprise,
            vertexai=configured_vertexai,
            project=google_settings.get("cloud_project"),
            location=google_settings.get("cloud_location"),
            credentials=credentials,
        )
        self._owns_client = client is None
        configured_mode = configured_enterprise if configured_enterprise is not None else configured_vertexai
        self._vertexai = resolve_vertexai_mode(self._genai_client, fallback=configured_mode)
        self._service_url = resolve_service_url(self._genai_client, vertexai=self._vertexai)

        super().__init__(additional_properties=additional_properties)

    def service_url(self) -> str:
        """Return the resolved Gemini Developer API or Vertex AI endpoint."""
        return self._service_url

    async def close(self) -> None:
        """Close both transports when this client created its own Google SDK client."""
        if self._owns_client:
            try:
                await self._genai_client.aio.aclose()
            finally:
                self._genai_client.close()

    async def get_embeddings(
        self,
        values: Sequence[str | types.Content | types.Part],
        *,
        options: GeminiEmbeddingOptionsT | None = None,
    ) -> GeneratedEmbeddings[list[float], GeminiEmbeddingOptionsT]:
        """Generate one embedding per input, preserving the order of texts and multimodal content.

        Args:
            values: Text strings or Google SDK ``Content`` / media ``Part`` values.
                A ``Content`` may aggregate text and media into one embedding.
            options: Model and dimensions, plus a required task type for text strings.
                ``title`` applies only to text using ``RETRIEVAL_DOCUMENT``. Multimodal
                content is never task-prefixed; omit ``task_type`` for media-only calls.

        Returns:
            Embeddings with token counts when the service reports them.

        Raises:
            ValueError: If a text lacks a task type, multimodal content lacks media,
                or the model, dimensions, task type, or title is invalid.
            IntegrationInvalidAuthException: If credentials are rejected by Google.
            IntegrationInvalidRequestException: If Google rejects the request.
            IntegrationInvalidResponseException: If Google returns malformed embeddings.
            IntegrationException: If the SDK request fails for another reason.
        """
        if not values:
            return GeneratedEmbeddings([], options=options)

        opts: dict[str, Any] = options or {}  # type: ignore[assignment]
        model = _validate_embedding_model(opts.get("model", self.model))

        task_type = opts.get("task_type")
        title = opts.get("title")
        if task_type is not None and (
            not isinstance(task_type, str)
            or (task_type != "RETRIEVAL_DOCUMENT" and task_type not in _QUERY_TASK_PREFIXES)
        ):
            raise ValueError(f"Unsupported Gemini embedding task_type: {task_type!r}.")
        if title is not None and (not isinstance(title, str) or not title.strip()):
            raise ValueError("title must be a non-empty string")
        if title is not None and task_type != "RETRIEVAL_DOCUMENT":
            raise ValueError("title requires task_type='RETRIEVAL_DOCUMENT'")

        dimensions = opts.get("dimensions")
        if dimensions is not None and (
            isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions < 1
        ):
            raise ValueError("dimensions must be a positive integer")

        config = types.EmbedContentConfig(output_dimensionality=dimensions)
        contents: list[types.Content] = []
        has_text = False
        for index, value in enumerate(values):
            if isinstance(value, str):
                has_text = True
                if task_type is None:
                    raise ValueError("task_type is required for text embeddings.")
                contents.append(
                    types.Content(
                        parts=[
                            types.Part.from_text(
                                text=_prepare_text_for_embedding(value, task_type=task_type, title=title)
                            )
                        ]
                    )
                )
            elif isinstance(value, (types.Content, types.Part)):
                contents.append(_prepare_multimodal_content(value, index=index))
            else:
                raise ValueError(f"Unsupported embedding input at index {index}: {type(value).__name__}.")
        if not has_text and task_type is not None:
            raise ValueError("task_type is for text strings; omit it when embedding only multimodal content.")

        batches = [[content] for content in contents] if self._vertexai else [contents]
        mark_feature_used(FeatureIndex.GEMINI)
        raw_embeddings: list[types.ContentEmbedding] = []
        billable_characters = 0
        has_billable_characters = True
        for batch in batches:
            try:
                response = await self._genai_client.aio.models.embed_content(  # pyright: ignore[reportUnknownMemberType]
                    model=model,
                    contents=batch,
                    config=config,
                )
            except IntegrationException:
                raise
            except Exception as ex:
                raise _wrap_gemini_embedding_error(ex) from ex

            if not isinstance(response, types.EmbedContentResponse):
                raise IntegrationInvalidResponseException("Gemini embeddings returned an invalid response.")
            batch_embeddings = response.embeddings
            if batch_embeddings is None or len(batch_embeddings) != len(batch):
                raise IntegrationInvalidResponseException(
                    f"Gemini embeddings returned {len(batch_embeddings) if batch_embeddings is not None else 0} "
                    f"vectors for {len(batch)} inputs."
                )
            raw_embeddings.extend(batch_embeddings)
            if response.metadata is not None and response.metadata.billable_character_count is not None:
                billable_characters += response.metadata.billable_character_count
            else:
                has_billable_characters = False

        embeddings: list[Embedding[list[float]]] = []
        total_tokens = 0
        has_token_counts = True
        for item in raw_embeddings:
            if not isinstance(item, types.ContentEmbedding):
                raise IntegrationInvalidResponseException("Gemini embeddings returned an invalid embedding.")
            vector = item.values
            if not vector or any(
                isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                for value in vector
            ):
                raise IntegrationInvalidResponseException("Gemini embeddings returned an invalid vector.")
            if dimensions is not None and len(vector) != dimensions:
                raise IntegrationInvalidResponseException(
                    f"Gemini embeddings returned {len(vector)} dimensions; requested {dimensions}."
                )

            stats = item.statistics
            extra: dict[str, Any] = {}
            if stats is not None:
                if stats.truncated is not None:
                    extra["truncated"] = stats.truncated
                count = stats.token_count
                if count is not None and (
                    isinstance(count, bool)
                    or not isinstance(count, (int, float))
                    or not math.isfinite(count)
                    or count < 0
                ):
                    raise IntegrationInvalidResponseException("Gemini embeddings returned an invalid token count.")
                if count is not None and float(count).is_integer():
                    total_tokens += int(count)
                else:
                    has_token_counts = False
            else:
                has_token_counts = False

            embeddings.append(Embedding(vector=list(vector), model=model, additional_properties=extra))

        usage: UsageDetails | None = None
        if has_token_counts:
            usage = {"input_token_count": total_tokens, "total_token_count": total_tokens}
        metadata: dict[str, Any] = {"billable_character_count": billable_characters} if has_billable_characters else {}
        return GeneratedEmbeddings(embeddings, options=options, usage=usage, additional_properties=metadata)


class GeminiEmbeddingClient(
    EmbeddingTelemetryLayer[str | types.Content | types.Part, list[float], GeminiEmbeddingOptionsT],
    RawGeminiEmbeddingClient[GeminiEmbeddingOptionsT],
    Generic[GeminiEmbeddingOptionsT],
):
    """Gemini Developer API and Enterprise text and multimodal embedding client with telemetry.

    Defaults to stable ``gemini-embedding-2``. Pass ``task_type`` in each text call's
    options: ``RETRIEVAL_DOCUMENT`` for indexing or ``RETRIEVAL_QUERY`` for searching.
    Media ``Part`` and multimodal ``Content`` inputs require no task type.
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "gcp.gemini"

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | SecretString | None = None,
        enterprise: bool | None = None,
        vertexai: bool | None = None,
        project: str | None = None,
        location: str | None = None,
        credentials: Credentials | None = None,
        client: genai.Client | None = None,
        otel_provider_name: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a Gemini embedding client with optional telemetry."""
        super().__init__(
            model=model,
            api_key=api_key,
            enterprise=enterprise,
            vertexai=vertexai,
            project=project,
            location=location,
            credentials=credentials,
            client=client,
            otel_provider_name=otel_provider_name,
            additional_properties=additional_properties,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
