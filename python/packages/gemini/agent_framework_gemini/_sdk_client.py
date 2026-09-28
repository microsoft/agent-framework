# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any

from agent_framework._settings import SecretString
from agent_framework._telemetry import get_user_agent
from google import genai
from google.auth.credentials import Credentials
from typing_extensions import TypedDict


class GoogleGeminiSettings(TypedDict, total=False):
    """Connector settings loaded from ``GOOGLE_*`` environment variables."""

    api_key: SecretString | None
    model: str | None
    embedding_model: str | None
    genai_use_enterprise: bool | None
    genai_use_vertexai: bool | None
    cloud_project: str | None
    cloud_location: str | None


_GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com"
_VERTEX_AI_BASE_URL = "https://aiplatform.googleapis.com"


def resolve_vertexai_mode(client: genai.Client, *, fallback: bool | None = None) -> bool:
    """Resolve whether a client targets Vertex AI, preferring the instantiated SDK client state."""
    api_client = getattr(client, "_api_client", None)
    vertexai = getattr(api_client, "vertexai", None)
    if isinstance(vertexai, bool):
        return vertexai
    return bool(fallback)


def resolve_service_url(client: genai.Client, *, vertexai: bool) -> str:
    """Resolve the base service URL from the instantiated SDK client, with a stable fallback."""
    api_client = getattr(client, "_api_client", None)
    http_options = getattr(api_client, "_http_options", None)
    base_url = getattr(http_options, "base_url", None)
    if isinstance(base_url, str) and base_url:
        return base_url.rstrip("/")
    return _VERTEX_AI_BASE_URL if vertexai else _GEMINI_API_BASE_URL


def _validate_client_auth_configuration(
    *,
    vertexai: bool | None,
    api_key: SecretString | None,
    project: str | None,
    location: str | None,
    credentials: Credentials | None,
) -> None:
    """Validate supported auth combinations before instantiating the SDK client."""
    if vertexai is not True:
        if api_key is None:
            raise ValueError(
                "Gemini client requires an API key when Vertex AI is not enabled. "
                "Set GOOGLE_API_KEY or pass api_key explicitly."
            )
        return

    if api_key is not None or credentials is not None or (project and location):
        return

    if project or location:
        raise ValueError(
            "Gemini client requires both GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION "
            "when Vertex AI is enabled without an API key."
        )

    raise ValueError(
        "Gemini client requires Vertex AI credentials or configuration when Vertex AI is enabled. "
        "Provide GOOGLE_API_KEY for Vertex AI express mode, pass credentials, or set "
        "GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION."
    )


def create_genai_client(
    *,
    client: genai.Client | None,
    api_key: SecretString | None,
    vertexai: bool | None,
    project: str | None,
    location: str | None,
    credentials: Credentials | None,
    enterprise: bool | None = None,
) -> genai.Client:
    """Create an SDK client for either Gemini Developer API or Vertex AI, unless one was supplied."""
    if client is not None:
        return client

    if api_key is not None and not api_key.get_secret_value().strip():
        raise ValueError("GOOGLE_API_KEY must not be empty when provided.")
    if enterprise is not None and vertexai is not None and enterprise != vertexai:
        raise ValueError("GOOGLE_GENAI_USE_ENTERPRISE and GOOGLE_GENAI_USE_VERTEXAI cannot disagree.")
    use_enterprise = enterprise if enterprise is not None else vertexai
    _validate_client_auth_configuration(
        vertexai=use_enterprise,
        api_key=api_key,
        project=project,
        location=location,
        credentials=credentials,
    )
    client_kwargs: dict[str, Any] = {
        "http_options": {"headers": {"x-goog-api-client": get_user_agent()}},
    }
    if enterprise is not None:
        client_kwargs["enterprise"] = enterprise
    elif vertexai is not None:
        client_kwargs["vertexai"] = vertexai

    if api_key is not None and (use_enterprise is not True or (credentials is None and not (project and location))):
        client_kwargs["api_key"] = api_key.get_secret_value()

    if use_enterprise is True and project:
        client_kwargs["project"] = project

    if use_enterprise is True and location:
        client_kwargs["location"] = location
    if use_enterprise is True and credentials is not None:
        client_kwargs["credentials"] = credentials

    return genai.Client(**client_kwargs)
